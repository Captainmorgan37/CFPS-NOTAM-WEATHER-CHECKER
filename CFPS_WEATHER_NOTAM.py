import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO
from datetime import datetime, timezone

# ----- CONFIG -----
FAA_CLIENT_ID = st.secrets["FAA_CLIENT_ID"]
FAA_CLIENT_SECRET = st.secrets["FAA_CLIENT_SECRET"]
KEYWORDS = ["CLOSED", "CLSD"]  # Add any more keywords here

st.set_page_config(page_title="CFPS/FAA NOTAM Viewer", layout="wide")
st.title("CFPS & FAA NOTAM Viewer")

# ----- STYLES -----
st.markdown("""
<style>
.notam-card {
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 15px;
    background-color: #f9f9f9;
}
.notam-text {
    font-size: 15px;
    line-height: 1.5;
    font-family: monospace;
    white-space: pre-wrap;
}
.notam-id {
    display: block;
    margin-top: 5px;
    font-size: 13px;
    color: #666;
    font-weight: bold;
}
.notam-timestamps {
    margin-top: 10px;
    font-size: 13px;
    color: #333;
}
.notam-timestamps td {
    padding-right: 10px;
}
.active {
    color: green;
    font-weight: bold;
}
.expired {
    color: red;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# ----- FUNCTIONS -----
def get_cfps_notams(icao: str):
    url = "https://plan.navcanada.ca/weather/api/alpha/"
    params = {"site": icao, "alpha": ["notam"], "notam_choice": "default", "_": "1756244240291"}
    query_params = [(k, v) for k, val in params.items() for v in (val if isinstance(val, list) else [val])]
    response = requests.get(url, params=query_params)
    response.raise_for_status()
    data = response.json()
    notams = []
    for n in data.get("data", []):
        if n.get("type") == "notam":
            try:
                notam_json = json.loads(n["text"])
                notams.append({
                    "text": notam_json.get("raw", ""),
                    "id": n.get("id", ""),
                    "effectiveStart": None,
                    "effectiveEnd": None
                })
            except:
                notams.append({"text": n["text"], "id": n.get("id", ""), "effectiveStart": None, "effectiveEnd": None})
    return notams

def get_faa_notams(icao: str):
    url = "https://external-api.faa.gov/notamapi/v1/notams"
    headers = {"client_id": FAA_CLIENT_ID, "client_secret": FAA_CLIENT_SECRET}
    params = {"icaoLocation": icao.upper(), "responseFormat": "geoJson", "pageSize": 50}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    items = data.get("items", [])
    notams = []
    for feature in items:
        props = feature.get("properties", {})
        core = props.get("coreNOTAMData", {})
        notam_data = core.get("notam", {})
        translations = core.get("notamTranslation", [])

        simple_text = None
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                simple_text = t.get("simpleText")

        notams.append({
            "text": simple_text or notam_data.get("text", ""),
            "id": notam_data.get("number", ""),
            "effectiveStart": notam_data.get("effectiveStart"),
            "effectiveEnd": notam_data.get("effectiveEnd")
        })
    return notams

def format_notam_card(notam):
    text = notam.get("text", "")
    for kw in KEYWORDS:
        text = text.replace(kw, f"<span style='color:red;font-weight:bold'>{kw}</span>")

    notam_id = notam.get("id", "")
    start = notam.get("effectiveStart")
    end = notam.get("effectiveEnd")

    status_html = ""
    if start and end:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            status = "Active" if start_dt <= now <= end_dt else "Expired"
            status_class = "active" if status == "Active" else "expired"

            status_html = f"""
            <table class="notam-timestamps">
            <tr><td>Effective</td><td>{start_dt.strftime('%b %d %Y, %I:%M %p UTC')}</td></tr>
            <tr><td>Expires</td><td>{end_dt.strftime('%b %d %Y, %I:%M %p UTC')}</td><td class="{status_class}">({status})</td></tr>
            </table>
            """
        except:
            pass

    return f"""
    <div class="notam-card">
        <div class="notam-text">{text}</div>
        <span class="notam-id">{notam_id}</span>
        {status_html}
    </div>
    """

# ----- INPUT -----
icao_input = st.text_input("Enter ICAO codes (comma separated, e.g., CYYC, CYVR, KJFK):").upper().strip()
uploaded_file = st.file_uploader("Or upload Excel/CSV with ICAO codes (column named 'ICAO')", type=["xlsx", "csv"])

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

icao_list = list(set(icao_list))

# ----- FETCH & DISPLAY -----
if icao_list:
    st.write(f"Fetching NOTAMs for {len(icao_list)} airport(s)...")
    canadian_results, faa_results = [], []

    for icao in icao_list:
        try:
            if icao.startswith("C"):
                notams = get_cfps_notams(icao)
                canadian_results.append((icao, notams))
            else:
                notams = get_faa_notams(icao)
                faa_results.append((icao, notams))
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🇨🇦 Canadian NOTAMs (CFPS)")
        for icao, notams in canadian_results:
            with st.expander(icao, expanded=False):
                for n in notams:
                    st.markdown(format_notam_card(n), unsafe_allow_html=True)

    with col2:
        st.subheader("🇺🇸 FAA NOTAMs")
        for icao, notams in faa_results:
            with st.expander(icao, expanded=False):
                for n in notams:
                    st.markdown(format_notam_card(n), unsafe_allow_html=True)
