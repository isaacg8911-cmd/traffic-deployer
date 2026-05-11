import streamlit as st
import re
import pandas as pd
import json
import io
import time
import os
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_geolocation import streamlit_geolocation

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V51.23 Main-Arterial", layout="centered")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

# --- THEME ENGINE ---
if "theme" not in st.session_state:
    st.session_state.theme = "☁️ Overcast (Standard)"

def set_theme(theme_choice):
    if theme_choice == "🌞 Bright Sun (OLED Contrast)":
        return """
        <style>
        .stApp { background-color: #000000; color: #FFFFFF; }
        h1, h2, h3 { color: #00FFFF !important; font-family: 'Arial Black'; font-weight: 900;}
        div.stButton > button { background-color: #000000; color: #00FFFF; border: 3px solid #00FFFF; font-weight: 900; }
        .stTabs [data-baseweb="tab-list"] { background-color: #000000; border-bottom: 3px solid #333; }
        input, select, textarea { background-color: #000000 !important; color: #00FFFF !important; border: 2px solid #00FFFF !important; }
        div[data-testid="stMetricValue"] { color: #00FFFF !important; font-weight: 900; }
        </style>
        """
    else:
        return """
        <style>
        .stApp { background-color: #0A0A0A; color: #FFFFFF; }
        h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; }
        div.stButton > button { background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; font-weight: 900; }
        input, select, textarea { background-color: #111 !important; color: #FFD700 !important; border: 1px solid #444 !important; }
        div[data-testid="stMetricValue"] { color: #FFD700 !important; }
        </style>
        """

st.markdown(set_theme(st.session_state.theme), unsafe_allow_html=True)

if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except: pass
    if "optimized_route" not in st.session_state:
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.pickup_itinerary = [], [], []
        st.session_state.site_data = {}
        st.session_state.current_index, st.session_state.pickup_index = 0, 0
        st.session_state.mission_type = "📍 INSTALLATION"
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    return now.strftime("%H00"), now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")

def auto_save():
    try:
        payload = {
            "active_files": st.session_state.get("active_files", []),
            "optimized_route": st.session_state.get("optimized_route", []),
            "site_data": st.session_state.get("site_data", {}),
            "current_index": st.session_state.get("current_index", 0),
            "mission_type": st.session_state.get("mission_type", "📍 INSTALLATION"),
            "pickup_index": st.session_state.get("pickup_index", 0),
            "pickup_itinerary": st.session_state.get("pickup_itinerary", []),
            "theme": st.session_state.get("theme", "☁️ Overcast (Standard)")
        }
        with open(BACKUP_FILE, "w") as f:
            json.dump(payload, f)
    except: pass

def process_upload(est_configs, excel_files, m_type):
    excel_data = {}
    for f in excel_files:
        try:
            df = pd.read_csv(f, encoding='latin-1') if f.name.lower().endswith('.csv') else pd.read_excel(f)
            lat_c = next((c for c in df.columns if 'lat' in c.lower()), None)
            lon_c = next((c for c in df.columns if 'lon' in c.lower()), None)
            id_c = next((c for c in df.columns if any(x in c.lower() for x in ['site', 'tds', 'id'])), df.columns[0])
            if lat_c and lon_c:
                for _, row in df.iterrows():
                    sid = str(row[id_c]).split('.')[0].strip()
                    if sid.isdigit():
                        v1, v2 = float(row[lat_c]), float(row[lon_c])
                        lat = v1 if (32.0 < v1 < 36.0) else (v2 if (32.0 < v2 < 36.0) else None)
                        lon = v2 if (-120.0 < v2 < -114.0) else (v1 if (-120.0 < v1 < -114.0) else None)
                        if lat and lon:
                            excel_data[sid] = {"lat": lat, "lon": lon, "street": str(row.get('Street', f'Site {sid}'))}
        except: pass

    if not excel_data: return False, 0

    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_data.items():
            if sid in raw_map:
                # V51.23: ALWAYS prefer the Excel coordinate as it usually represents the main road intersection.
                # We only use the Map file to confirm the site belongs on this specific day's route.
                final_raw.append({
                    "id": sid, 
                    "uid": f"{cfg['label']}_{sid}", 
                    "nav_lat": data['lat'], 
                    "nav_lon": data['lon'], 
                    "sheet": cfg['label'], 
                    "street": data['street']
                })

    if final_raw:
        # Standard Nearest-Neighbor Routing
        master_route, curr = [], HOME_COORDS
        while final_raw:
            best_site = min(final_raw, key=lambda x: (curr[0]-x['nav_lat'])**2 + (curr[1]-x['nav_lon'])**2)
            master_route.append(best_site)
            curr = (best_site['nav_lat'], best_site['nav_lon'])
            final_raw.remove(best_site)
            
        st.session_state.optimized_route = master_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.site_data = {s['uid']: {
            "Date":"","Time":"","ExactTime":"","Site":s['id'],"UID":s['uid'],"Counter":"c1b","Serial":"",
            "Directions": "n", "Lanes":2,"Street":s['street'],"Notes":"","Installed":"",
            "LAT":s['nav_lat'],"LON":s['nav_lon'],"Skipped":False,"Sheet":s['sheet']
        } for s in master_route}
        st.session_state.mission_type, st.session_state.current_index, st.session_state.pickup_index = m_type, 0, 0
        auto_save(); return True, len(master_route)
    return False, 0

