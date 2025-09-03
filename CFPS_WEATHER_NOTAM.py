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
KEYWORDS = ["CLOSED", "CLSD"]  # Add any more keywords here
HIDE_KEYWORDS = ["crane", "RUSSIAN", "CONGO"]  # Add words you want to hide

st.set_page_config(page_title="CFPS/FAA NOTAM Viewer", layout="wide")
st.title("CFPS & FAA NOTAM Viewer")

# ----- FUNCTIONS -----
def highlight_keywords(notam_text: str):
    for kw in KEYWORDS:
        notam_text = notam_text.replace(kw, f"<span style='color:red;font-weight:bold'>{kw}</span>")
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
                "sortKey": sort_key
            })

    notams.sort(key=lambda x: x["sortKey"], reverse=True)
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

        # Extract text
        notam_text = notam_data.get("text", "")
        translations = core.get("notamTranslation", [])
        simple_text = None
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                simple_text = t.get("simpleText")
        text_to_use = simple_text if simple_text else notam_text

        if any(hide_kw.lower() in text_to_use.lower() for hide_kw in HIDE_KEYWORDS):
            continue

        effective = notam_data.get("effectiveStart", None)
        expiry = notam_data.get("effectiveEnd", None)

        start_dt = end_dt = None

        # Handle effective
        if effective == "PERM":
            effective_display = "PERM"
        elif effective:
            start_dt = datetime.fromisoformat(effective.replace("Z", ""))
            effective_display = start_dt.strftime("%b %d %Y, %H:%M")
        else:
            effective_display = "N/A"

        # Handle expiry
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
            "sortKey": start_dt if start_dt else datetime.min
        })

    notams.sort(key=lambda x: x["sortKey"], reverse=True)
    return notams

def format_notam_card(notam):
    highlighted_text = highlight_keywords(notam["text"])

    # Calculate duration
    if notam["start_dt"] and notam["end_dt"]:
        delta = notam["end_dt"] - notam["start_dt"]
        hours, remainder = divmod(delta.total_seconds(), 3600)
        minutes = remainder // 60
        duration_str = f"{int(hours)}h{int(minutes):02d}m"
    else:
        duration_str = "N/A"

    # Calculate time remaining
    now = datetime.utcnow()
    if notam["end_dt"]:
        remaining_delta = notam["end_dt"] - now
        if remaining_delta.total_seconds() > 0:
            rem_hours, rem_remainder = divmod(remaining_delta.total_seconds(), 3600)
            rem_minutes = rem_remainder // 60
            remaining_str = f"(in {int(rem_hours)}h{int(rem_minutes):02d}m)"
        else:
            remaining_str = "(expired)"
    else:
        remaining_str = ""

    card_html = f"""
    <div style='border:1px solid #ccc; padding:10px; margin-bottom:8px; background-color:#111; color:#eee; border-radius:5px;'>
        <p style='margin:0; font-family:monospace; white-space:pre-wrap;'>{highlighted_text}</p>
        <table style='margin-top:5px; font-size:0.9em; color:#aaa; width:100%;'>
            <tr><td><strong>Effective:</strong></td><td>{notam['effectiveStart']}</td><td>{remaining_str}</td></tr>
            <tr><td><strong>Expires:</strong></td><td>{notam['effectiveEnd']}</td></tr>
            <tr><td><strong>Duration:</strong></td><td>{duration_str}</td></tr>
        </table>
    </div>
    """
    return card_html

# ----- USER INPUT -----
icao_input = st.text_input(
    "Enter ICAO code(s) separated by commas (e.g., CYYC, KTEB):"
).upper().strip()
uploaded_file = st.file_uploader(
    "Or upload an Excel/CSV with ICAO codes (column named 'ICAO')", type=["xlsx", "csv"]
)

icao_list = []

if icao_input:
    icao_list.extend([code.strip() for code in icao_input.split(",") if code.strip()])

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
    cfps_list = []
    faa_list = []

    for icao in icao_list:
        try:
            if icao.startswith("C"):
                notams = get_cfps_notams(icao)
                cfps_list.append({"ICAO": icao, "notams": notams})
            else:
                notams = get_faa_notams(icao)
                faa_list.append({"ICAO": icao, "notams": notams})
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Canadian Airports (CFPS)")
        for airport in cfps_list:
            with st.expander(airport["ICAO"], expanded=False):
                for notam in airport["notams"]:
                    st.markdown(format_notam_card(notam), unsafe_allow_html=True)

    with col2:
        st.subheader("US Airports (FAA)")
        for airport in faa_list:
            with st.expander(airport["ICAO"], expanded=False):
                for notam in airport["notams"]:
                    st.markdown(format_notam_card(notam), unsafe_allow_html=True)

    # Download Excel
    all_results = []
    for airport in cfps_list + faa_list:
        for notam in airport["notams"]:
            all_results.append({
                "ICAO": airport["ICAO"],
                "NOTAM": notam["text"],
                "Effective": notam["effectiveStart"],
                "Expires": notam["effectiveEnd"]
            })

    df_results = pd.DataFrame(all_results)
    towrite = BytesIO()
    df_results.to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button(
        label="Download All NOTAMs as Excel",
        data=towrite,
        file_name="notams.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

