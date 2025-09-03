import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO
from datetime import datetime, timedelta

# ----- CONFIG -----
FAA_CLIENT_ID = st.secrets["FAA_CLIENT_ID"]
FAA_CLIENT_SECRET = st.secrets["FAA_CLIENT_SECRET"]
KEYWORDS = ["CLOSED", "CLSD"]        # Keywords to highlight
IGNORE_KEYWORDS = ["crane"]          # Keywords to hide from display

st.set_page_config(page_title="CFPS/FAA NOTAM Viewer", layout="wide")
st.title("CFPS & FAA NOTAM Viewer")

# ----- FUNCTIONS -----
def parse_cfps_times(notam_text):
    """
    Extract effective start and end times from CFPS NOTAM text.
    Format: B) YYMMDDHHMM C) YYMMDDHHMM or PERM
    """
    effective, expires = "N/A", "N/A"
    try:
        lines = notam_text.splitlines()
        for line in lines:
            if line.startswith("B)"):
                dt_str = line[2:].strip()
                effective = datetime.strptime(dt_str, "%y%m%d%H%M").strftime("%b %d %Y, %H:%M")
            if line.startswith("C)"):
                dt_str = line[2:].strip()
                if dt_str.upper() != "PERM":
                    expires = datetime.strptime(dt_str, "%y%m%d%H%M").strftime("%b %d %Y, %H:%M")
                else:
                    expires = "PERM"
    except:
        pass
    return effective, expires

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
                text = notam_json.get("raw", "")
            except:
                text = n["text"]
            # Apply ignore filter
            if not any(kw.lower() in text.lower() for kw in IGNORE_KEYWORDS):
                effective, expires = parse_cfps_times(text)
                notams.append({"text": text, "effective": effective, "expires": expires})
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
        notam_text = notam_data.get("text", "")
        translations = core.get("notamTranslation", [])
        simple_text = None
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                simple_text = t.get("simpleText")
        clean_text = simple_text if simple_text else notam_text

        # Apply ignore filter
        if any(kw.lower() in clean_text.lower() for kw in IGNORE_KEYWORDS):
            continue

        # Extract timestamps
        eff = notam_data.get("effectiveStart")
        exp = notam_data.get("effectiveEnd")
        effective = datetime.fromisoformat(eff.replace("Z", "+00:00")).strftime("%b %d %Y, %H:%M") if eff else "N/A"
        expires = datetime.fromisoformat(exp.replace("Z", "+00:00")).strftime("%b %d %Y, %H:%M") if exp else "N/A"

        # Build clean entry
        entry = {
            "text": f"📌 {notam_data.get('number', '')} | {notam_data.get('classification', '')}\n{clean_text}",
            "effective": effective,
            "expires": expires
        }
        notams.append(entry)
    return notams

def highlight_keywords(notam_text: str):
    for kw in KEYWORDS:
        notam_text = notam_text.replace(kw, f"<span style='color:red;font-weight:bold'>{kw}</span>")
    return notam_text

def format_notam_card(notam):
    return f"""
    <div class="notam-card" style="border:1px solid #999; padding:10px; margin-bottom:10px; border-radius:6px; background-color:#f7f7f7; font-family:Arial, sans-serif;">
        <p style="margin:0; white-space:pre-wrap;">{highlight_keywords(notam['text'])}</p>
        <p style="margin:2px 0; font-size:12px; color:#555;">
            Effective: {notam['effective']} | Expires: {notam['expires']}
        </p>
    </div>
    """

# ----- USER INPUT -----
icao_input = st.text_input("Enter ICAO code(s) separated by commas (e.g., CYYC,KTEB):").upper().strip()
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

    # Display in two columns
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Canadian Airports (CFPS)")
        for r in cfps_results:
            if r["NOTAMS"]:
                with st.expander(r["ICAO"], expanded=False):
                    for n in r["NOTAMS"]:
                        st.markdown(format_notam_card(n), unsafe_allow_html=True)
            else:
                st.write(f"{r['ICAO']}: No NOTAMs available")

    with col2:
        st.subheader("US Airports (FAA)")
        for r in faa_results:
            if r["NOTAMS"]:
                with st.expander(r["ICAO"], expanded=False):
                    for n in r["NOTAMS"]:
                        st.markdown(format_notam_card(n), unsafe_allow_html=True)
            else:
                st.write(f"{r['ICAO']}: No NOTAMs available")

    # Excel export
    export_rows = []
    for r in cfps_results + faa_results:
        for n in r["NOTAMS"]:
            export_rows.append({
                "ICAO": r["ICAO"],
                "NOTAM": n["text"],
                "Effective": n["effective"],
                "Expires": n["expires"]
            })

    if export_rows:
        df_export = pd.DataFrame(export_rows)
        towrite = BytesIO()
        df_export.to_excel(towrite, index=False, engine="openpyxl")
        towrite.seek(0)
        st.download_button(
            label="Download All NOTAMs as Excel",
            data=towrite,
            file_name="notams.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
