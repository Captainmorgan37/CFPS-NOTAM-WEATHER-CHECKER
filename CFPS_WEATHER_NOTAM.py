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

# ----- RUNWAY DATA (OurAirports) -----
@st.cache_data
def load_runway_data():
    url = "https://ourairports.com/data/runways.csv"
    df = pd.read_csv(url)
    return df

runways_df = load_runway_data()

def get_runway_info(icao_code):
    rows = runways_df[runways_df["airport_ident"] == icao_code]
    runway_list = []
    for _, row in rows.iterrows():
        le = str(row['le_ident']) if pd.notna(row['le_ident']) else ''
        he = str(row['he_ident']) if pd.notna(row['he_ident']) else ''
        if le or he:
            identifiers = f"{le}/{he}" if le and he else le or he
            length_ft = int(row['length_ft']) if pd.notna(row['length_ft']) else 'N/A'
            runway_list.append(f"{identifiers} – {length_ft:,} ft")
    return runway_list

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

# ... (keep your existing get_cfps_notams, get_faa_notams, format_notam_card functions as-is) ...

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

        # Define allowed column names
        valid_columns = ["ICAO", "From (ICAO)", "To (ICAO)"]

        found_codes = []
        for col in valid_columns:
            if col in df.columns:
                found_codes.extend(df[col].dropna().astype(str).str.upper().tolist())

        if found_codes:
            # Deduplicate while preserving order
            unique_codes = list(dict.fromkeys(found_codes))
            icao_list.extend(unique_codes)
        else:
            st.error("Uploaded file must have a column named 'ICAO', 'From (ICAO)', or 'To (ICAO)'")
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

    # Filter input
    filter_input = st.text_input("Filter NOTAMs by keywords (comma-separated):").strip().lower()
    filter_terms = [t.strip() for t in filter_input.split(",") if t.strip()]

    def matches_filter(text: str):
        if not filter_terms:
            return True
        return any(term in text.lower() for term in filter_terms)

    def highlight_search_terms(notam_text: str):
        """Highlight user-entered search terms in yellow."""
        highlighted = notam_text
        for term in filter_terms:
            highlighted = re.sub(
                f"({re.escape(term)})",
                r"<span style='background-color:rgba(255, 255, 0, 0.3); font-weight:bold'>\1</span>",
                highlighted,
                flags=re.IGNORECASE,
            )
        return highlighted

    # --- Display CFPS ---
    with col1:
        st.subheader("Canadian Airports (CFPS)")
        for airport in cfps_list:
            with st.expander(airport["ICAO"], expanded=False):
                # Show runways first
                runways = get_runway_info(airport["ICAO"])
                if runways:
                    st.markdown("**Runways:**")
                    for rwy in runways:
                        st.markdown(f"• {rwy}")
                else:
                    st.markdown("_No runway data available_")

                # Show NOTAMs
                for notam in airport["notams"]:
                    if matches_filter(notam["text"]):
                        notam_copy = notam.copy()
                        notam_copy["text"] = highlight_search_terms(notam_copy["text"])
                        st.markdown(format_notam_card(notam_copy), unsafe_allow_html=True)

    # --- Display FAA ---
    with col2:
        st.subheader("US Airports (FAA)")
        for airport in faa_list:
            with st.expander(airport["ICAO"], expanded=False):
                runways = get_runway_info(airport["ICAO"])
                if runways:
                    st.markdown("**Runways:**")
                    for rwy in runways:
                        st.markdown(f"• {rwy}")
                else:
                    st.markdown("_No runway data available_")

                for notam in airport["notams"]:
                    if matches_filter(notam["text"]):
                        notam_copy = notam.copy()
                        notam_copy["text"] = highlight_search_terms(notam_copy["text"])
                        st.markdown(format_notam_card(notam_copy), unsafe_allow_html=True)

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
