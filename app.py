import streamlit as st
import pandas as pd
import json
import re
import os
import time
import math
from datetime import datetime
from zoneinfo import ZoneInfo

# --- CORE CONFIG ---
st.set_page_config(page_title="Live Wire V51.45 Quad-Node Efficiency", layout="centered")

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

def get_5_nodes(p1, p2):
    """Calculates Beg, End, Mid, and 2 Quarter-Points between two GPS coordinates."""
    lat1, lon1 = p1
    lat2, lon2 = p2
    mid = ((lat1 + lat2) / 2, (lon1 + lon2) / 2)
    q1 = ((lat1 + mid[0]) / 2, (lon1 + mid[1]) / 2)
    q2 = ((mid[0] + lat2) / 2, (mid[1] + lon2) / 2)
    return [p1, q1, mid, q2, p2]

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
                    v1, v2 = float(row[lat_c]), float(row[lon_c])
                    lat = v1 if (30.0 < v1 < 40.0) else v2
                    lon = v2 if (-125.0 < v2 < -110.0) else v1
                    excel_map[sid] = (lat, lon, str(row.get('Street', f'Site {sid}')))
        except: pass

    final_pool = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, (ex_lat, ex_lon, street) in excel_map.items():
            if sid in raw_map:
                # Find the Map coordinate to create the segment
                gps_matches = re.findall(r'(-?\d{2,3}\.\d{3,})', raw_map[raw_map.find(sid):raw_map.find(sid)+2500])
                m_lat, m_lon = ex_lat, ex_lon
                for val in [float(x) for x in gps_matches]:
                    if 32.0 < val < 36.0: m_lat = val
                    if -120.0 < val < -114.0: m_lon = val
                
                nodes = get_5_nodes((ex_lat, ex_lon), (m_lat, m_lon))
                final_pool.append({"id": sid, "uid": f"{cfg['label']}_{sid}", "nodes": nodes, "street": street})

    if final_pool:
        # HOME-TO-HOME ROUTING ENGINE
        curr = HOME_COORDS
        route = []
        while final_pool:
            # Find the site with the NEAREST single node to current position
            best_site = None
            best_node = None
            min_dist = float('inf')
            
            for site in final_pool:
                for node in site['nodes']:
                    d = (curr[0]-node[0])**2 + (curr[1]-node[1])**2
                    if d < min_dist:
                        min_dist = d
                        best_site = site
                        best_node = node
            
            best_site['lat'], best_site['lon'] = best_node
            route.append(best_site)
            curr = best_node
            final_pool.remove(best_site)
            
        st.session_state.site_data = {s['uid']: {**s, "Installed": False} for s in route}
        st.session_state.optimized_route = route
        st.session_state.current_index = 0
        auto_save(); st.rerun()

# --- UI ---
if not st.session_state.optimized_route:
    st.title("🚦 Live Wire: Node-Efficiency Sync")
    ex = st.file_uploader("1️⃣ Excel List", accept_multiple_files=True)
    maps = st.file_uploader("2️⃣ Map Files (.EST)", accept_multiple_files=True)
    if ex and maps and st.button("🚀 OPTIMIZE 5-NODE ROUTE"):
        process_data([{"file": f, "label": f"Day {i+1}"} for i, f in enumerate(maps)], ex)
else:
    st.title("📁 Optimized Manifest")
    # Small dots (size 6) for clarity
    map_df = pd.DataFrame([{"lat": sd['lat'], "lon": sd['lon'], "color": "#00FF00" if sd['Installed'] else "#FFA500", "size": 6} 
                           for sd in st.session_state.site_data.values()])
    st.map(map_df, color="color", size="size")
    
    st.divider()

    idx = st.session_state.current_index
    if idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        sd = st.session_state.site_data.get(active['uid'])
        
        st.info(f"**STOP {idx+1}: SITE {sd['id']}**\n\n{sd['street']}")
        st.link_button("🚗 NAV TO FASTEST NODE", f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}", use_container_width=True)
        
        # Batch 9
        batch = [f"{st.session_state.site_data[s['uid']]['lat']},{st.session_state.site_data[s['uid']]['lon']}" 
                 for s in st.session_state.optimized_route[idx:idx+9] if not st.session_state.site_data[s['uid']]['Installed']]
        if len(batch) > 1:
            st.link_button(f"🗺️ BATCH NAV {len(batch)} SITES", f"https://www.google.com/maps/dir/{'/'.join(batch)}", use_container_width=True)

        if st.button("✅ MARK INSTALLED & NEXT", use_container_width=True):
            st.session_state.site_data[active['uid']]['Installed'] = True
            st.session_state.current_index += 1; auto_save(); st.rerun()
            
        if idx > 0:
            if st.button("⬅️ PREV STOP"):
                st.session_state.current_index -= 1; auto_save(); st.rerun()
    else:
        # END AT HOME
        st.success("🏁 All sites installed.")
        st.link_button("🏠 RETURN HOME (GARDEN GROVE)", f"https://www.google.com/maps/search/?api=1&query={HOME_COORDS[0]},{HOME_COORDS[1]}", use_container_width=True)

    if st.button("🗑️ RESET"):
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
        st.session_state.optimized_route = []; st.rerun()