# --- UI ---
if not st.session_state.get("optimized_route"):
    st.title("🚦 Live Wire Direct Route")
    restore_file = st.file_uploader("🔄 RESTORE (.JSON)", type=["json"])
    if restore_file and st.button("🔓 LOAD"):
        data = json.loads(restore_file.getvalue()); [st.session_state.update({k: v}) for k, v in data.items()]; st.rerun()
    st.divider()
    m_type = st.radio("MISSION:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    excel_files = st.file_uploader("1️⃣ DATA (SITE & GPS)", accept_multiple_files=True)
    up_files = st.file_uploader("2️⃣ MAPS (DAY GROUPS)", accept_multiple_files=True)
    if up_files and excel_files:
        configs = [{"file": f, "label": st.text_input(f"Day {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        if st.button("🚀 SYNC DIRECT"):
            success, count = process_upload(configs, excel_files, m_type)
            if success: st.success(f"Locked {count} sites."); time.sleep(1); st.rerun()
            else: st.error("No California site matches found.")
else:
    new_theme = st.radio("MODE:", ["☁️ Overcast", "🌞 Bright Sun"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: st.session_state.theme = new_theme; auto_save(); st.rerun()
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])
    with tab1:
        st.success(f"STOPS: {len(st.session_state.optimized_route)}")
        map_points = [{"lat": HOME_COORDS[0], "lon": HOME_COORDS[1], "color": "#FFFFFF", "size": 12}]
        for s in st.session_state.optimized_route:
            sd = st.session_state.site_data[s['uid']]
            done = sd["Installed"] == "x" or sd.get("Picked up") == "x"
            map_points.append({"lat": sd['LAT'], "lon": sd['LON'], "color": "#00FF00" if done else "#FFA500", "size": 8})
        st.map(pd.DataFrame(map_points), color="color", size="size")
        for idx, s in enumerate(st.session_state.optimized_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd["Installed"] == "x" or sd.get("Picked up") == "x"
            if st.button(f"{'✅' if done else '🟠'} Stop {idx+1}: Site {sd['Site']}", key=f"m_{idx}", use_container_width=True):
                st.session_state.current_index = idx; st.rerun()
        if st.button("🗑️ RESET"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.session_state.optimized_route = []; st.rerun()
    with tab2:
        cur = st.session_state.current_index
        if cur < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur]; sd = st.session_state.site_data[s['uid']]
            st.subheader(f"#{cur+1}: Site {sd['Site']}")
            st.link_button("🚗 NAV TO SITE", f"https://www.google.com/maps/search/?api=1&query={sd['LAT']},{sd['LON']}", use_container_width=True)
            batch = [f"{st.session_state.site_data[bs['uid']]['LAT']},{st.session_state.site_data[bs['uid']]['LON']}" for bs in st.session_state.optimized_route[cur:cur+9] if st.session_state.site_data[bs['uid']]['Installed'] != "x"]
            if len(batch) > 1: st.link_button(f"🗺️ BATCH NAV", "https://www.google.com/maps/dir/" + "/".join(batch), use_container_width=True)
            loc = streamlit_geolocation()
            with st.form(f"f_{cur}"):
                dr = st.selectbox("DIR", ["n","e","s","w"])
                ln = st.number_input("LANES", min_value=1, value=2)
                ser, nt = st.text_input("SERIAL #"), st.text_input("NOTES")
                if st.form_submit_button("✅ COMPLETE", use_container_width=True):
                    _, d, et = get_ca_time()
                    st.session_state.site_data[s['uid']].update({"Date":d, "ExactTime":et, "Directions":dr, "Serial":ser, "Lanes":ln, "Notes":nt, "Installed":"x", "LAT":loc['latitude'] if loc and loc.get('latitude') else sd['LAT'], "LON":loc['longitude'] if loc and loc.get('longitude') else sd['LON']})
                    st.session_state.current_index += 1; auto_save(); st.rerun()
    with tab3:
        itin = [sd for sd in st.session_state.site_data.values() if sd.get("Installed") == "x"]
        if itin:
            p_idx = st.session_state.pickup_index
            if p_idx < len(itin):
                s = itin[p_idx]
                st.subheader(f"PICK-UP #{p_idx+1}: Site {s['Site']}")
                st.link_button("🚗 NAV", f"https://www.google.com/maps/search/?api=1&query={s['LAT']},{s['LON']}", use_container_width=True)
                if st.button("✅ SECURED", use_container_width=True):
                    st.session_state.site_data[s['UID']]["Picked up"] = "x"; st.session_state.pickup_index += 1; auto_save(); st.rerun()
    with tab4:
        all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
        if all_d:
            st.download_button("📊 DOWNLOAD EXCEL", pd.DataFrame(all_d).to_csv(index=False), "Report.csv", use_container_width=True)
