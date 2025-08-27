import streamlit as st
import pandas as pd
import requests
import json
from io import BytesIO

st.set_page_config(page_title="CFPS Weather & NOTAM Viewer", layout="wide")
st.title("CFPS Weather & NOTAM Viewer")

# --------------------------
# Keywords to highlight/flag
# --------------------------
KEYWORDS = ["CLOSED", "CLSD"]

# --------------------------
# Function to fetch CFPS data
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
# Function to highlight keywords in text
# --------------------------
def highlight_text(text: str, keywords=KEYWORDS) -> str:
    for kw in keywords:
        text = text.replace(kw, f"<span style='color:red; font-weight:bold;'>{kw}</span>")
    return text

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

                # Check for keywords
                if any(kw in raw_text for kw in KEYWORDS):
                    notam_flagged = True
                highlighted_text = highlight_text(raw_text)
                notams.append(highlighted_text)

            notam_text = "\n\n".join(notams)

            results.append({
                "ICAO": icao,
                "METAR": metar,
                "TAF": taf,
                "NOTAMs": notam_text,
                "flagged": notam_flagged
            })
        except Exception as e:
            st.warning(f"Failed to fetch data for {icao}: {e}")

    # Display each ICAO nicely with collapsible header
    st.subheader("CFPS Data")
    for r in results:
        if r["flagged"]:
            header_style = f"<span style='color:red; font-weight:bold'>{r['ICAO']}</span>"
        else:
            header_style = r["ICAO"]

        with st.expander(header_style, expanded=True):
            st.markdown("**METAR:**")
            st.code(r["METAR"] or "No METAR available", language="text")
            st.markdown("**TAF:**")
            st.code(r["TAF"] or "No TAF available", language="text")
            st.markdown("**NOTAMs:**")
            # Split NOTAMs by double newlines and put each in its own sub-expander
            for i, nt in enumerate(r["NOTAMs"].split("\n\n")):
                with st.expander(f"NOTAM {i+1}"):
                    st.markdown(nt, unsafe_allow_html=True)

    # Allow download as Excel
    df_results = pd.DataFrame(results)
    towrite = BytesIO()
    df_results.to_excel(towrite, index=False, engine="openpyxl")
    towrite.seek(0)
    st.download_button(
        label="Download All Results as Excel",
        data=towrite,
        file_name="cfps_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
