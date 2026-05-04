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
        
        st.metric("Installation Progress", f"{completed} / {total} Sites")
        st.progress(completed / total if total > 0 else 0)
        
        for i, site in enumerate(st.session_state.optimized_route):
            sid = site['id']
            s_data = st.session_state.site_data[sid]
            is_done = s_data["INSTALLED"] == "x"
            
            icon = "✅" if is_done else "📝"
            
            with st.expander(f"{icon} Stop {i+1}: Site {sid}"):
                if not is_done:
                    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={site['lat']},{site['lon']}"
                    st.link_button("🚗 Start Drive", maps_url)
                    
                    st.markdown("### Log Installation")
                    with st.form(key=f"install_form_{sid}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            direction = st.selectbox("Direction", ["N", "E", "S", "W"], index=0 if s_data["DIR"] == "N" else 1)
                        with col2:
                            lanes = st.number_input("Lanes", min_value=1, step=1, value=int(s_data["LANES"]))
                        
                        notes = st.text_input("Install Notes", value=s_data["NOTES"])
                        
                        if st.form_submit_button("Save & Mark Installed"):
                            mil_time, current_date = get_california_time()
                            
                            st.session_state.site_data[sid].update({
                                "DATE": current_date,
                                "TIME": mil_time,
                                "DIR": direction,
                                "LANES": lanes,
                                "NOTES": notes,
                                "INSTALLED": "x"
                            })
                            st.rerun()
                else:
                    st.success(f"Installed at {s_data['TIME']} on {s_data['DATE']}.")
                    st.write(f"**Lanes:** {s_data['LANES']} | **Dir:** {s_data['DIR']} | **Counter:** {s_data['COUNTER']}")

        st.divider()
        if st.button("Reset Day / Start Over"):
            st.session_state.optimized_route = []
            st.session_state.site_data = {}
            st.rerun()

elif mode == "♻️ 2. Pick-Up & Export":
    st.subheader("Pick-Up Itinerary")
    
    installed_sites = [data for sid, data in st.session_state.site_data.items() if data["INSTALLED"] == "x"]
    
    if not installed_sites:
        st.info("No sites have been marked as installed yet.")
    else:
        for s_data in installed_sites:
            sid = s_data["SITE"]
            is_picked = s_data["PICKED UP"] == "x"
            
            icon = "✅" if is_picked else "📦"
            with st.expander(f"{icon} Pick Up: Site {sid}"):
                if not is_picked:
                    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={s_data['LAT']},{s_data['LON']}"
                    st.link_button("🚗 Drive to Pick-Up", maps_url)
                    
                    with st.form(key=f"pickup_form_{sid}"):
                        pickup_notes = st.text_input("Pick-Up Notes", value=s_data["NOTES"], placeholder="Any damage or issues?")
                        if st.form_submit_button("Mark Picked Up"):
                            st.session_state.site_data[sid]["PICKED UP"] = "x"
                            st.session_state.site_data[sid]["NOTES"] = pickup_notes
                            st.rerun()
                else:
                    st.success("Equipment secured.")
                    st.write(f"Final Notes: {s_data['NOTES']}")
        
        st.divider()
        st.subheader("Export Excel Data")
        
        export_df = pd.DataFrame(installed_sites)
        export_df = export_df[["DATE", "TIME", "SITE", "DIR", "LANES", "COUNTER", "NOTES", "INSTALLED", "PICKED UP"]]
        
        csv_data = export_df.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📊 Download Final Data Sheet",
            data=csv_data,
            file_name=f"Traffic_Data_{datetime.now(ZoneInfo('America/Los_Angeles')).strftime('%Y_%m_%d')}.csv",
            mime="text/csv"
        )
