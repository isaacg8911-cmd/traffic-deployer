import streamlit as st
import re
import pandas as pd
import math
import time
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Live Wire Field App", layout="centered")
st.title("🚦 Field Data Collector")

HOME_COORDS = (33.7715, -117.9431) 
HOME_ADDR = "13121 Yockey St, Garden Grove, CA 92844"
BACKUP_FILE = "field_backup.json"

# --- AUTO-SAVE LOGIC ---
def save_state():
    backup_data = {
        "active_file_name": st.session_state.active_file_name,
        "optimized_route": st.session_state.optimized_route,
        "site_data": st.session_state.site_data
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup_data, f)

def load_state():
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            backup_data = json.load(f)
            st.session_state.active_file_name = backup_data.get("active_file_name", None)
            st.session_state.optimized_route = backup_data.get("optimized_route", [])
            st.session_state.site_data = backup_data.get("site_data", {})
            return True
    return False

# --- SESSION STATES ---
if "initialized" not in st.session_state:
    if not load_state():
        st.session_state.active_file_name = None
        st.session_state.optimized_route = []
        st.session_state.site_data = {} 
    st.session_state.initialized = True

def get_california_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0:
        now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- NAVIGATION TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 Vault", "📍 Install", "♻️ Pick-Up", "📊 Data"])

# ==========================================
# TAB 1: FILE VAULT & VISUAL GRID
# ==========================================
with tab1:
    st.subheader("Map Management")
    
    if not st.session_state.active_file_name:
        uploaded_file = st.file_uploader("Upload .est Map to begin", type=["est", "txt"])
        
        if uploaded_file:
            with st.spinner("Calculating route and generating visual grid..."):
                time.sleep(1) 
                try:
                    raw_data = uploaded_file.read()
                    readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_data])
                    site_pattern = r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)'
                    matches = re.findall(site_pattern, readable_text)
                    
                    if matches:
                        raw_sites = []
                        for m in matches:
                            sid = m[0]
                            if sid == "3333": continue 
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
                        st.session_state.active_file_name = uploaded_file.name
                        
                        for site in temp_route:
                            if site['id'] not in st.session_state.site_data:
                                st.session_state.site_data[site['id']] = {
                                    "Date": "", "Time": "", "Site": site['id'],
                                    "Counter": "c1b", "Serial": "", "Directions": "n", 
                                    "Lanes": 1, "Notes": "", "Installed": "", "Picked up": "",
                                    "LAT": site['lat'], "LON": site['lon'] 
                                }
                        save_state()
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            
    else:
        st.success(f"🔒 Active Map: {st.session_state.active_file_name}")
        
        # --- THE VISUAL GRID RENDER ---
        st.markdown("### 🗺️ Route Overview")
        map_df = pd.DataFrame(st.session_state.optimized_route)
        # Add Home Base to the visual for context
        home_df = pd.DataFrame([{"id": "HOME", "lat": HOME_COORDS[0], "lon": HOME_COORDS[1]}])
        full_map_view = pd.concat([home_df, map_df], ignore_index=True)
        
        st.map(full_map_view, zoom=9, use_container_width=True)
        
        st.info("The map above shows your optimized sequence starting from Garden Grove.")
        
        if st.button("🗑️ Delete Job & Start Fresh", type="primary", use_container_width=True):
            st.session_state.active_file_name = None
            st.session_state.optimized_route = []
            st.session_state.site_data = {}
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# TAB 2: INSTALLATION WORKFLOW
# ==========================================
with tab2:
    if not st.session_state.optimized_route:
        st.info("👈 Load a map in the Vault first.")
    else:
        total = len(st.session_state.optimized_route)
        completed = sum(1 for data in st.session_state.site_data.values() if data["Installed"] == "x")
        st.metric("Daily Progress", f"{completed} / {total} Sites")
        st.progress(completed / total if total > 0 else 0)
        
        for i, site in enumerate(st.session_state.optimized_route):
            sid = site['id']
            s_data = st.session_state.site_data[sid]
            is_done = s_data["Installed"] == "x"
            icon = "✅" if is_done else "📝"
            
            with st.expander(f"{icon} Stop {i+1}: Site {sid}"):
                if not is_done:
                    st.link_button("🚗 Start GPS", f"https://www.google.com/maps/dir/?api=1&destination={site['lat']},{site['lon']}")
                    with st.form(key=f"ins_{sid}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            direction = st.selectbox("Direction", ["n", "e", "s", "w"], index=["n", "e", "s", "w"].index(s_data["Directions"]))
                        with c2:
                            lanes = st.number_input("Lanes", min_value=0, step=1, value=int(s_data["Lanes"]))
                        serial = st.text_input("Serial Number", value=s_data["Serial"])
                        notes = st.text_input("Notes", value=s_data["Notes"])
                        if st.form_submit_button("Save & Mark Installed"):
                            if lanes < 1: st.error("Lanes required.")
                            else:
                                t, d = get_california_time()
                                st.session_state.site_data[sid].update({
                                    "Date": d, "Time": t, "Directions": "n" if direction in ["n", "s"] else "e", 
                                    "Serial": serial.strip(), "Lanes": lanes, "Notes": notes.strip(), "Installed": "x"
                                })
                                save_state(); st.rerun()
                else:
                    st.write(f"Done at {s_data['Time']} | Lanes: {s_data['Lanes']} | Dir: {s_data['Directions']}")
                    if st.button("✏️ Edit", key=f"ed_ins_{sid}"):
                        st.session_state.site_data[sid]["Installed"] = ""; save_state(); st.rerun()

# ==========================================
# TAB 3: PICK-UP
# ==========================================
with tab3:
    installed = [d for sid, d in st.session_state.site_data.items() if d["Installed"] == "x"]
    if not installed: st.info("No sites installed yet.")
    else:
        for s in installed:
            sid = s["Site"]; is_picked = s["Picked up"] == "x"
            icon = "✅" if is_picked else "📦"
            with st.expander(f"{icon} Pick Up: Site {sid}"):
                if not is_picked:
                    st.link_button("🚗 GPS", f"https://www.google.com/maps/dir/?api=1&destination={s['LAT']},{s['LON']}")
                    with st.form(key=f"pu_{sid}"):
                        p_notes = st.text_input("Notes", value=s["Notes"])
                        if st.form_submit_button("Mark Picked Up"):
                            st.session_state.site_data[sid]["Picked up"] = "x"
                            st.session_state.site_data[sid]["Notes"] = p_notes.strip()
                            save_state(); st.rerun()
                else:
                    st.write(f"Picked up. Notes: {s['Notes']}")
                    if st.button("✏️ Edit", key=f"ed_pu_{sid}"):
                        st.session_state.site_data[sid]["Picked up"] = ""; save_state(); st.rerun()

# ==========================================
# TAB 4: DATA SPREADSHEET
# ==========================================
with tab4:
    installed = [d for sid, d in st.session_state.site_data.items() if d["Installed"] == "x"]
    if not installed: st.info("Spreadsheet is empty.")
    else:
        export_df = pd.DataFrame(installed)[["Date", "Time", "Site", "Counter", "Serial", "Directions", "Lanes", "Notes", "Installed", "Picked up"]]
        st.dataframe(export_df, use_container_width=True)
        csv = export_df.to_csv(index=False).encode('utf-8')
        st.download_button("📊 Download .CSV", csv, f"Traffic_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", type="primary", use_container_width=True)
