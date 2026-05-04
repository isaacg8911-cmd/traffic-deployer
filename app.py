import streamlit as st
import re
import pandas as pd
import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Live Wire Field App", layout="centered")
st.title("🚦 Field Data Collector")

HOME_COORDS = (33.7715, -117.9431) 
HOME_ADDR = "13121 Yockey St, Garden Grove, CA 92844"

# --- SESSION STATES ---
if "optimized_route" not in st.session_state:
    st.session_state.optimized_route = []
if "site_data" not in st.session_state:
    st.session_state.site_data = {} 
if "active_file" not in st.session_state:
    st.session_state.active_file = None # Holds file in a "Vault" before processing

# --- HELPER FUNCTIONS ---
def get_california_time():
    """Gets current CA time and rounds UP to next hour in military format."""
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0:
        now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%m/%d/%Y")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- NAVIGATION TABS ---
tab1, tab2, tab3 = st.tabs(["📁 File Vault", "📍 Installation", "♻️ Pick-Up"])

# ==========================================
# TAB 1: FILE VAULT & PROCESSING
# ==========================================
with tab1:
    st.subheader("Map Management")
    
    # Show uploader only if no file is currently held in memory
    if not st.session_state.active_file:
        uploaded_file = st.file_uploader("Upload .est Map", type=["est", "txt"])
        if uploaded_file:
            # Save file to memory vault instantly
            st.session_state.active_file = {
                "name": uploaded_file.name,
                "data": uploaded_file.getvalue()
            }
            st.rerun()
            
    else:
        # File Management Interface
        st.success("File securely loaded into the Vault.")
        
        # 1. Rename Feature
        new_name = st.text_input("Edit File Name:", value=st.session_state.active_file["name"])
        if new_name != st.session_state.active_file["name"]:
             st.session_state.active_file["name"] = new_name
             
        col1, col2 = st.columns(2)
        
        with col1:
            # 2. Manual Processing Button + Loading Spinner
            if st.button("🚀 Calculate Route", use_container_width=True):
                with st.spinner("Analyzing map and calculating optimal route..."):
                    time.sleep(1) # Ensures the spinner renders smoothly on mobile
                    try:
                        raw_data = st.session_state.active_file["data"]
                        readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_data])
                        
                        site_pattern = r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)'
                        matches = re.findall(site_pattern, readable_text)
                        
                        if matches:
                            raw_sites = []
                            for m in matches:
                                sid = m[0]
                                if sid == "3333": # Block internal Microsoft glitch
                                    continue 
                                raw_sites.append({"id": sid, "lat": float(m[2]), "lon": float(m[3])})
                                
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
                            
                            for site in temp_route:
                                if site['id'] not in st.session_state.site_data:
                                    st.session_state.site_data[site['id']] = {
                                        "DATE": "", "TIME": "", "SITE": site['id'],
                                        "DIR": "N", "LANES": 1, "COUNTER": "C1B",
                                        "NOTES": "", "INSTALLED": "", "PICKED UP": "",
                                        "LAT": site['lat'], "LON": site['lon'] 
                                    }
                            st.success("✅ Route Ready! Switch to the 'Installation' tab.")
                        else:
                            st.error("No valid sites found in the file.")
                    except Exception as e:
                        st.error(f"Error processing file: {e}")

        with col2:
            # 3. Delete Feature
            if st.button("🗑️ Delete File", type="secondary", use_container_width=True):
                st.session_state.active_file = None
                st.session_state.optimized_route = []
                st.session_state.site_data = {}
                st.rerun()

# ==========================================
# TAB 2: INSTALLATION WORKFLOW
# ==========================================
with tab2:
    if not st.session_state.optimized_route:
        st.info("👈 Please load and process a map in the File Vault first.")
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
                            lanes = st.number_input("Lanes", min_value=0, step=1, value=int(s_data["LANES"]))
                        
                        notes = st.text_input("Install Notes", value=s_data["NOTES"])
                        
                        if st.form_submit_button("Save & Mark Installed"):
                            if lanes < 1:
                                st.error("⚠️ Error: Lanes must be 1 or greater.")
                            else:
                                mil_time, current_date = get_california_time()
                                clean_notes = notes.strip().upper()
                                
                                st.session_state.site_data[sid].update({
                                    "DATE": current_date,
                                    "TIME": mil_time,
                                    "DIR": direction,
                                    "LANES": lanes,
                                    "NOTES": clean_notes,
                                    "INSTALLED": "x"
                                })
                                st.rerun()
                else:
                    st.success(f"Installed at {s_data['TIME']} on {s_data['DATE']}.")
                    st.write(f"**Lanes:** {s_data['LANES']} | **Dir:** {s_data['DIR']} | **Counter:** {s_data['COUNTER']}")

# ==========================================
# TAB 3: PICK-UP & EXPORT
# ==========================================
with tab3:
    installed_sites = [data for sid, data in st.session_state.site_data.items() if data["INSTALLED"] == "x"]
    
    if st.session_state.optimized_route:
        missing_sites = [s['id'] for s in st.session_state.optimized_route if st.session_state.site_data[s['id']]["INSTALLED"] != "x"]
        if missing_sites:
            st.error(f"🛑 SYSTEM AUDIT: {len(missing_sites)} sites not marked installed!")
            st.write(f"**Missing:** {', '.join(missing_sites)}")
        else:
            st.success("✅ SYSTEM AUDIT: 100% of sites from the map are accounted for.")
    
    if not installed_sites:
        st.info("No sites have been marked as installed yet.")
    else:
        st.subheader("Pick-Up Itinerary")
        for s_data in installed_sites:
            sid = s_data["SITE"]
            is_picked = s_data["PICKED UP"] == "x"
            
            icon = "✅" if is_picked else "📦"
            with st.expander(f"{icon} Pick Up: Site {sid}"):
                if not is_picked:
                    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={s_data['LAT']},{s_data['LON']}"
                    st.link_button("🚗 Drive to Pick-Up", maps_url)
                    
                    with st.form(key=f"pickup_form_{sid}"):
                        pickup_notes = st.text_input("Pick-Up Notes", value=s_data["NOTES"])
                        if st.form_submit_button("Mark Picked Up"):
                            st.session_state.site_data[sid]["PICKED UP"] = "x"
                            st.session_state.site_data[sid]["NOTES"] = pickup_notes.strip().upper()
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
