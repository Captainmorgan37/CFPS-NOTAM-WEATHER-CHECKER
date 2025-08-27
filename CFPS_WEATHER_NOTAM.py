import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO

st.set_page_config(page_title="CFPS & FAA Weather/NOTAM Viewer", layout="wide")
st.title("CFPS & FAA Weather & NOTAM Viewer")

# --------------------------
# Function to fetch CFPS data (Canada)
# --------------------------
def get_cfps_data(icao: str):
    url = "https://plan.navcanada.ca/weather/api/alpha/"
    params = {
        "site": icao,
        "alpha": ["sigmet", "airmet", "notam", "metar", "taf", "pirep", "upperwind", "space_weather"],
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

    organized = {}
    for item in data["data"]:
        typ = item["type"]
        if typ not in organized:
            organized[typ] = []
        organized[typ].append(item)
    return organized

# --------------------------
# Function to fetch US NOTAMs (FAA via AviationWeather.gov)
# --------------------------
def get_us_notams(icao: str):
    url = f"https://aviationweather.gov/cgi-bin/json/NotamJSON.php?designators={icao}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()

    notams = []
    for n in data.get("notam", []):
        raw_text = n.get("all", "")
        if raw_text:
            notams.append(raw_text)
    return notams

# --------------------------
# User input
# --------------------------
icao_input = st.text_input("Enter a single ICAO code (e.g., CYYC or KJFK):").upper().strip()
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
    st.write(f"Fetching data for {len(icao_list)} airport(s)...")
    results = []

    for icao in icao_list:
        try:
            if icao.startswith("C"):  # Canadian airports
                data = get_cfps_data(icao)
                metar = "\n".join([m["text"] for m in data.get("metar", [])])
                taf = "\n".join([t["text"] for t in data.get("taf", [])])
                notams = []
                for n in data.get("notam", []):
                    try:
                        notam_json = json.loads(n["text"])
                        notams.append(notam_json.get("raw", ""))
                    except:
                        notams.append(n["text"])
                notam_text = "\n\n".join(notams)

            elif icao.startswith("K"):  # U.S. airports
                metar, taf = "", ""  # Could expand later with aviationweather.gov METAR/TAF API
                notams = get_us_notams(icao)
                notam_text = "\n\n".join(notams)

            else:  # Unsupported ICAO
                metar, taf, notam_text = "", "", "Unsupported ICAO prefix"

            results.append({
                "ICAO": icao,
                "METAR": metar,
                "TAF": taf,
                "NOTAMs": notam_text
            })

        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    # Display each ICAO nicely
    st.subheader("Airport Data")
    for r in results:
        with st.expander(f"{r['ICAO']}"):
            st.markdown("**METAR:**")
            st.code(r["METAR"] or "No METAR available", language="text")
            st.markdown("**TAF:**")
            st.code(r["TAF"] or "No TAF available", language="text")
            st.markdown("**NOTAMs:**")
            st.text_area("NOTAMs", r["NOTAMs"] or "No NOTAMs available", height=300)

    # Allow download as Excel
    df_results = pd.DataFrame(results)
    towrite = BytesIO()
    df_results.to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button(
        label="Download All Results as Excel",
        data=towrite,
        file_name="airport_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
