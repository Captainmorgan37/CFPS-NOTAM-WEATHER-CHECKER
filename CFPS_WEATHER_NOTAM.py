import streamlit as st
import pandas as pd
import requests
import json
import re
from io import BytesIO
from datetime import datetime, timedelta

# ----- CONFIG -----
FAA_CLIENT_ID = st.secrets["FAA_CLIENT_ID"]
FAA_CLIENT_SECRET = st.secrets["FAA_CLIENT_SECRET"]
KEYWORDS = ["CLOSED", "CLSD"]
HIDE_KEYWORDS = ["crane", "RUSSIAN", "CONGO", "OBST RIG", "CANCELLED", "CANCELED", 
                 "SAFETY AREA NOT STD", "GRASS CUTTING", "OBST TOWER"]

st.set_page_config(page_title="CFPS/FAA NOTAM Viewer", layout="wide")
st.title("CFPS & FAA NOTAM Viewer")

# ----- RUNWAYS DATA -----
@st.cache_data
def load_runway_data():
    df = pd.read_csv("runways.csv")
    return df

runways_df = load_runway_data()

# ----- FUNCTIONS -----
def highlight_keywords(notam_text: str):
    for kw in KEYWORDS:
        notam_text = notam_text.replace(
            kw, f"<span style='color:red;font-weight:bold'>{kw}</span>"
        )
    return notam_text

def parse_cfps_times(notam_text):
    start_match = re.search(r'\bB\)\s*(\d{10}|PERM)', notam_text)
    end_match = re.search(r'\bC\)\s*(\d{10}|PERM)', notam_text)

    def format_time(t):
        if not t:
            return 'N/A', None
        if t == 'PERM':
            return 'PERM', None
        dt = datetime.strptime(t, "%y%m%d%H%M")
        return dt.strftime("%b %d %Y, %H:%M"), dt

    start, start_dt = format_time(start_match.group(1)) if start_match else ('N/A', None)
    end, end_dt = format_time(end_match.group(1)) if end_match else ('N/A', None)
    return start, end, start_dt, end_dt

def categorize_notam(text: str) -> str:
    text_upper = text.upper()
    if any(kw in text_upper for kw in ["RWY", "RUNWAY"]):
        return "Runway"
    elif any(kw in text_upper for kw in ["TWY", "APRON", "TAXIWAY"]):
        return "Taxiway/Apron"
    elif any(kw in text_upper for kw in ["AIRSPACE", "VOR", "NAV", "NAVAID", "RADAR"]):
        return "Airspace/Navigation"
    elif any(kw in text_upper for kw in ["OBST", "LIGHT", "TOWER"]):
        return "Obstacle/Lighting"
    else:
        return "Other"

def get_cfps_notams(icao: str):
    url = "https://plan.navcanada.ca/weather/api/alpha/"
    params = {
        "site": icao,
        "alpha": ["notam"],
        "notam_choice": "default",
        "_": "1756244240291"
    }
    query_params = []
    for key, value in params.items():
        if isinstance(value, list):
            for v in value:
                query_params.append((key, v))
        else:
            query_params.append((key, value))

    response = requests.get(url, params=query_params)
    response.raise_for_status()
    data = response.json()
    notams = []

    for n in data.get("data", []):
        if n.get("type") == "notam":
            text = n["text"]
            try:
                notam_json = json.loads(text)
                notam_text = notam_json.get("raw", text)
            except:
                notam_text = text

            if any(hide_kw.lower() in notam_text.lower() for hide_kw in HIDE_KEYWORDS):
                continue

            effective_start, effective_end, start_dt, end_dt = parse_cfps_times(notam_text)
            sort_key = start_dt if start_dt else datetime.min

            notams.append({
                "text": notam_text,
                "effectiveStart": effective_start,
                "effectiveEnd": effective_end,
                "start_dt": start_dt,
                "end_dt": end_dt,
                "sortKey": sort_key,
                "category": categorize_notam(notam_text)
            })

    notams.sort(key=lambda x: (x["category"], x["sortKey"]))
    return notams

def get_faa_notams(icao: str):
    url = "https://external-api.faa.gov/notamapi/v1/notams"
    headers = {
        "client_id": FAA_CLIENT_ID,
        "client_secret": FAA_CLIENT_SECRET
    }
    params = {
        "icaoLocation": icao.upper(),
        "responseFormat": "geoJson",
        "pageSize": 200
    }

    all_items = []
    page_cursor = None

    while True:
        if page_cursor:
            params["pageCursor"] = page_cursor

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        all_items.extend(items)
        page_cursor = data.get("nextPageCursor")
        if not page_cursor:
            break

    notams = []

    for feature in all_items:
        props = feature.get("properties", {})
        core = props.get("coreNOTAMData", {})
        notam_data = core.get("notam", {})

        notam_text = notam_data.get("text", "")
        translations = core.get("notamTranslation", [])
        simple_text = None
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                simple_text = t.get("simpleText")
        text_to_use = simple_text if simple_text else notam_text

        if not simple_text:
            continue

        if any(hide_kw.lower() in text_to_use.lower() for hide_kw in HIDE_KEYWORDS):
            continue

        effective = notam_data.get("effectiveStart", None)
        expiry = notam_data.get("effectiveEnd", None)

        start_dt = end_dt = None
        if effective == "PERM":
            effective_display = "PERM"
        elif effective:
            start_dt = datetime.fromisoformat(effective.replace("Z", ""))
            effective_display = start_dt.strftime("%b %d %Y, %H:%M")
        else:
            effective_display = "N/A"

        if expiry == "PERM":
            expiry_display = "PERM"
        elif expiry:
            end_dt = datetime.fromisoformat(expiry.replace("Z", ""))
            expiry_display = end_dt.strftime("%b %d %Y, %H:%M")
        else:
            expiry_display = "N/A"

        notams.append({
            "text": text_to_use,
            "effectiveStart": effective_display,
            "effectiveEnd": expiry_display,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "sortKey": start_dt if start_dt else datetime.min,
            "category": categorize_notam(text_to_use)
        })

    notams.sort(key=lambda x: (x["category"], x["sortKey"]))
    notams = deduplicate_notams(notams)
    return notams

# ----- Remaining functions (format_notam_card, deduplicate, runway status, user input) -----
# (Use your previous code as-is; just ensure airport["notams"] is sorted by category)
