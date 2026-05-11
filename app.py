import streamlit as st
import pandas as pd
import json
import re
import os
import time
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_folium import st_folium
import folium

# --- CORE CONFIG ---
st.set_page_config(page_title="Live Wire V51.29 Sat-Plotter", layout="centered")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

# --- THEME ---
st.markdown("""
    <style>
    .stApp { background-color: #0A0A0A; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; }
    div.stButton > button { background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; font-weight: bold; border-radius: 8px; }
    .stSelectbox label { color: #FFD700 !important; }
    </style>
""", unsafe_allow_html=True)

if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except: pass
    if "optimized_route" not in st.session_state:
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data = [], [], {}
        st.session_state.current_index, st.session_state.plotting_mode = 0, True
    st.session_state.init = True

def auto_save():
    payload = {
        "active_files": st.session_state.active_files,
        "optimized_route": st.session_state.optimized_route,
        "site_data": st.session_state.site_data,
        "current_index": st.session_state.current_index,
        "plotting_mode": st.session_state.plotting_mode
    }
    with open(BACKUP_FILE, "w") as f: json.dump(payload, f)

def process_data(est_configs, excel_files):
    excel_data = {}
    for f in excel_files:
        try:
            df = pd.read_csv(f, encoding='latin-1') if f.name.lower().endswith('.csv') else pd.read_excel(f)
            lat_c = next((c for c in df.columns if 'lat' in c.lower()), None)
            lon_c = next((c for c in df.columns if 'lon' in c.lower()), None)
            id_c = next((c for c in df.columns if any(x in c.lower() for x in ['site', 'tds', 'id'])), df.columns[0])
            for _, row in df.iterrows():
                sid = str(row[id_c]).split('.')[0].strip()
                if sid.isdigit():
                    v1, v2 = float(row[lat_c]), float(row[lon_c])
                    lat = v1 if (32.0 < v1 < 36.0) else (v2 if (32.0 < v2 < 36.0) else v1)
                    lon = v2 if (-120.0 < v2 < -114.0) else (v1 if (-120.0 < v1 < -114.0) else v2)
                    excel_data[sid] = {"lat": lat, "lon": lon, "street": str(row.get('Street', f'Site {sid}'))}
        except: pass

    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_data.items():
            if sid in raw_map:
                uid = f"{cfg['label']}_{sid}"
                final_raw.append({"id": sid, "uid": uid, "lat": data['lat'], "lon": data['lon'], "sheet": cfg['label'], "street": data['street']})
    
    st.session_state.optimized_route = final_raw
    st.session_state.site_data = {s['uid']: {**s, "Installed": False} for s in final_raw}
    st.session_state.active_files = [c['label'] for c in est_configs]
    st.session_state.plotting_mode = True
    auto_save()

# --- UI LOGIC ---
if not st.session_state.optimized_route:
    st.title("🚦 Live Wire: Data Sync")
    ex = st.file_uploader("1️⃣ DATA (Excel/CSV)", accept_multiple_files=True)
    maps = st.file_uploader("2️⃣ MAPS (.EST)", accept_multiple_files=True)
    if ex and maps and st.button("🚀 INITIAL SYNC"):
        configs = [{"file": f, "label": f"Day {i+1}"} for i, f in enumerate(maps)]
        process_data(configs, ex)
        st.rerun()

elif st.session_state.plotting_mode:
    st.title("🎯 Tactical Plotter")
    st.info("Tap the Satellite map to move the site pin. Get it off the dead-end and onto the main road.")
    
    options = [s['uid'] for s in st.session_state.optimized_route]
    target_uid = st.selectbox("Select Site to Verify:", options)
    sd = st.session_state.site_data[target_uid]

    # --- SATELLITE PLOTTER MAP ---
    m = folium.Map(location=[sd['lat'], sd['lon']], zoom_start=18, tiles=None)
    # Adding Esri Satellite tiles for better field visibility
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    folium.Marker(
        [sd['lat'], sd['lon']], 
        popup=f"Site {sd['id']}", 
        icon=folium.Icon(color='orange', icon='location-dot', prefix='fa')
    ).add_to(m)
    
    map_data = st_folium(m, height=450, width=700)

    if map_data and map_data.get("last_clicked"):
        new_coords = map_data["last_clicked"]
        if st.button(f"Relocate Site {sd['id']} to Tapped Spot"):
            st.session_state.site_data[target_uid]['lat'] = new_coords['lat']
            st.session_state.site_data[target_uid]['lon'] = new_coords['lng']
            for s in st.session_state.optimized_route:
                if s['uid'] == target_uid:
                    s['lat'], s['lon'] = new_coords['lat'], new_coords['lng']
            st.success(f"Site {sd['id']} Fixed!")
            auto_save()
            time.sleep(0.5)
            st.rerun()

    st.divider()
    if st.button("🏁 LOCK PLACEMENT & GENERATE ROUTE", use_container_width=True):
        st.session_state.plotting_mode = False
        # Final Route Optimization
        curr = HOME_COORDS
        new_route, rem = [], list(st.session_state.optimized_route)
        while rem:
            nxt = min(rem, key=lambda x: (curr[0]-x['lat'])**2 + (curr[1]-x['lon'])**2)
            new_route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
        st.session_state.optimized_route = new_route
        auto_save(); st.rerun()

else:
    # --- DRIVING MODE ---
    st.title("📁 Active Route")
    idx = st.session_state.current_index
    if idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        sd = st.session_state.site_data[active['uid']]
        
        st.subheader(f"Stop {idx+1}: Site {sd['id']}")
        st.write(f"📍 {sd['street']}")
        
        st.link_button("🚗 NAVIGATE TO PLOTTED SPOT", f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}", use_container_width=True)
        
        if st.button("✅ MARK INSTALLED", use_container_width=True):
            st.session_state.site_data[active['uid']]['Installed'] = True
            st.session_state.current_index += 1
            auto_save(); st.rerun()
    else:
        st.success("Shift Complete!")
    
    if st.button("🗑️ CLEAR SYSTEM"):
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
        st.session_state.optimized_route = []
        st.rerun()
