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

# --- PAGE CONFIG ---
st.set_page_config(page_title="Live Wire Precision Pro", layout="centered")

# --- CUSTOM ROAD AESTHETIC ---
st.markdown("""
    <style>
    .stApp { background-color: #2F2F2F; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; text-transform: uppercase; letter-spacing: 2px; }
    div.stButton > button:first-child { 
        background-color: #444444; color: #FFD700; border: 2px solid #FFD700; border-radius: 10px; 
    }
    /* CUSTOM LOADING BAR - CAUTION YELLOW */
    .stProgress > div > div > div > div { background-color: #FFD700 !important; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 High-Strength Collector")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "field_backup_precision.json"

# --- AUTO-SAVE ---
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
# TAB 1: VAULT (STRENGTHENED GRAB)
# ==========================================
with tab1:
    if not st.session_state.optimized_route:
        st.subheader("Load Map Files")
        uploaded_files = st.file_uploader("Select .est Maps", type=["est", "txt"], accept_multiple_files=True)
        
        if uploaded_files:
            file_configs = []
            for i, f in enumerate(uploaded_files):
                label = st.text_input(f"Sheet Label for {f.name}:", value=f"Day {i+1}", key=f"label_in_{i}")
                file_configs.append({"file": f, "label": label})
            
            if st.button("🚀 Process & Merge Maps", use_container_width=True):
                all_raw_sites = []
                active_labels = []
                
                # Visual Loading Feedback
                status_box = st.empty()
                bar = st.progress(0)
                
                for idx, config in enumerate(file_configs):
                    status_box.markdown(f"**Grabbing data from:** `{config['file'].name}`...")
                    active_labels.append(config['label'])
                    
                    try:
                        # Stream the file to avoid memory lag
                        raw_bytes = config['file'].getvalue()
                        # Decode with latin-1 to handle binary Microsoft characters safely
                        content = raw_bytes.decode('latin-1', errors='ignore')
                        
                        # Aggressive Regex: specifically targets the coordinate/ID strings
                        matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', content)
                        
                        file_count = 0
                        for m in matches:
                            if m[0] == "3333": continue
                            all_raw_sites.append({
                                "id": str(m[0]), "lat": float(m[2]), "lon": float(m[3]), "sheet": config['label']
                            })
                            file_count += 1
                        
                        st.write(f"✅ {config['label']} loaded: {file_count} sites found.")
                    except Exception as e:
                        st.error(f"Error in {config['file'].name}")
                    
                    # Update Loading Bar
                    bar.progress((idx + 1) / len(file_configs))
                
                if all_raw_sites:
                    status_box.markdown("**Calculating Master Efficiency Path...**")
                    df = pd.DataFrame(all_raw_sites).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: calculate_distance(curr, (x['lat'], x['lon'])))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    
                    st.session_state.optimized_route = route
                    st.session_state.active_files = active_labels
                    for s in route:
                        st.session_state.site_data[s['id']] = {
                            "Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n",
                            "Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],
                            "Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":None,"INSTALL_LON":None
                        }
                    save_state()
                    status_box.success("🎯 Route Optimized! Switch to INSTALL tab.")
                    time.sleep(1)
                    st.rerun()
    else:
        st.success(f"Merged Route: {len(st.session_state.optimized_route)} Stops Total")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        if st.button("🗑️ Reset Application", use_container_width=True):
            st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# INSTALL, PICK-UP, AND EXCEL TABS REMAIN STABLE
# ==========================================
# (Code follows the previously established Focus/List and GPS capture logic)
