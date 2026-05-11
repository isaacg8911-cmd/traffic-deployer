import streamlit as st
import pandas as pd
import json
import re
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# --- CORE CONFIG ---
st.set_page_config(page_title="Live Wire V51.37 Direct-Flow", layout="centered")

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

# --- SESSION GATE ---
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
    payload = {"optimized_route": st.session_state.optimized_route, "site_data": st.session_state.site_data, "current_index": st.session_state.current_index}
    with open(BACKUP_FILE, "w") as f: json.dump(payload, f)

def process_data(est_configs, excel_files):
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    
    excel_map = {}
    for f in excel_files:
        try:
            df = pd.read_csv(f, encoding='latin-1') if f.name.lower().endswith('.csv') else pd.read_excel(f)
            lat_c = next((c for c in df.columns if 'lat' in str(c).lower()), None)
            lon_c = next((c for c in df.columns if 'lon' in str(c).lower()), None)
            id_c = next((c for c in df.columns if any(x in str(c).lower() for x in ['site', 'tds', 'id'])), df.columns[0])
            for _, row in df.iterrows():
                sid = str(row[id_c]).split('.')[0].strip()
                if sid.isdigit():
                    try:
                        v1, v2 = float(row[lat_c]), float(row[lon_c])
                        # CA Geofence Lock
                        lat = v1 if (32.0 < v1 < 36.0) else (v2 if (32.0 < v2 < 36.0) else v1)
                        lon = v2 if (-121.0 < v2 < -114.0) else (v1 if (-120.0 < v1 < -114.0) else v2)
                        excel_map[sid] = {"lat": lat, "lon": lon, "street": str(row.get('Street', f'Site {sid}'))}
                    except: continue
        except: pass

    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_map.items():
            if sid in raw_map:
                uid = f"{cfg['label']}_{sid}".replace(" ", "_")
                # V51.37: Direct Excel Anchoring (No Snapping)
                final_raw.append({"id": sid, "uid": uid, "lat": data['lat'], "lon": data['lon'], "street": data['street']})
    
    if final_raw:
        curr = HOME_COORDS
        route, rem = [], list(final_raw)
        while rem:
            nxt = min(rem, key=lambda x: (curr[0]-x['lat'])**2 + (curr[1]-x['lon'])**2)
            route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
        st.session_state.site_data = {s['uid']: {**s, "Installed": False} for s in route}
        st.session_state.optimized_route = route
        st.session_state.current_index = 0
        auto_save(); st.rerun()

# --- UI ---
if not st.session_state.optimized_route:
    st.title("🚦 Live Wire: Direct Sync")
    ex = st.file_uploader("1️⃣ Excel List", accept_multiple_files=True)
    maps = st.file_uploader("2️⃣ Map Files (.EST)", accept_multiple_files=True)
    if ex and maps and st.button("🚀 SYNC & DRIVE"):
        process_data([{"file": f, "label": f"Day {i+1}"} for i, f in enumerate(maps)], ex)
else:
    st.title("📁 Active Manifest")
    
    # Manifest Map (Small dots for accuracy)
    map_df = pd.DataFrame([{"lat": sd['lat'], "lon": sd['lon'], "color": "#00FF00" if sd['Installed'] else "#FFA500", "size": 6} 
                           for sd in st.session_state.site_data.values()])
    st.map(map_df, color="color", size="size")
    
    idx = st.session_state.current_index
    if 0 <= idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        sd = st.session_state.site_data.get(active['uid'])
        if sd:
            st.info(f"**STOP {idx+1}: SITE {sd['id']}**\n\n{sd['street']}")
            st.link_button("🚗 NAVIGATE", f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}", use_container_width=True)
            if st.button("✅ MARK INSTALLED & NEXT"):
                st.session_state.site_data[active['uid']]['Installed'] = True
                st.session_state.current_index += 1; auto_save(); st.rerun()
            if idx > 0:
                if st.button("⬅️ PREVIOUS"):
                    st.session_state.current_index -= 1; auto_save(); st.rerun()
    else: st.success("🏁 Shift Complete!")
    
    if st.button("🗑️ RESET SYSTEM"):
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
        st.session_state.optimized_route = []; st.rerun()
