import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Airport NOTAM & Weather Checker", layout="wide")

st.title("Airport NOTAM & Weather Checker")

# --- Upload Excel/CSV file with ICAO codes ---
uploaded_file = st.file_uploader("Upload Excel/CSV file with ICAO codes", type=["xlsx", "csv"])

# Highlight keywords in NOTAMs
def highlight_notams(text):
    keywords = ["CLOSED", "RESTRICTED", "INOPERATIVE", "OBSTRUCTION", "HAZARD", "RWY"]
    # Wrap keywords in HTML span with style
    def repl(match):
        return f'<span style="color:red; font-weight:bold;">{match.group(0)}</span>'
    pattern = re.compile("|".join(keywords), re.IGNORECASE)
    return pattern.sub(repl, text).replace("\n", "<br>")

if uploaded_file:
    # Read file
    if uploaded_file.name.endswith(".xlsx"):
        df_airports = pd.read_excel(uploaded_file)
    else:
        df_airports = pd.read_csv(uploaded_file)
    
    if "ICAO" not in df_airports.columns:
        st.error("Excel/CSV file must contain an 'ICAO' column.")
    else:
        # Simulate fetching data for each airport
        # Replace this with your real NOTAM/weather fetching
        results = []
        for icao in df_airports["ICAO"]:
            results.append({
                "ICAO": icao,
                "Airport Name": f"Sample Airport {icao}",
                "NOTAMs": f"RWY 27 CLOSED due to maintenance.\nTaxiway B RESTRICTED.\nObstruction near runway.",
                "Weather": f"METAR/TAF for {icao}: Wind 270@15kt, visibility 10km, clear skies."
            })
        df_results = pd.DataFrame(results)

        # --- Display nicely ---
        for i, row in df_results.iterrows():
            with st.expander(f"{row['ICAO']} - {row['Airport Name']}", expanded=True):
                st.markdown("**NOTAMs:**")
                st.markdown(
                    f'<div style="max-height:250px; overflow-y:auto; border:1px solid #ccc; padding:5px; background-color:#f9f9f9;">'
                    f'{highlight_notams(row["NOTAMs"])}'
                    f'</div>',
                    unsafe_allow_html=True
                )

                st.markdown("**Weather:**")
                st.markdown(
                    f'<div style="max-height:150px; overflow-y:auto; border:1px solid #ccc; padding:5px; background-color:#eef;">'
                    f'{row["Weather"].replace(chr(10), "<br>")}'
                    f'</div>',
                    unsafe_allow_html=True
                )
