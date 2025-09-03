import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO

st.set_page_config(page_title="CFPS + FAA NOTAM Viewer", layout="wide")
st.title("CFPS + FAA NOTAM Viewer")

# =============================
# CONFIG - FAA API credentials
# =============================
FAA_CLIENT_ID = st.secrets.get("FAA_CLIENT_ID", "cd92bc1249d64f32a10f93c72412125e")
FAA_CLIENT_SECRET = st.secrets.get("FAA_CLIENT_SECRET", "6271aa0250394c98A84a0Be41c1943E0")

# --------------------------
# CFPS Data Fetcher
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
        organized.setdefault(typ, []).append(item)
    return organized

# --------------------------
# FAA NOTAM Fetcher
# --------------------------
def get_faa_notams(icao: str):
    url = "https://external-api.faa.gov/notamapi/v1/notams"
    headers = {
        "client_id": FAA_CLIENT_ID,
        "client_secret": FAA_CLIENT_SECRET
    }
    params = {"designators": icao}
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    notams = [n.get("all", "") for n in data.get("notamList", [])]
    return notams


# --------------------------
# User input
# --------------------------
icao_input = st.text_input("Enter a single ICAO code (e.g., CYYC or KTEB):").upper().strip()
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
            if icao.startswith("C"):
                data = get_cfps_data(icao)
                notams = [n["text"] for n in data.get("notam", [])]
            else:
                notams = get_faa_notams(icao)


            results.append({
                "ICAO": icao,
                "METAR": metar,
                "TAF": taf,
                "NOTAMs": "\n\n".join(notams)
            })
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    # Display each ICAO nicely
    st.subheader("Airport Data")
    for r in results:
        with st.expander(f"{r['ICAO']}"):
            if r["METAR"]:
                st.markdown("**METAR:**")
                st.code(r["METAR"], language="text")
            if r["TAF"]:
                st.markdown("**TAF:**")
                st.code(r["TAF"], language="text")
            st.markdown("**NOTAMs:**")
            st.text_area("NOTAMs", r["NOTAMs"] or "No NOTAMs available", height=300, key=f"notams_{r['ICAO']}")

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


