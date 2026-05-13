import streamlit as st
import re
import pandas as pd
import json
import time
import os
import random
import requests
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_geolocation import streamlit_geolocation

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V51.74 Auto-Login", layout="centered")

HOME_COORDS = (33.7715, -117.9431) 

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
        .success-recap { background-color: #003300; border: 2px solid #00FF00; color: #00FF00; padding: 10px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; text-align: center;}
        .skip-recap { background-color: #330000; border: 2px solid #FF0000; color: #FF0000; padding: 10px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; text-align: center;}
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
        .success-recap { background-color: #1E2E1E; border: 2px solid #32CD32; color: #32CD32; padding: 10px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; text-align: center; }
        .skip-recap { background-color: #2E1E1E; border: 2px solid #FF4500; color: #FF4500; padding: 10px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; text-align: center; }
        </style>
        """

st.markdown(set_theme(st.session_state.theme), unsafe_allow_html=True)

# --- 1. AUTO-PROVISIONING LOGIN SCREEN ---
if "driver_name" not in st.session_state:
    st.title("🚦 LIVE WIRE: FIELD LOGIN")
    st.info("Enter your Name/ID. If this is your first time, your workspace will be created automatically.")
    
    with st.form("login_form"):
        username_input = st.text_input("DRIVER NAME:").strip().upper()
        submitted = st.form_submit_button("🚀 START SHIFT", use_container_width=True)
        
        if submitted:
            if username_input:
                st.session_state.driver_name = username_input
                st.rerun()
            else:
                st.error("❌ Please enter a name to continue.")
    st.stop() # Halts app completely until a name is provided

# Dynamic Backup File based on logged-in User
BACKUP_FILE = f"live_wire_backup_{st.session_state.driver_name}.json"

# --- 2. STATE MANAGEMENT ---
if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except Exception: pass
    if "optimized_route" not in st.session_state:
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.pickup_itinerary = [], [], []
        st.session_state.site_data = {}
        st.session_state.current_index, st.session_state.pickup_index = 0, 0
        st.session_state.mission_type = "📍 INSTALLATION"
        
    st.session_state.last_install_msg = None
    st.session_state.last_pickup_msg = None
    st.session_state.msg_type = "success"
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    return now.strftime("%H00"), now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")

def auto_save():
    # --- ATOMIC SAVE PROTOCOL (CRASH PROOF) ---
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
    temp_file = BACKUP_FILE + ".tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(payload, f)
        os.replace(temp_file, BACKUP_FILE)
    except Exception: pass

# --- ELITE CLUSTER SOLVER ---
def calc_scaled_dist(lat1, lon1, lat2, lon2):
    return ((lon1 - lon2) * 0.832)**2 + (lat1 - lat2)**2

def calc_total_distance(path):
    if not path: return 0
    d = calc_scaled_dist(HOME_COORDS[0], HOME_COORDS[1], path[0]['nav_lat'], path[0]['nav_lon'])
    for i in range(len(path) - 1):
        d += calc_scaled_dist(path[i]['nav_lat'], path[i]['nav_lon'], path[i+1]['nav_lat'], path[i+1]['nav_lon'])
    return d

def untangle_route(route):
    best_route = list(route)
    best_distance = calc_total_distance(best_route)
    improved = True
    while improved:
        improved = False
        for i in range(len(best_route) - 1):
            for j in range(i + 2, len(best_route) + 1):
                new_route = best_route[:i] + best_route[i:j][::-1] + best_route[j:]
                new_distance = calc_total_distance(new_route)
                if new_distance < best_distance:
                    best_route = new_route
                    best_distance = new_distance
                    improved = True
    return best_route, best_distance

def process_upload(est_configs, excel_files, m_type):
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    st.session_state.last_install_msg = None
    st.session_state.last_pickup_msg = None
    
    excel_data = {}
    for f in excel_files:
        try:
            df = pd.read_csv(f, encoding='latin-1') if f.name.lower().endswith('.csv') else pd.read_excel(f)
            id_c = next((c for c in df.columns if any(x in c.lower() for x in ['tds', 'site', 'id'])), df.columns[0])
            b_lat_c = next((c for c in df.columns if 'begin_lat' in c.lower()), next((c for c in df.columns if 'lat' in c.lower()), None))
            b_lon_c = next((c for c in df.columns if 'begin_lon' in c.lower()), next((c for c in df.columns if 'lon' in c.lower()), None))
            e_lat_c = next((c for c in df.columns if 'end_lat' in c.lower()), None)
            e_lon_c = next((c for c in df.columns if 'end_lon' in c.lower()), None)

            if b_lat_c and b_lon_c:
                for _, row in df.iterrows():
                    sid = str(row[id_c]).split('.')[0].strip()
                    if sid.isdigit():
                        try:
                            b_lat, b_lon = float(row[b_lat_c]), float(row[b_lon_c])
                            if 30.0 < b_lat < 40.0 and -125.0 < b_lon < -110.0:
                                nodes = [(b_lat, b_lon)]
                                if e_lat_c and e_lon_c and pd.notna(row[e_lat_c]) and pd.notna(row[e_lon_c]):
                                    e_lat, e_lon = float(row[e_lat_c]), float(row[e_lon_c])
                                    if 30.0 < e_lat < 40.0 and -125.0 < e_lon < -110.0:
                                        nodes.append((e_lat, e_lon))
                                street_name = str(row.get('Street', f'Site {sid}'))
                                excel_data[sid] = {"nodes": nodes, "street": street_name}
                        except Exception: pass
        except Exception: pass

    if not excel_data: return False, 0

    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_data.items():
            match = re.search(r'\b' + re.escape(sid) + r'\b', raw_map)
            if match:
                final_raw.append({
                    "id": sid, 
                    "uid": f"{cfg['label']}_{sid}", 
                    "nodes": data['nodes'], 
                    "sheet": cfg['label'], 
                    "street": data['street']
                })

    if final_raw:
        master_route, curr = [], HOME_COORDS
        temp_raw = list(final_raw)
        while temp_raw:
            best_site = min(temp_raw, key=lambda x: calc_scaled_dist(curr[0], curr[1], x['nodes'][0][0], x['nodes'][0][1]))
            best_node = min(best_site['nodes'], key=lambda n: calc_scaled_dist(curr[0], curr[1], n[0], n[1]))
            best_site['nav_lat'], best_site['nav_lon'] = best_node
            master_route.append(best_site)
            curr = best_node
            temp_raw.remove(best_site)
            
        best_route, best_dist = untangle_route(master_route)
        for _ in range(20):
            shuffled = list(master_route)
            random.shuffle(shuffled)
            opt_route, opt_dist = untangle_route(shuffled)
            if opt_dist < best_dist:
                best_dist = opt_dist
                best_route = opt_route
            
        st.session_state.optimized_route = best_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.site_data = {
            s['uid']: {
                "Date":"", "Time":"", "ExactTime":"", "Site":s['id'], "UID":s['uid'], "Counter":"c1b",
                "Serial":"", "Directions":"n", "Lanes":2, "Street":s['street'], "Notes":"", "Installed":"",
                "LAT":s['nav_lat'], "LON":s['nav_lon'], "Skipped":"", "Sheet":s['sheet']
            } for s in best_route
        }
        st.session_state.mission_type = m_type
        st.session_state.current_index = 0
        st.session_state.pickup_index = 0
        auto_save()
        return True, len(best_route)
    return False, 0

# --- NLP DICTATION ---
def parse_dictation(text, current_dr, current_ln, current_ser):
    if not text or pd.isna(text) or str(text).strip() == "": 
        return current_dr, current_ln, current_ser
    t = str(text).lower()
    dr = current_dr
    if "north" in t: dr = "n"
    elif "south" in t: dr = "s"
    elif "east" in t: dr = "e"
    elif "west" in t: dr = "w"
    
    # Allows numerical values via keyboard or voice
    ln = current_ln
    ln_match = re.search(r'(\d+)\s*lane', t)
    if ln_match: ln = int(ln_match.group(1))
    
    ser = current_ser
    ser_match = re.search(r'serial.*?(\w+)', t)
    if ser_match: ser = str(ser_match.group(1)).upper()
    return dr, ln, ser

# --- MAIN UI ---
col_logo, col_logout = st.columns([3, 1])
with col_logo: st.title(f"🚦 Ops: {st.session_state.driver_name}")
with col_logout:
    if st.button("LOGOUT", use_container_width=True):
        del st.session_state.driver_name
        st.rerun()

if not st.session_state.get("optimized_route"):
    restore_file = st.file_uploader("🔄 RESTORE BACKUP", type=["json"])
    if restore_file and st.button("🔓 LOAD BACKUP"):
        data = json.loads(restore_file.getvalue())
        for k, v in data.items(): st.session_state[k] = v
        st.rerun()
        
    st.divider()
    m_type = st.radio("MISSION:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    excel_files = st.file_uploader("1️⃣ EXCEL DATA", accept_multiple_files=True)
    up_files = st.file_uploader("2️⃣ MAPS (.EST)", accept_multiple_files=True)
    
    if up_files and excel_files:
        configs = [{"file": f, "label": st.text_input(f"Map {i+1} Name (e.g. Day 1):", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        if st.button("🚀 SYNC TACTICAL MAP"):
            success, count = process_upload(configs, excel_files, m_type)
            if success: 
                st.success(f"Locked {count} sites.")
                time.sleep(0.5)
                st.rerun()
            else: 
                st.error("Sync error. No matching sites found.")
else:
    new_theme = st.radio("MODE:", ["☁️ Overcast", "🌞 Bright Sun"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: 
        st.session_state.theme = new_theme
        auto_save()
        st.rerun()
    
    available_days = ["All Days"] + st.session_state.active_files
    selected_day = st.selectbox("📅 MISSION FILTER:", available_days)
    
    active_route = st.session_state.optimized_route if selected_day == "All Days" else [s for s in st.session_state.optimized_route if s['sheet'] == selected_day]
    
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL / AUDIT"])
    
    with tab1:
        st.success(f"STOPS IN VIEW: {len(active_route)}")
        
        m = folium.Map(location=HOME_COORDS, zoom_start=11, tiles="CartoDB dark_matter")
        folium.Marker(HOME_COORDS, popup="HOME", icon=folium.Icon(color="blue", icon="home")).add_to(m)
        route_coords = [HOME_COORDS]
        
        for idx, s in enumerate(active_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            skipped = sd.get("Skipped") == "x"
            safe_lat, safe_lon = sd.get('LAT', sd.get('lat')), sd.get('LON', sd.get('lon'))
            
            if safe_lat and safe_lon:
                route_coords.append((safe_lat, safe_lon))
                color = "#FF0000" if skipped else ("#00FF00" if done else "#FFA500")
                
                folium.CircleMarker(
                    location=(safe_lat, safe_lon), radius=10, color=color, fill=True, fill_color=color, fill_opacity=0.9,
                    popup=f"Stop {idx+1}: Site {sd.get('Site', s['id'])}"
                ).add_to(m)
                
                folium.Marker(
                    location=(safe_lat, safe_lon),
                    icon=DivIcon(
                        icon_size=(20,20),
                        icon_anchor=(10,10),
                        html=f'<div style="font-size: 10pt; color: black; font-weight: 900; text-align: center; line-height: 20px;">{idx+1}</div>',
                    )
                ).add_to(m)
        
        if len(route_coords) > 1:
            chunk_size = 50
            for i in range(0, len(route_coords) - 1, chunk_size - 1):
                chunk = route_coords[i:i + chunk_size]
                coords_str = ";".join([f"{lon},{lat}" for lat, lon in chunk])
                osrm_url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
                try:
                    resp = requests.get(osrm_url, timeout=3).json()
                    if resp.get('code') == 'Ok':
                        route_geo = resp['routes'][0]['geometry']['coordinates']
                        route_points = [(lat, lon) for lon, lat in route_geo]
                        folium.PolyLine(route_points, color="#00FFFF" if st.session_state.theme == "🌞 Bright Sun (OLED Contrast)" else "#FFD700", weight=4, opacity=0.7).add_to(m)
                except requests.exceptions.RequestException: 
                    pass 
        
        st_folium(m, height=450, use_container_width=True, returned_objects=[])
            
        for idx, s in enumerate(active_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            skipped = sd.get("Skipped") == "x"
            status_icon = '❌' if skipped else ('✅' if done else '🟠')
            if st.button(f"{status_icon} Stop {idx+1}: {sd.get('Site', s['id'])}", key=f"m_{s['uid']}", use_container_width=True):
                st.session_state.current_index = st.session_state.optimized_route.index(s)
                st.rerun()
                
        if st.button("🗑️ RESET ROUTE (CLEAR DEVICE)"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.session_state.optimized_route = []
            st.rerun()
            
    with tab2:
        cur = st.session_state.current_index
        if cur < len(st.session_state.optimized_route):
            
            if st.session_state.last_install_msg:
                css_class = "success-recap" if st.session_state.msg_type == "success" else "skip-recap"
                st.markdown(f"<div class='{css_class}'>{st.session_state.last_install_msg}</div>", unsafe_allow_html=True)
                
            s = st.session_state.optimized_route[cur]
            sd = st.session_state.site_data[s['uid']]
            safe_lat, safe_lon = sd.get('LAT', sd.get('lat')), sd.get('LON', sd.get('lon'))
            
            st.subheader(f"#{cur+1}: Site {sd.get('Site', s['id'])}")
            
            display_street = str(sd.get('Street', f"Site {s['id']}"))
            if display_street.lower() == 'nan': display_street = ""
            new_street = st.text_input("📍 STREET NAME (Edit if incorrect):", value=display_street)
            st.session_state.site_data[s['uid']]['Street'] = str(new_street).strip()
            
            st.link_button("🚗 NAV TO INTERSECTION NODE", f"https://www.google.com/maps/search/?api=1&query={safe_lat},{safe_lon}", use_container_width=True)
            
            batch = []
            for bs in st.session_state.optimized_route[cur:cur+9]:
                bsd = st.session_state.site_data[bs['uid']]
                if bsd.get('Installed') != "x" and bsd.get('Skipped') != "x":
                    b_lat, b_lon = bsd.get('LAT', bsd.get('lat')), bsd.get('LON', bsd.get('lon'))
                    if b_lat and b_lon: batch.append(f"{b_lat},{b_lon}")
                        
            if len(batch) > 1: st.link_button(f"🗺️ BATCH NAV", "https://www.google.com/maps/dir/" + "/".join(batch), use_container_width=True)
            
            st.info("🎙️ **VOICE PARSER:** Tap the box, use phone keyboard mic, and speak. Example: *'Facing south, IV lanes, serial 5678, wide road'*")
            dictation = st.text_area("Field Notes / Dictation:")
            
            loc = streamlit_geolocation()
            with st.form(f"f_{s['uid']}"):
                dr_val, ln_val, ser_val = parse_dictation(dictation, sd.get('Directions', 'n'), sd.get('Lanes', 2), str(sd.get('Serial', '')))
                dr = st.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(dr_val))
                ln = st.number_input("LANES", min_value=1, value=int(ln_val))
                ser = st.text_input("SERIAL #", value=str(ser_val))
                
                col_c, col_s = st.columns(2)
                with col_c: submit_btn = st.form_submit_button("✅ INSTALL")
                with col_s: skip_btn = st.form_submit_button("❌ SKIP")

                if submit_btn or skip_btn:
                    _, d, et = get_ca_time()
                    final_lat = loc['latitude'] if loc and loc.get('latitude') else safe_lat
                    final_lon = loc['longitude'] if loc and loc.get('longitude') else safe_lon
                    
                    st.session_state.site_data[s['uid']].update({
                        "Date":d, "ExactTime":et, "Directions":dr, "Serial":str(ser), "Lanes":ln, "N
