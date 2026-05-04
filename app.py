import streamlit as st
import re
import pandas as pd
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Live Wire Field App", layout="centered")
st.title("🚦 Field Data Collector")

HOME_COORDS = (33.7715, -117.9431) 
HOME_ADDR = "13121 Yockey St, Garden Grove, CA 92844"

# Initialize Session States
if "optimized_route" not in st.session_state:
    st.session_state.optimized_route = []
if "site_data" not in st.session_state:
    st.session_state.site_data = {} 

# --- HELPER FUNCTIONS ---
def get_california_time():
    """Gets current CA time and rounds UP to the next hour in military format."""
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0:
        now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%m/%d/%Y")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- UI WORKFLOW ---
mode = st.radio("Select Workflow Phase:", ["📍 1. Installation", "♻️ 2. Pick-Up & Export"])

if mode == "📍 1. Installation":
    
    # 1. If we don't have a route yet, show the uploader
    if not st.session_state.optimized_route:
        uploaded_file = st.file_uploader("Upload .est Map to Start Day", type=["est", "txt"])

        if uploaded_file:
            try:
                raw_data = uploaded_file.read()
                readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_data])
                
                site_pattern = r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)'
                matches = re.findall(site_pattern, readable_text)
                
                if matches:
                    raw_sites = [{"id": m[0], "lat": float(m[2]), "lon": float(m[3])} for m in matches]
                    midpoint_data = pd.DataFrame(raw_sites).groupby("id").mean().reset_index()
                    
                    temp_route = []
                    current_pos = HOME_COORDS
                    remaining = midpoint_data.to_dict('records')
                    
                    while remaining:
                        next_stop = min(remaining, key=lambda x: calculate_distance(current_pos, (x['lat'], x['lon'])))
                        temp_route.append(next_stop)
                        current_pos = (next_stop['lat'], next_stop['lon'])
                        remaining.remove(next_stop)
                    
                    st.session_state.optimized_route = temp_route
                    
                    # Pre-fill empty data templates for each site
                    for site in temp_route:
                        if site['id'] not in st.session_state.site_data:
                            st.session_state.site_data[site['id']] = {
                                "DATE": "", "TIME": "", "SITE": site['id'],
                                "DIR": "N", "LANES": 1, "COUNTER": "C1B",
                                "NOTES": "", "INSTALLED": "", "PICKED UP": "",
                                "LAT": site['lat'], "LON": site['lon'] 
                            }
                    st.rerun() # Refresh to hide the upload button and show the route
                else:
                    st.error("No valid sites found in the file.")
            except Exception as e:
                st.error(f"Error processing file: {e}")

    # 2. If we DO have a route, show the dashboard (No upload button needed anymore)
    else:
        total = len(st.session_state.optimized_route)
        completed = sum(1 for data in st.session_state.site_data.values() if data["INSTALLED"] == "x")
        
        st.metric("Installation Progress",
