import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO

# ----- CONFIG -----
FAA_CLIENT_ID = st.secrets["FAA_CLIENT_ID"]
FAA_CLIENT_SECRET = st.secrets["FAA_CLIENT_SECRET"]
KEYWORDS = ["CLOSED", "CLSD"]  # Add any more keywords here

st.set_page_config(page_title="CFPS/FAA NOTAM Viewer", layout="wide")
st.title("CFPS & FAA NOTAM Viewer")

# ----- FUNCTIONS -----
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
                notams.append(notam_json.get("raw", ""))
            except:
                notams.append(n["text"])
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

        # Extract the main NOTAM text
        notam_text = notam_data.get("text", "")

        # Try to get the "simpleText" translation (nicer formatting)
        translations = core.get("notamTranslation", [])
        simple_text = None
        for t in translations:
            if t.get("type") == "LOCAL_FORMAT":
                simple_text = t.get("simpleText")

        # Build a clean string
        clean_entry = f"📌 {notam_data.get('number', '')} | {notam_data.get('classification', '')}\n"
        if simple_text:
            clean_entry += simple_text
        else:
            clean_entry += notam_text

        notams.append(clean_entry.strip())

    return notams



def highlight_keywords(notam_text: str):
    for kw in KEYWORDS:
        notam_text = notam_text.replace(kw, f"<span style='color:red;font-weight:bold'>{kw}</span>")
    return notam_text

# ----- USER INPUT -----
icao_input = st.text_input("Enter a single ICAO code (e.g., CYYC):").upper().strip()
uploaded_file = st.file_uploader("Or upload an Excel/CSV with ICAO codes (column named 'ICAO')", type=["xlsx", "csv"])

icao_list = []

if icao_input:
    icao_list.append(icao_input)

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
    results = []

    for icao in icao_list:
        try:
            if icao.startswith("C"):
                notams = get_cfps_notams(icao)
            else:
                notams = get_faa_notams(icao)
            
            combined_notams = "\n\n".join(notams) or "No NOTAMs available"
            highlighted_notams = highlight_keywords(combined_notams)

            # Check if any keywords are present for header coloring
            header_color = "red" if any(kw in combined_notams for kw in KEYWORDS) else "black"

            results.append({
                "ICAO": icao,
                "NOTAMs": combined_notams,
                "Highlighted": highlighted_notams,
                "HeaderColor": header_color
            })
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    # Display each ICAO nicely
    st.subheader("NOTAMs")
    for r in results:
        with st.expander(f"{r['ICAO']}", expanded=False):
            st.markdown(r["Highlighted"], unsafe_allow_html=True)

    # Allow download as Excel
    df_results = pd.DataFrame([{"ICAO": r["ICAO"], "NOTAMs": r["NOTAMs"]} for r in results])
    towrite = BytesIO()
    df_results.to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button(
        label="Download All NOTAMs as Excel",
        data=towrite,
        file_name="notams.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )




