import streamlit as st
import pandas as pd
import json
import re
import os
import time
import math
from datetime import datetime
from zoneinfo import ZoneInfo

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V51.36 Quad-Node", layout="centered")

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

if "init" not in st.session_state:
    st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], {}, 0
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

def get_best_arterial_node(lat1, lon1, lat2, lon2):
    """Generates 4 points and snaps to the one most accessible from arterial flow."""
    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    q1_lat, q1_lon = (lat1 + mid_lat) / 2, (lon1 + mid_lon) / 2
    q2_lat, q2_lon = (mid_lat + lat2) / 2, (mid_lon + lon2) / 2
    nodes = [(lat1, lon1), (q1_lat, q1_lon), (mid_lat, mid_lon), (q2_lat, q2_lon), (lat2, lon2)]
    # Snap to the node closest to the city center/arterial start (Garden Grove/Home)
    return min(nodes, key=lambda n: (n[0]-HOME_COORDS[0])**2 + (n[1]-HOME_COORDS[1])**2)

def process_data(est_configs, excel_files):
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
                        lat = v1 if (32.0 < v1 < 36.0) else (v2 if (32.0 < v2 < 36.0) else v1)
                        lon = v2 if (-121.0 < v2 < -114.0) else (v1 if (-121.0 < v1 < -114.0) else v2)
                        excel_map[sid] = {"lat": lat, "lon": lon, "street": str(row.get('Street', f'Site {sid}'))}
                    except: continue
        except: pass

    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_map.items():
            if sid in raw_map:
                # AUDIT: Search Map file for the "other" coordinate to build the 4-node bridge
                gps_matches = re.findall(r'(-?\d{2,3}\.\d{3,})', raw_map[raw_map.find(sid):raw_map.find(sid)+2500])
                m_lat, m_lon = data['lat'], data['lon']
                for val in [float(x) for x in gps_matches]:
                    if 32.0 < val < 36.0: m_lat = val
                    if -121.0 < val < -114.0: m_lon = val
                
                # EXECUTE QUAD-NODE SNAP
                best_lat, best_lon = get_best_arterial_node(data['lat'], data['lon'], m_lat, m_lon)
                uid = f"{cfg['label']}_{sid}".replace(" ", "_")
                final_raw.append({"id": sid, "uid": uid, "lat": best_lat, "lon": best_lon, "street": data['street']})

    if final_raw:
        curr = HOME_COORDS
        route, rem = [], list(final_raw)
        while rem:
            nxt = min(rem, key=lambda x: (curr[0]-x['lat'])**2 + (curr[1]-x['lon'])**2)
            route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
        st.session_state.site_data = {s['uid']: {**s, "Installed": False} for s in route}
        st.session_state.optimized_route = route; st.session_state.current_index = 0
        auto_save(); st.rerun()

# --- UI ---
if not st.session_state.optimized_route:
    st.title("🚦 Live Wire: Quad-Node Sync")
    ex = st.file_uploader("1️⃣ Excel Site List", accept_multiple_files=True)
    maps = st.file_uploader("2️⃣ Map Files (.EST)", accept_multiple_files=True)
    if ex and maps and st.button("🚀 SYNC & AUDIT NODES"):
        process_data([{"file": f, "label": f"Day {i+1}"} for i, f in enumerate(maps)], ex)
else:
    st.title("📁 Active Manifest")
    # MANIFEST MAP: DOTS 1/4 SMALLER
    map_data = [{"lat": sd['lat'], "lon": sd['lon'], "color": "#00FF00" if sd['Installed'] else "#FFA500", "size": 8} 
                for sd in st.session_state.site_data.values()]
    st.map(pd.DataFrame(map_data), color="color", size="size")
    
    idx = st.session_state.current_index
    if 0 <= idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        sd = st.session_state.site_data.get(active['uid'])
        if sd:
            st.info(f"**STOP {idx+1}: SITE {sd['id']}**\n\n{sd['street']}")
            st.link_button("🚗 NAVIGATE (NODE OPTIMIZED)", f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}", use_container_width=True)
            if st.button("✅ MARK INSTALLED & NEXT"):
                st.session_state.site_data[active['uid']]['Installed'] = True
                st.session_state.current_index += 1; auto_save(); st.rerun()
    else: st.success("🏁 Shift Complete!")
    if st.button("🗑️ RESET"):
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
        st.session_state.optimized_route = []; st.rerun()
