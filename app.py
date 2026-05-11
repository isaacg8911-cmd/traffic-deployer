import streamlit as st
import pandas as pd
import json
import re
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V51.34 Shielded", layout="centered")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

# --- THEME ---
st.markdown("""
    <style>
    .stApp { background-color: #0A0A0A; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; }
    div.stButton > button { 
        background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; 
        font-weight: bold; border-radius: 8px; height: 3.5em; width: 100%;
    }
    .stInfo { background-color: #111 !important; border: 1px solid #FFD700 !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# --- SESSION SAFETY GATE ---
if "init" not in st.session_state:
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    st.session_state.current_index = 0
    
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except: pass
    st.session_state.init = True

def auto_save():
    payload = {
        "optimized_route": st.session_state.optimized_route,
        "site_data": st.session_state.site_data,
        "current_index": st.session_state.current_index
    }
    with open(BACKUP_FILE, "w") as f: json.dump(payload, f)

def process_data(est_configs, excel_files):
    # 1. Clear previous state to prevent cross-contamination
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    
    excel_map = {}
    for f in excel_files:
        try:
            df = pd.read_csv(f, encoding='latin-1') if f.name.lower().endswith('.csv') else pd.read_excel(f)
            
            # Identify columns
            lat_c = next((c for c in df.columns if 'lat' in str(c).lower()), None)
            lon_c = next((c for c in df.columns if 'lon' in str(c).lower()), None)
            id_c = next((c for c in df.columns if any(x in str(c).lower() for x in ['site', 'tds', 'id'])), df.columns[0])
            
            if lat_c and lon_c:
                for _, row in df.iterrows():
                    sid = str(row[id_c]).split('.')[0].strip()
                    if sid.isdigit():
                        try:
                            v1, v2 = float(row[lat_c]), float(row[lon_c])
                            # CA Bounds Logic
                            lat = v1 if (32.0 < v1 < 36.0) else (v2 if (32.0 < v2 < 36.0) else v1)
                            lon = v2 if (-120.0 < v2 < -114.0) else (v1 if (-120.0 < v1 < -114.0) else v2)
                            excel_map[sid] = {"lat": lat, "lon": lon, "street": str(row.get('Street', f'Site {sid}'))}
                        except (ValueError, TypeError): continue
        except Exception as e: st.error(f"Excel Error: {e}")

    # 2. Match Map Site IDs to Excel GPS
    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_map.items():
            if sid in raw_map:
                uid = f"{cfg['label']}_{sid}".replace(" ", "_")
                final_raw.append({"id": sid, "uid": uid, "lat": data['lat'], "lon": data['lon'], "street": data['street']})
    
    if not final_raw:
        st.error("No overlap found between Excel site numbers and the Map file.")
        return

    # 3. Optimize Route
    curr = HOME_COORDS
    route, rem = [], list(final_raw)
    while rem:
        nxt = min(rem, key=lambda x: (curr[0]-x['lat'])**2 + (curr[1]-x['lon'])**2)
        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)

    # 4. Atomic Session Update
    new_site_data = {s['uid']: {**s, "Installed": False} for s in route}
    st.session_state.site_data = new_site_data
    st.session_state.optimized_route = route
    st.session_state.current_index = 0
    auto_save()
    st.rerun()

# --- UI LAYER ---
if not st.session_state.optimized_route:
    st.title("🚦 Live Wire: Direct Sync")
    ex = st.file_uploader("1️⃣ Excel Site List", accept_multiple_files=True)
    maps = st.file_uploader("2️⃣ Map Files (.EST)", accept_multiple_files=True)
    if ex and maps and st.button("🚀 SYNC SYSTEM"):
        configs = [{"file": f, "label": f"Day {i+1}"} for i, f in enumerate(maps)]
        process_data(configs, ex)
else:
    st.title("📁 Active Manifest")
    idx = st.session_state.current_index
    
    # Boundary and Key Protection
    if 0 <= idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        uid = active.get('uid', 'INVALID')
        
        # --- THE SHIELD: Check if both site and coords exist ---
        sd = st.session_state.site_data.get(uid)
        
        if sd and 'lat' in sd and 'lon' in sd:
            st.subheader(f"Stop {idx+1} of {len(st.session_state.optimized_route)}")
            st.info(f"**SITE {sd['id']}**\n\nStreet: {sd['street']}")
            
            nav_url = f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}"
            st.link_button("🚗 NAVIGATE TO SITE", nav_url, use_container_width=True)
            
            st.divider()
            
            if st.button("✅ MARK INSTALLED & NEXT", use_container_width=True):
                st.session_state.site_data[uid]['Installed'] = True
                st.session_state.current_index += 1
                auto_save(); st.rerun()
                
            if idx > 0:
                if st.button("⬅️ PREVIOUS STOP"):
                    st.session_state.current_index -= 1
                    auto_save(); st.rerun()
        else:
            st.error(f"Data gap detected for Stop {idx+1}. Skipping safely.")
            if st.button("Skip to Next"):
                st.session_state.current_index += 1
                st.rerun()
    else:
        st.success("🏁 All sites installed. Shift Complete!")

    if st.button("🗑️ CLEAR & RESET"):
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
        st.session_state.optimized_route = []
        st.session_state.site_data = {}
        st.session_state.current_index = 0
        st.rerun()
