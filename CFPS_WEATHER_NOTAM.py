import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO

st.set_page_config(page_title="CFPS Weather & NOTAM Viewer", layout="wide")
st.title("CFPS Weather & NOTAM Viewer")

# --------------------------
# Function to fetch CFPS data
# --------------------------
def get_cfps_data(icao: str):
    url = "https://plan.navcanada.ca/weather/api/alpha/"
    params = {
        "site": icao,
        "alpha": ["sigmet", "airmet", "notam", "metar", "taf", "pirep", "upperwind", "space_weather"],
        "notam_choice": "default",
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

    organized = {}
    for item in data["data"]:
        typ = item["type"]
        if typ not in organized:
            organized[typ] = []
        organized[typ].append(item)
    return organized


# --------------------------
# Keyword highlighter
# --------------------------
def highlight_text(text: str, keyword: str = "CLOSED") -> str:
    """Highlight keyword in red inside NOTAM text."""
    return text.replace(keyword, f"<span style='color:red; font-weight:bold;'>{keyword}</span>")


# --------------------------
# User input
# --------------------------
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


# --------------------------
# Fetch and display data
# --------------------------
if icao_list:
    st.write(f"Fetching CFPS data for {len(icao_list)} airport(s)...")
    results = []

    for icao in icao_list:
        try:
            data = get_cfps_data(icao)
            metar = "\n".join([m["text"] for m in data.get("metar", [])])
            taf = "\n".join([t["text"] for t in data.get("taf", [])])

            notams = []
            notam_flagged = False
            for n in data.get("notam", []):
                try:
                    notam_json = json.loads(n["text"])
                    raw_text = notam_json.get("raw", "")
                except:
                    raw_text = n["text"]

                if "CLOSED" in raw_text:
                    notam_flagged = True
                notams.
