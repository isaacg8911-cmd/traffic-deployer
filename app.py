import streamlit as st
import re
import pandas as pd
import math
import time
import json
import os
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_js_eval import streamlit_js_eval

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="Live Wire Precision Pro", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #2F2F2F; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; text-transform: uppercase; letter-spacing: 2px; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    div.stButton > button:first-child { background-color: #444444; color: #FFD700; border: 2px solid #FFD700; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 Precision Field Collector")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "field_backup_precision.json"

# --- CORE LOGIC ---
def save_state():
    backup_data = {
        "active_files": st.session_state.active_files,
        "optimized_route": st.session_state.optimized_route,
        "site_data": st.session_state.site_data,
        "current_index": st.session_state.current_index
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup_data, f)

def load_state():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                backup_data = json.load(f)
                st.session_state.active_files = backup_data.get("active_files", [])
                st.session_state.optimized_route = backup_data.get("optimized_route", [])
                st.session_state.site_data = backup_data.get("site_data", {})
                st.session_state.current_index = backup_data.get("current_index", 0)
                return True
        except: return False
    return False

if "initialized" not in st.session_state:
    if not load_state():
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
    st.session_state.initialized = True

def get_california_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- NAVIGATION ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 VAULT", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

# ==========================================
# TAB 1: FAIL-SAFE MULTI-FILE VAULT
# ==========================================
with tab1:
    st.subheader("Load Work Orders")
    
    # Check if we already have a route; if not, show uploader
    if not st.session_state.optimized_route:
        uploaded_files = st.file_uploader("Upload .est Maps", type=["est", "txt"], accept_multiple_files=True)
        
        if uploaded_files:
            file_configs = []
            for i, f in enumerate(uploaded_files):
                # Use a cleaner key to prevent Streamlit widget conflicts
                label = st.text_input(f"Sheet Label for {f.name}:", value=f"Day {i+1}", key=f"file_label_input_{i}")
                file_configs.append({"file": f, "label": label})
            
            if st.button("🚀 Calculate Efficiency Route", use_container_width=True):
                all_raw = []
                active_labels = []
                
                with st.spinner("Processing maps..."):
                    for config in file_configs:
                        lbl = config["label"]
                        active_labels.append(lbl)
                        
                        try:
                            # Robust reading: Try to decode but ignore errors
                            raw_bytes = config["file"].read()
                            readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_bytes])
                            
                            matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', readable_text)
                            
                            found_in_file = 0
                            for m in matches:
                                if m[0] == "3333": continue
                                all_raw.append({
                                    "id": str(m[0]), 
                                    "lat": float(m[2]), 
                                    "lon": float(m[3]), 
                                    "sheet": lbl
                                })
                                found_in_file += 1
                            st.write(f"✅ Found {found_in_file} sites in {config['file'].name}")
                            
                        except Exception as e:
                            st.error(f"Error reading {config['file'].name}: {e}")

                if all_raw:
                    # Merge Logic
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: calculate_distance(curr, (x['lat'], x['lon'])))
                        route.append(nxt)
                        curr = (nxt['lat'], nxt['lon'])
                        rem.remove(nxt)
                    
                    # Update Session
                    st.session_state.optimized_route = route
                    st.session_state.active_files = active_labels
                    
                    # Clear and rebuild site data
                    st.session_state.site_data = {}
                    for s in route:
                        st.session_state.site_data[s['id']] = {
                            "Date":"", "Time":"", "Site":s['id'], "Counter":"c1b", 
                            "Serial":"", "Directions":"n", "Lanes":1, "Notes":"", 
                            "Installed":"", "Picked up":"", "LAT":s['lat'], 
                            "LON":s['lon'], "Skipped":False, "Sheet":s['sheet'],
                            "INSTALL_LAT":None, "INSTALL_LON":None
                        }
                    
                    save_state()
                    st.success("Master Route Solved! Head to the INSTALL tab.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("No sites found. Check file format.")
    else:
        st.success(f"Route Active with {len(st.session_state.optimized_route)} stops.")
        st.map(pd.DataFrame(st.session_state.optimized_route))
        if st.button("🗑️ Reset Application"):
            st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# TAB 2: INSTALL (AUTO-ADVANCE)
# ==========================================
with tab2:
    if not st.session_state.optimized_route: 
        st.info("Please load maps in the Vault first.")
    else:
        view = st.radio("Display Mode:", ["🎯 Focus", "📜 List"], horizontal=True)
        loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_CHECK_VAL')
        
        def render_form(sid, site_coords, index):
            s_data = st.session_state.site_data.get(sid, {})
            st.markdown(f"### Site {sid} ({s_data.get('Sheet', 'N/A')})")
            st.link_button("🚗 Start GPS", f"https://www.google.com/maps/dir/?api=1&destination={site_coords[0]},{site_coords[1]}", use_container_width=True)
            
            with st.form(key=f"precision_form_{sid}"):
                c1, c2 = st.columns(2)
                with c1: 
                    d_opt = ["n","e","s","w"]
                    curr_d = s_data.get("Directions", "n")
                    direction = st.selectbox("Direction", d_opt, index=d_opt.index(curr_d))
                with c2: 
                    lanes = st.number_input("Lanes", min_value=1, value=int(s_data.get("Lanes", 1)))
                
                serial = st.text_input("Serial Number", value=s_data.get("Serial", ""))
                notes = st.text_input("Notes", value=s_data.get("Notes", ""))
                
                b1, b2 = st.columns(2)
                if b1.form_submit_button("✅ COMPLETE", use_container_width=True):
                    t, d = get_california_time()
                    lat_cap, lon_cap = site_coords
                    if loc: 
                        coords = json.loads(loc)
                        lat_cap, lon_cap = coords[0], coords[1]
                    st.session_state.site_data[sid].update({
                        "Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e",
                        "Serial":serial,"Lanes":lanes,"Notes":notes,"Installed":"x",
                        "INSTALL_LAT":lat_cap,"INSTALL_LON":lon_cap
                    })
                    if view == "🎯 Focus": st.session_state.current_index += 1
                    save_state(); st.rerun()
                
                if b2.form_submit_button("🚨 UNABLE", use_container_width=True):
                    t, d = get_california_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Notes":f"SKIPPED: {notes.upper()}","Skipped":True})
                    if view == "🎯 Focus": st.session_state.current_index += 1
                    save_state(); st.rerun()

        if view == "🎯 Focus":
            idx = st.session_state.current_index
            if idx < len(st.session_state.optimized_route):
                s = st.session_state.optimized_route[idx]
                st.subheader(f"Stop #{idx+1} of {len(st.session_state.optimized_route)}")
                render_form(s['id'], (s['lat'], s['lon']), idx)
                if idx > 0 and st.button("⬅️ PREVIOUS"): st.session_state.current_index -= 1; st.rerun()
            else: st.success("🏁 All installations handled.")
        else:
            for i, s in enumerate(st.session_state.optimized_route):
                sd = st.session_state.site_data.get(s['id'], {})
                is_done = sd.get("Installed") == "x" or sd.get("Skipped")
                icon = "✅" if sd.get("Installed") == "x" else ("🚫" if sd.get("Skipped") else "📝")
                with st.expander(f"{icon} #{i+1} - SITE {s['id']}"):
                    if not is_done: render_form(s['id'], (s['lat'], s['lon']), i)
                    else: st.write("Logged.")

# ==========================================
# TAB 3 & 4: PICK-UP & EXCEL (Remains same)
# ==========================================
# (Logic here is omitted for brevity but should remain the same as previous stable version)
