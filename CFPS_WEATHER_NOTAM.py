import streamlit as st
import pandas as pd
import requests
import json
import re
from io import BytesIO
from datetime import datetime

# ----- CONFIG -----
FAA_CLIENT_ID = st.secrets["FAA_CLIENT_ID"]
FAA_CLIENT_SECRET = st.secrets["FAA_CLIENT_SECRET"]
KEYWORDS = ["CLOSED", "CLSD"]  # Add more keywords here

st.set_page_config(page_title="CFPS & FAA NOTAM Viewer", layout="wide")
st.title("CFPS & FAA NOTAM Viewer")

# ----- FUNCTIONS -----
def parse_cfps_times(notam_text: str):
    # Look for B) start and C) end
    start_match = re.search(r"B\)\s*(\d+|PERM)", notam_text)
    end_match = re.search(r"C\)\s*(\d+|PERM)", notam_text)
    if start_match:
        start_raw = start_match.group(1)
        if start_raw == "PERM":
            start = "PERM"
        else:
            start = datetime.strptime(start_raw, "%y%m%d%H%M").strftime("%b %d %Y, %H:%M UTC")
    else:
        start = "N/A"

    if end_match:
        end_raw = end_match.group(1)
        if end_raw == "PERM":
            end = "PERM"
        else:
            end = datetime.strptime(end_raw, "%y%m%d%H%M").strftime("%b %d %Y, %H:%M UTC")
    else:
        end = "PERM" if start == "PERM" else "N/A"

    return start, end

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
            try:
                notam_json = json.loads(n["text"])
                raw_text = notam_json.get("raw", "")
            except:
                raw_text = n["text"]
            start, end = parse_cfps_times(raw_text)
            notams.append({"text": raw_text, "start": start, "end": end})
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
        "pageSize": 50
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    items = data.get("items", [])
    notams = []

    for feature in items:
        props = feature.get("properties", {})
        core = props.get("coreNOTAMData", {})
        notam_data = core.get("notam", {})

        # Extract main text
        notam_text = notam_data.get("text", "")

        # Prefer simpleText translation
        translations = core.get("notamTranslation", [])
        simple_text = None
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                simple_text = t.get("simpleText")

        clean_entry = f"{notam_data.get('number', '')} | {notam_data.get('classification', '')}\n"
        clean_entry += simple_text or notam_text

        # Extract effective and expiry times
        start_raw = notam_data.get("effectiveStart")
        end_raw = notam_data.get("effectiveEnd")
        start = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).strftime("%b %d %Y, %H:%M UTC") if start_raw else "PERM"
        end = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).strftime("%b %d %Y, %H:%M UTC") if end_raw else "PERM"

        notams.append({"text": clean_entry.strip(), "start": start, "end": end})
    return notams

def highlight_keywords(notam_text: str):
    for kw in KEYWORDS:
        notam_text = notam_text.replace(kw, f"<span style='color:red;font-weight:bold'>{kw}</span>")
    return notam_text

def format_notam_card(notam):
    # Determine PERM label
    perm_label = ""
    if notam["start"] == "PERM" or notam["end"] == "PERM":
        perm_label = "<span style='background-color:yellow;font-weight:bold;padding:2px 4px;margin-right:5px'>PERM</span>"

    return f"""
    <div style='border:1px solid #ccc; padding:10px; margin-bottom:10px; border-radius:5px; background-color:#f9f9f9; font-family:Arial, sans-serif; font-size:14px'>
        {perm_label}<span style='font-weight:bold'>{highlight_keywords(notam["text"])}</span>
        <table style='margin-top:5px; font-size:12px'>
            <tr><td><b>Effective:</b></td><td>{notam["start"]}</td></tr>
            <tr><td><b>Expires:</b></td><td>{notam["end"]}</td></tr>
        </table>
    </div>
    """

# ----- USER INPUT -----
icao_input = st.text_input("Enter ICAO codes (comma-separated, e.g., CYYC,KTEB):").upper().strip()
uploaded_file = st.file_uploader("Or upload an Excel/CSV with ICAO codes (column named 'ICAO')", type=["xlsx", "csv"])

icao_list = []

if icao_input:
    icao_list.extend([x.strip() for x in icao_input.split(",") if x.strip()])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        if "ICAO" in df.columns:
            icao_list.extend(df["ICAO"].dropna().str.upper().tolist())
        else:
            st.error("Uploaded file must have a column named 'ICAO'")
    except Exception as e:
        st.error(f"Error reading file: {e}")

# ----- FETCH & DISPLAY -----
if icao_list:
    st.write(f"Fetching NOTAMs for {len(icao_list)} airport(s)...")
    cfps_results = []
    faa_results = []

    for icao in icao_list:
        try:
            if icao.startswith("C"):
                notams = get_cfps_notams(icao)
                cfps_results.append({"ICAO": icao, "NOTAMS": notams})
            else:
                notams = get_faa_notams(icao)
                faa_results.append({"ICAO": icao, "NOTAMS": notams})
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Canadian Airports (CFPS)")
        for r in cfps_results:
            with st.expander(r["ICAO"], expanded=False):
                for notam in r["NOTAMS"]:
                    st.markdown(format_notam_card(notam), unsafe_allow_html=True)

    with col2:
        st.subheader("US Airports (FAA)")
        for r in faa_results:
            with st.expander(r["ICAO"], expanded=False):
                for notam in r["NOTAMS"]:
                    st.markdown(format_notam_card(notam), unsafe_allow_html=True)

    # ----- DOWNLOAD -----
    df_all = []
    for r in cfps_results + faa_results:
        for n in r["NOTAMS"]:
            df_all.append({"ICAO": r["ICAO"], "NOTAM": n["text"], "Effective": n["start"], "Expires": n["end"]})

    towrite = BytesIO()
    pd.DataFrame(df_all).to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button(
        label="Download All NOTAMs as Excel",
        data=towrite,
        file_name="notams.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
