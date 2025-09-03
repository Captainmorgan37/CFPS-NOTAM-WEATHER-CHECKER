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

# ----- FUNCTIONS -----
def get_cfps_notams(icao: str):
    url = "https://plan.navcanada.ca/weather/api/alpha/"
    params = {"site": icao, "alpha": ["notam"], "notam_choice": "default", "_": "1756244240291"}

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
                notams.append({
                    "id": notam_json.get("id", ""),
                    "text": notam_json.get("raw", n["text"]),
                    # Try multiple possible fields for start/end
                    "effectiveStart": notam_json.get("startTime") or notam_json.get("startDateTime"),
                    "effectiveEnd": notam_json.get("endTime") or notam_json.get("endDateTime")
                })
            except:
                notams.append({
                    "id": "",
                    "text": n["text"],
                    "effectiveStart": None,
                    "effectiveEnd": None
                })
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

        # Extract fields
        notam_id = notam_data.get("number", notam_data.get("id", ""))
        text = notam_data.get("text", "")
        effective_start = notam_data.get("effectiveStart")
        effective_end = notam_data.get("effectiveEnd")

        # Prefer "simpleText" if available
        translations = core.get("notamTranslation", [])
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                text = t.get("simpleText")

        notams.append({
            "id": notam_id,
            "text": text,
            "effectiveStart": effective_start,
            "effectiveEnd": effective_end
        })

    return notams

def highlight_keywords(notam_text: str):
    for kw in KEYWORDS:
        notam_text = notam_text.replace(
            kw, f"<span style='color:red;font-weight:bold'>{kw}</span>"
        )
    return notam_text

def format_notam_card(notam):
    # Convert times to datetime objects
    start_dt = (
        datetime.fromisoformat(notam["effectiveStart"].replace("Z", "+00:00"))
        if notam["effectiveStart"]
        else None
    )
    end_dt = (
        datetime.fromisoformat(notam["effectiveEnd"].replace("Z", "+00:00"))
        if notam["effectiveEnd"]
        else None
    )
    now = datetime.now(timezone.utc)

    # Status
    status = ""
    remaining = ""
    if start_dt and end_dt:
        if start_dt <= now <= end_dt:
            status = "Active"
            remaining_seconds = int((end_dt - now).total_seconds())
        elif now < start_dt:
            status = "Pending"
            remaining_seconds = int((start_dt - now).total_seconds())
        else:
            status = "Expired"
            remaining_seconds = 0
        hours = remaining_seconds // 3600
        minutes = (remaining_seconds % 3600) // 60
        remaining = f"({hours}h{minutes}m remaining)" if remaining_seconds > 0 else ""

    # Highlight keywords
    text_html = highlight_keywords(notam["text"])

    # Build HTML card
    html = f"""
    <div style="
        border:1px solid #ccc;
        border-radius:5px;
        padding:10px;
        margin-bottom:10px;
        background-color:#f9f9f9;
        font-family:Arial, sans-serif;
        color:#000;
    ">
        <p style="margin:0; font-weight:bold;">{notam['id']} - {status} {remaining}</p>
        <p style="margin:5px 0;">{text_html}</p>
        <p style="margin:0; font-size:0.8em; color:#555;">
            Effective: {start_dt.strftime('%b %d %Y, %I:%M %p %Z') if start_dt else 'N/A'} |
            Expires: {end_dt.strftime('%b %d %Y, %I:%M %p %Z') if end_dt else 'N/A'}
        </p>
    </div>
    """
    return html

# ----- USER INPUT -----
icao_input = st.text_area("Enter ICAO codes (comma or space separated, e.g., CYYC, KTEB):").upper().strip()
uploaded_file = st.file_uploader("Or upload an Excel/CSV with ICAO codes (column named 'ICAO')", type=["xlsx", "csv"])

icao_list = []

if icao_input:
    for val in icao_input.replace(",", " ").split():
        if val:
            icao_list.append(val.strip())

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
    results_cfps = []
    results_faa = []

    for icao in icao_list:
        try:
            if icao.startswith("C"):
                notams = get_cfps_notams(icao)
                results_cfps.append({"ICAO": icao, "NOTAMs": notams})
            else:
                notams = get_faa_notams(icao)
                results_faa.append({"ICAO": icao, "NOTAMs": notams})
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    # Two columns layout
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Canadian Airports (CFPS)")
        for r in results_cfps:
            with st.expander(r["ICAO"], expanded=False):
                for notam in r["NOTAMs"]:
                    st.markdown(format_notam_card(notam), unsafe_allow_html=True)

    with col2:
        st.subheader("US Airports (FAA)")
        for r in results_faa:
            with st.expander(r["ICAO"], expanded=False):
                for notam in r["NOTAMs"]:
                    st.markdown(format_notam_card(notam), unsafe_allow_html=True)

    # Allow download as Excel
    all_results = []
    for r in results_cfps + results_faa:
        for n in r["NOTAMs"]:
            all_results.append({
                "ICAO": r["ICAO"],
                "NOTAM ID": n["id"],
                "Text": n["text"],
                "Effective Start": n["effectiveStart"],
                "Effective End": n["effectiveEnd"]
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

