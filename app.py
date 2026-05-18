import streamlit as st
import streamlit.components.v1 as components
import re
import pandas as pd
import json
import time
import os
import math
import requests
import folium
import uuid
import io
from folium.features import DivIcon
from streamlit_folium import st_folium
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- TITANIUM SAFETY NET FOR COOKIES & GPS ---
try:
    from streamlit_cookies_manager import CookieManager
    HAS_COOKIES = True
except ImportError:
    HAS_COOKIES = False

try:
    from streamlit_geolocation import streamlit_geolocation
    HAS_GPS = True
except ImportError:
    HAS_GPS = False

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Traffic Data Service V51.119", layout="centered")

# --- 👑 COMMANDER PROFILE SETUP ---
COMMANDER_NAME = "ISAAC GARCIA"

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
        input, select, textarea { background-color: #000000 !important; color: #00FFFF !important; border: 2px solid #00FFFF !important; }
        div[data-testid="stMetricValue"] { color: #00FFFF !important; font-weight: 900; }
        .success-recap { background-color: #003300; border: 2px solid #00FF00; color: #00FF00; padding: 10px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; text-align: center;}
        .skip-recap { background-color: #330000; border: 2px solid #FF0000; color: #FF0000; padding: 10px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; text-align: center;}
        .list-card { background-color: #111; border: 1px solid #00FFFF; padding: 10px; border-radius: 5px; margin-bottom: 5px; }
        div[role="radiogroup"] { padding-bottom: 10px; border-bottom: 2px solid #333; margin-bottom: 15px;}
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
        .list-card { background-color: #1a1a1a; border: 1px solid #444; padding: 10px; border-radius: 5px; margin-bottom: 5px; }
        div[role="radiogroup"] { padding-bottom: 10px; border-bottom: 2px solid #333; margin-bottom: 15px;}
        </style>
        """

st.markdown(set_theme(st.session_state.theme), unsafe_allow_html=True)

# --- OFFLINE JS LOCALSTORAGE INJECTION ---
components.html(
    """
    <script>
    function backupToBrowser() {
        const state = window.parent.document.body.innerText;
        if(state.includes('Traffic Data Service')) {
            localStorage.setItem('tds_emergency_backup', Date.now());
        }
    }
    setInterval(backupToBrowser, 10000);
    </script>
    """,
    height=0,
)

if HAS_COOKIES:
    cookies = CookieManager()
    if not cookies.ready():
        st.stop()
else:
    cookies = {}

# --- 1. AUTO-PROVISIONING LOGIN SCREEN ---
if "driver_name" not in st.session_state:
    if HAS_COOKIES and "tds_driver_cookie" in cookies and cookies["tds_driver_cookie"]:
        st.session_state.driver_name = cookies["tds_driver_cookie"]
        st.rerun()
    else:
        st.title("🚦 TRAFFIC DATA SERVICE")
        st.info("Enter your Name/ID. If this is your first time, your workspace will be created automatically.")
        
        if not HAS_COOKIES:
            st.warning("⚠️ Auto-Login disabled. Add `streamlit-cookies-manager` to requirements.txt.")
            
        with st.form("login_form"):
            username_input = st.text_input("DRIVER NAME:").strip().upper()
            submitted = st.form_submit_button("🚀 START SHIFT", use_container_width=True)
            
            if submitted:
                if username_input:
                    st.session_state.driver_name = username_input
                    if HAS_COOKIES:
                        cookies["tds_driver_cookie"] = username_input
                        cookies.save()
                    st.rerun()
                else:
                    st.error("❌ Please enter a name to continue.")
        st.stop()

BACKUP_FILE = f"tds_backup_{st.session_state.driver_name}.json"

# --- 2. MASTER STATE SANITIZER ---
if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except Exception: pass

defaults = {
    "session_id": str(uuid.uuid4())[:8],
    "home_coords": (33.7715, -117.9431),
    "active_files": [],
    "optimized_route": [],
    "raw_nodes": [], 
    "manual_sequence": [], 
    "routing_phase": "upload", 
    "site_data": {},
    "current_index": 0,
    "pickup_index": 0,
    "mission_type": "📍 INSTALLATION",
    "upload_strategy": "📌 Keep Maps Separate (Day-by-Day)",
    "auto_advance_nav": False,
    "last_install_msg": None,
    "last_pickup_msg": None,
    "msg_type": "success",
    "auto_open_url": "",
    "pickup_target": "All Maps (Merged)",
    "pickup_sort_method": "🔄 Route Efficiency",
    "install_view_toggle": "Single Site Mode", 
    "pickup_view_toggle": "Single Site Mode",
    "last_processed_click": None,
    "map_center": None, 
    "map_zoom": None,
    "drafting_day": None, 
    "init": True
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    return now.strftime("%H00"), now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")

def auto_save():
    payload = {k: st.session_state[k] for k in defaults.keys() if k in st.session_state}
    payload["theme"] = st.session_state.get("theme", "☁️ Overcast (Standard)")
    try:
        with open(BACKUP_FILE, "w") as f:
            json.dump(payload, f, default=str)
    except Exception: pass

def render_backup_button(suffix):
    st.divider()
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f: backup_data = f.read()
            st.download_button("💾 DOWNLOAD BACKUP JSON", backup_data, f"tds_backup_{st.session_state.driver_name}.json", mime="application/json", use_container_width=True, key=f"bkp_btn_{suffix}")
        except Exception: pass

def get_map_bounds(nodes, home_coords):
    if not nodes: return None
    lats = [home_coords[0]] + [n.get('nav_lat', n.get('LAT')) for n in nodes if n.get('nav_lat') or n.get('LAT')]
    lons = [home_coords[1]] + [n.get('nav_lon', n.get('LON')) for n in nodes if n.get('nav_lon') or n.get('LON')]
    if not lats or not lons: return None
    return [[min(lats), min(lons)], [max(lats), max(lons)]]

def geocode_address(address):
    try:
        url = f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address={requests.utils.quote(address)}&benchmark=Public_AR_Current&format=json"
        resp = requests.get(url, timeout=5).json()
        matches = resp.get("result", {}).get("addressMatches", [])
        if matches:
            return float(matches[0]["coordinates"]["y"]), float(matches[0]["coordinates"]["x"])
    except Exception: pass
    try:
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(address)}"
        headers = {'User-Agent': f'TDS-Traffic-Ops-{st.session_state.session_id}/1.0'}
        resp = requests.get(url, headers=headers, timeout=5).json()
        if resp:
            return float(resp[0]['lat']), float(resp[0]['lon'])
    except Exception: pass
    return None, None

def get_street_from_coords(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        headers = {'User-Agent': f'TDS-Traffic-Ops-{st.session_state.session_id}/1.0'}
        resp = requests.get(url, headers=headers, timeout=3).json()
        if 'address' in resp and 'road' in resp['address']:
            return resp['address']['road'] 
    except Exception: pass
    return ""

def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371.0 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def solve_tsp_fixed(nodes_list, start_coords):
    if not nodes_list: return []
    unvisited = list(nodes_list)
    route = []
    curr_lat, curr_lon = start_coords
        
    while unvisited:
        next_node = min(unvisited, key=lambda x: haversine_dist(curr_lat, curr_lon, x['nav_lat'], x['nav_lon']))
        route.append(next_node)
        curr_lat, curr_lon = next_node['nav_lat'], next_node['nav_lon']
        unvisited.remove(next_node)
        
    return route

def process_upload(est_configs, excel_files, m_type, route_strategy):
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    st.session_state.last_install_msg = None
    st.session_state.last_pickup_msg = None
    st.session_state.upload_strategy = route_strategy 
    st.session_state.manual_sequence = []
    st.session_state.last_processed_click = None
    st.session_state.map_center = None 
    st.session_state.map_zoom = None
    
    excel_data = {}
    for f in excel_files:
        try:
            if f.name.lower().endswith('.csv'):
                dfs = {'Sheet1': pd.read_csv(f, encoding='latin-1')}
            else:
                dfs = pd.read_excel(f, sheet_name=None)
                
            for s_name, df in dfs.items():
                id_c = next((c for c in df.columns if any(x in c.lower() for x in ['tds', 'site', 'id'])), df.columns[0])
                b_lat_c = next((c for c in df.columns if 'begin_lat' in c.lower()), next((c for c in df.columns if 'lat' in c.lower()), None))
                b_lon_c = next((c for c in df.columns if 'begin_lon' in c.lower()), next((c for c in df.columns if 'lon' in c.lower()), None))
                
                if b_lat_c and b_lon_c:
                    for _, row in df.iterrows():
                        sid = str(row[id_c]).split('.')[0].strip()
                        if sid.isdigit():
                            try:
                                b_lat, b_lon = float(row[b_lat_c]), float(row[b_lon_c])
                                if 30.0 < b_lat < 40.0 and -125.0 < b_lon < -110.0:
                                    nodes = [(b_lat, b_lon)]
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
                best_node = min(data['nodes'], key=lambda n: haversine_dist(st.session_state.home_coords[0], st.session_state.home_coords[1], n[0], n[1]))
                best_node_lat, best_node_lon = best_node[0], best_node[1]
                
                overlap_count = sum(1 for n in final_raw if abs(n['nav_lat'] - best_node_lat) < 0.00001 and abs(n['nav_lon'] - best_node_lon) < 0.00001)
                if overlap_count > 0:
                    best_node_lat += 0.00005 * overlap_count
                    best_node_lon += 0.00005 * overlap_count
                    
                final_raw.append({
                    "id": sid, 
                    "uid": f"{cfg['label']}_{sid}", 
                    "nav_lat": best_node_lat,
                    "nav_lon": best_node_lon,
                    "sheet": cfg['label'], 
                    "street": data['street']
                })

    if final_raw:
        st.session_state.raw_nodes = final_raw
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.mission_type = m_type
        st.session_state.routing_phase = "drafting"
        st.session_state.drafting_day = st.session_state.active_files[0] if st.session_state.active_files else None
        auto_save()
        return True, len(final_raw)
    return False, 0

def parse_dictation(text, current_dr, current_ln, current_ser):
    if not text or pd.isna(text) or str(text).strip() == "": 
        return current_dr, current_ln, current_ser
    t = str(text).lower()
    dr = current_dr
    if "north" in t: dr = "n"
    elif "south" in t: dr = "s"
    elif "east" in t: dr = "e"
    elif "west" in t: dr = "w"
    ln = current_ln
    ln_match = re.search(r'(\d+)\s*lane', t)
    if ln_match: ln = int(ln_match.group(1))
    ser = current_ser
    ser_match = re.search(r'serial.*?(\w+)', t)
    if ser_match: ser = str(ser_match.group(1)).upper()
    return dr, ln, ser

def get_next_valid_index(current_idx, active_uids, direction=1):
    if not active_uids: return current_idx
    if current_idx >= len(st.session_state.optimized_route):
        current_idx = len(st.session_state.optimized_route) - 1
    current_uid = st.session_state.optimized_route[current_idx]['uid']
    if current_uid in active_uids:
        list_idx = active_uids.index(current_uid)
        new_list_idx = list_idx + direction
        if 0 <= new_list_idx < len(active_uids):
            target_uid = active_uids[new_list_idx]
            return next((i for i, s in enumerate(st.session_state.optimized_route) if s['uid'] == target_uid), current_idx)
    return current_idx

# --- MAIN UI ---
col_logo, col_logout = st.columns([3, 1])
with col_logo: st.title(f"🚦 Ops: {st.session_state.driver_name}")
with col_logout:
    if st.button("LOGOUT", use_container_width=True):
        if HAS_COOKIES and "tds_driver_cookie" in cookies:
            del cookies["tds_driver_cookie"]
            cookies.save()
            
        keys_to_wipe = ["driver_name", "optimized_route", "site_data", "init", "pickup_index", "current_index", "active_files", "mission_type", "last_install_msg", "last_pickup_msg", "msg_type", "show_pickup_map", "pickup_sort_method", "pickup_target", "upload_strategy", "auto_advance_nav", "auto_open_url", "routing_phase", "raw_nodes", "manual_sequence", "last_processed_click", "map_center", "map_zoom", "install_view_toggle", "pickup_view_toggle", "drafting_day"]
        for k in keys_to_wipe:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

if st.session_state.get("auto_open_url"):
    components.html(f"<script>window.open('{st.session_state.auto_open_url}', '_blank');</script>", height=0)
    st.session_state.auto_open_url = ""

# --- UPLOAD PHASE ---
if st.session_state.routing_phase == "upload":
    restore_file = st.file_uploader("🔄 RESTORE BACKUP", type=["json"])
    if restore_file and st.button("🔓 LOAD BACKUP"):
        data = json.loads(restore_file.getvalue())
        for k, v in data.items(): st.session_state[k] = v
        if "routing_phase" not in data and "optimized_route" in data and len(data["optimized_route"]) > 0:
            st.session_state.routing_phase = "finalized"
        st.rerun()
        
    st.divider()
    
    st.subheader("🏠 1. SET STARTING POINT")
    st.write(f"**Saved Origin:** `{st.session_state.home_coords[0]:.5f}, {st.session_state.home_coords[1]:.5f}`")
    
    tab_gps, tab_addr, tab_coords = st.tabs(["📍 1-Tap GPS", "🏠 Search Address", "✏️ Manual Coords"])
    
    with tab_gps:
        st.write("Grab your live phone/truck location:")
        if HAS_GPS:
            loc_start = streamlit_geolocation()
            if loc_start and loc_start.get('latitude'):
                current_lat = round(loc_start['latitude'], 4)
                saved_lat = round(st.session_state.home_coords[0], 4)
                if current_lat != saved_lat:
                    st.session_state.home_coords = (loc_start['latitude'], loc_start['longitude'])
                    auto_save()
                    st.success("✅ Origin snapped to GPS!")
                    time.sleep(1)
                    st.rerun()
        else:
            st.error("GPS Module missing in cloud. Use Search Address.")

    with tab_addr:
        address_input = st.text_input("Enter Address (e.g., 123 Main St, Garden Grove, CA):")
        if st.button("🔍 LOCATE & SAVE ADDRESS", use_container_width=True):
            if address_input:
                found_lat, found_lon = geocode_address(address_input)
                if found_lat and found_lon:
                    st.session_state.home_coords = (found_lat, found_lon)
                    auto_save()
                    st.success("✅ Origin locked in via Cloud Geocoder!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Address not found by API. Try using the GPS or Coordinates tab.")
            else:
                st.warning("Please type an address first.")

    with tab_coords:
        c_lat, c_lon = st.columns(2)
        with c_lat: man_lat = st.number_input("Latitude", value=st.session_state.home_coords[0], format="%.5f")
        with c_lon: man_lon = st.number_input("Longitude", value=st.session_state.home_coords[1], format="%.5f")
        if st.button("💾 SAVE COORDS", use_container_width=True):
            st.session_state.home_coords = (man_lat, man_lon)
            auto_save()
            st.success("✅ Origin Updated!")
            time.sleep(1)
            st.rerun()

    st.divider()
    st.subheader("📁 2. UPLOAD DATA")
    m_type = st.radio("MISSION:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    
    r_strat = st.radio("ROUTING STRATEGY:", ["📌 Keep Maps Separate (Day-by-Day)", "🔗 Merge All Maps into One Route"], horizontal=True)
    
    excel_files = st.file_uploader("EXCEL DATA (Supports multiple sheets)", accept_multiple_files=True)
    up_files = st.file_uploader("MAPS (.EST)", accept_multiple_files=True)
    
    if up_files and excel_files:
        configs = [{"file": f, "label": st.text_input(f"Map {i+1} Name (e.g. Day {i+1}):", value=f"Day {i+1}", key=f"l_{i}_{st.session_state.session_id}")} for i, f in enumerate(up_files)]
        if st.button("🚀 SYNC TACTICAL MAP", use_container_width=True):
            success, count = process_upload(configs, excel_files, m_type, r_strat)
            if success: 
                time.sleep(0.5)
                st.rerun()
            else: 
                st.error("Sync error. No matching sites found.")

# --- DRAFTING PHASE (SOLID-STATE MENU FIX) ---
elif st.session_state.routing_phase == "drafting":
    new_theme = st.radio("MODE:", ["☁️ Overcast", "🌞 Bright Sun"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: 
        st.session_state.theme = new_theme
        auto_save()
        st.rerun()
        
    map_tiles = "CartoDB dark_matter" if st.session_state.theme == "☁️ Overcast (Standard)" else "CartoDB positron"
    hc = st.session_state.home_coords
    is_commander = str(st.session_state.driver_name).upper() == COMMANDER_NAME.upper()
    
    if is_commander:
        draft_view = st.radio("COMMAND CENTER NAVIGATION:", ["🗺️ ROUTE BUILDER", "👑 FORECAST"], horizontal=True, label_visibility="collapsed")
    else:
        draft_view = "🗺️ ROUTE BUILDER"
    
    if draft_view == "🗺️ ROUTE BUILDER":
        if st.session_state.upload_strategy == "📌 Keep Maps Separate (Day-by-Day)":
            if "drafting_day" not in st.session_state or not st.session_state.drafting_day:
                st.session_state.drafting_day = st.session_state.active_files[0] if st.session_state.active_files else None
                
            new_draft_day = st.radio("📝 ACTIVE MAP:", st.session_state.active_files, index=st.session_state.active_files.index(st.session_state.drafting_day) if st.session_state.drafting_day in st.session_state.active_files else 0, horizontal=True)
            
            if new_draft_day != st.session_state.drafting_day:
                st.session_state.drafting_day = new_draft_day
                st.session_state.map_center = None 
                st.session_state.map_zoom = None
                st.session_state.last_processed_click = None
                st.rerun()
                
            active_raw_nodes = [n for n in st.session_state.raw_nodes if n['sheet'] == st.session_state.drafting_day]
            active_title = f"({st.session_state.drafting_day})"
        else:
            active_raw_nodes = st.session_state.raw_nodes
            active_title = "(All Maps Merged)"

        active_total = len(active_raw_nodes)
        active_sequence = [uid for uid in st.session_state.manual_sequence if any(n['uid'] == uid for n in active_raw_nodes)]
        active_tapped = len(active_sequence)

        st.subheader(f"🗺️ ROUTE BUILDER {active_title}")
        st.info(f"Progress: {active_tapped}/{active_total} Sequenced. Map will NOT snap when dragging.")
        
        if st.session_state.map_center and st.session_state.map_zoom:
            m_draft = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles=map_tiles)
        else:
            m_draft = folium.Map(location=hc, zoom_start=11, tiles=map_tiles)
            bounds = get_map_bounds(active_raw_nodes, hc)
            if bounds: m_draft.fit_bounds(bounds) 
            
        folium.Marker(hc, tooltip="STARTING POINT", icon=folium.Icon(color="blue", icon="home")).add_to(m_draft)
        
        path_coords = []
        
        for idx, uid in enumerate(active_sequence):
            node = next((n for n in active_raw_nodes if n['uid'] == uid), None)
            if node:
                path_coords.append((node['nav_lat'], node['nav_lon']))
                
                tag = f" [{node['sheet']}]" if st.session_state.upload_strategy == "🔗 Merge All Maps into One Route" else ""
                
                folium.CircleMarker(
                    location=(node['nav_lat'], node['nav_lon']), radius=10, color="#00FF00", fill=True, fill_color="#00FF00", fill_opacity=0.9,
                    tooltip=f"Stop {idx+1}: Site {node['id']}{tag}"
                ).add_to(m_draft)
                
                folium.Marker(
                    location=(node['nav_lat'], node['nav_lon']),
                    icon=DivIcon(
                        icon_size=(20,20),
                        icon_anchor=(10,10),
                        html=f'<div style="font-size: 10pt; color: black; font-weight: 900; text-align: center; line-height: 20px;">{idx+1}</div>',
                    )
                ).add_to(m_draft)
                
        unsequenced_active = [n for n in active_raw_nodes if n['uid'] not in st.session_state.manual_sequence]
        for node in unsequenced_active:
            tag = f" [{node['sheet']}]" if st.session_state.upload_strategy == "🔗 Merge All Maps into One Route" else ""
            folium.CircleMarker(
                location=(node['nav_lat'], node['nav_lon']), radius=8, color="#FFA500", fill=True, fill_color="#FFA500", fill_opacity=0.7,
                tooltip=f"Site {node['id']}{tag} (Untapped)"
            ).add_to(m_draft)

        if len(path_coords) > 1:
            folium.PolyLine(path_coords, color="#00FFFF" if st.session_state.theme == "🌞 Bright Sun (OLED Contrast)" else "#FFD700", weight=3, dash_array="5, 10").add_to(m_draft)
                
        # HARD BYPASS FOR REACT ERROR 185: Fixed width of 720px prevents the layout engine from infinitely thrashing
        map_data = st_folium(m_draft, width=720, height=450, returned_objects=["last_object_clicked"], key="draft_map")
        
        if map_data and map_data.get("last_object_clicked"):
            click_lat = map_data["last_object_clicked"]["lat"]
            click_lon = map_data["last_object_clicked"]["lng"]
            click_id = f"{click_lat}_{click_lon}"
            
            if click_id != st.session_state.last_processed_click:
                st.session_state.last_processed_click = click_id
                
                min_dist = float('inf')
                clicked_uid = None
                for s in active_raw_nodes:
                    dist = haversine_dist(click_lat, click_lon, s['nav_lat'], s['nav_lon'])
                    if dist < min_dist:
                        min_dist = dist
                        clicked_uid = s['uid']
                        
                if clicked_uid and min_dist < 0.2:
                    if clicked_uid not in st.session_state.manual_sequence:
                        st.session_state.manual_sequence.append(clicked_uid)
                        st.session_state.map_center = [click_lat, click_lon]
                        st.session_state.map_zoom = 14 
                        auto_save()
                        st.rerun()

        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("⏪ UNDO LAST TAP", use_container_width=True):
                if len(active_sequence) > 0:
                    uid_to_remove = active_sequence[-1]
                    st.session_state.manual_sequence.remove(uid_to_remove)
                    st.session_state.last_processed_click = None 
                    
                    new_active_sequence = [uid for uid in st.session_state.manual_sequence if any(n['uid'] == uid for n in active_raw_nodes)]
                    if len(new_active_sequence) > 0:
                        prev_uid = new_active_sequence[-1]
                        prev_node = next((n for n in active_raw_nodes if n['uid'] == prev_uid), None)
                        if prev_node:
                            st.session_state.map_center = [prev_node['nav_lat'], prev_node['nav_lon']]
                    else:
                        st.session_state.map_center = None
                        
                    auto_save()
                    st.rerun()
        with c2:
            if st.button("🤖 SMART AUTO-FINISH", use_container_width=True):
                if unsequenced_active:
                    if len(active_sequence) == 0:
                        auto_route = solve_tsp_fixed(unsequenced_active, hc)
                        for n in auto_route:
                            st.session_state.manual_sequence.append(n['uid'])
                    else:
                        current_seq = list(active_sequence)
                        for u_node in unsequenced_active:
                            best_insert_idx = len(current_seq)
                            min_added_dist = float('inf')
                            
                            node_0 = next(n for n in active_raw_nodes if n['uid'] == current_seq[0])
                            d_home_u = haversine_dist(hc[0], hc[1], u_node['nav_lat'], u_node['nav_lon'])
                            d_u_0 = haversine_dist(u_node['nav_lat'], u_node['nav_lon'], node_0['nav_lat'], node_0['nav_lon'])
                            d_home_0 = haversine_dist(hc[0], hc[1], node_0['nav_lat'], node_0['nav_lon'])
                            if (d_home_u + d_u_0 - d_home_0) < min_added_dist:
                                min_added_dist = (d_home_u + d_u_0 - d_home_0)
                                best_insert_idx = 0
                                
                            for i in range(len(current_seq) - 1):
                                n_a = next(n for n in active_raw_nodes if n['uid'] == current_seq[i])
                                n_b = next(n for n in active_raw_nodes if n['uid'] == current_seq[i+1])
                                d_a_u = haversine_dist(n_a['nav_lat'], n_a['nav_lon'], u_node['nav_lat'], u_node['nav_lon'])
                                d_u_b = haversine_dist(u_node['nav_lat'], u_node['nav_lon'], n_b['nav_lat'], n_b['nav_lon'])
                                d_a_b = haversine_dist(n_a['nav_lat'], n_a['nav_lon'], n_b['nav_lat'], n_b['nav_lon'])
                                if (d_a_u + d_u_b - d_a_b) < min_added_dist:
                                    min_added_dist = (d_a_u + d_u_b - d_a_b)
                                    best_insert_idx = i + 1
                                    
                            n_last = next(n for n in active_raw_nodes if n['uid'] == current_seq[-1])
                            added = haversine_dist(n_last['nav_lat'], n_last['nav_lon'], u_node['nav_lat'], u_node['nav_lon'])
                            if added < min_added_dist:
                                best_insert_idx = len(current_seq)
                                
                            current_seq.insert(best_insert_idx, u_node['uid'])
                        
                        first_idx = next((i for i, uid in enumerate(st.session_state.manual_sequence) if uid in active_sequence), len(st.session_state.manual_sequence))
                        st.session_state.manual_sequence = [uid for uid in st.session_state.manual_sequence if uid not in current_seq]
                        for uid in reversed(current_seq):
                            st.session_state.manual_sequence.insert(first_idx, uid)
                    auto_save()
                    st.rerun()
        with c3:
            if st.button("🗑️ CLEAR THIS MAP", use_container_width=True):
                st.session_state.manual_sequence = [uid for uid in st.session_state.manual_sequence if uid not in active_sequence]
                st.session_state.last_processed_click = None
                st.session_state.map_center = None 
                st.session_state.map_zoom = None
                auto_save()
                st.rerun()

        st.divider()
        
        global_tapped = len(st.session_state.manual_sequence)
        if global_tapped > 0:
            if st.button(f"✅ FINALIZE ALL ROUTES ({global_tapped} Total Stops)", use_container_width=True):
                st.session_state.optimized_route = []
                for uid in st.session_state.manual_sequence:
                    node = next((n for n in st.session_state.raw_nodes if n['uid'] == uid))
                    st.session_state.optimized_route.append(node)
                    
                st.session_state.site_data = {
                    s['uid']: {
                        "Date": "", "Time": "", "ExactTime": "", "Site": s['id'], "UID": s['uid'], "Counter": "c1b",
                        "Serial": "", "Directions": "n", "Lanes": 2, "Street": s['street'], "Notes": "", "Installed": "",
                        "LAT": s['nav_lat'], "LON": s['nav_lon'], "Skipped": "", "Sheet": s['sheet']
                    } for s in st.session_state.optimized_route
                }
                st.session_state.map_center = None 
                st.session_state.map_zoom = None
                st.session_state.routing_phase = "finalized"
                auto_save()
                st.rerun()
                
        if st.button("❌ CANCEL & RESTART"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            keys_to_wipe = ["optimized_route", "raw_nodes", "manual_sequence", "routing_phase", "last_processed_click", "map_center", "map_zoom", "drafting_day"]
            for k in keys_to_wipe:
                if k in st.session_state: del st.session_state[k]
            st.session_state.routing_phase = "upload"
            st.rerun()

    elif draft_view == "👑 FORECAST":
        st.subheader("👑 Commander Projection Engine")
        st.info("Calculate estimated shift duration based on your current drafted sequence.")
        c_proj1, c_proj2, c_proj3 = st.columns(3)
        with c_proj1: shift_start = st.time_input("Shift Start Time:", value=datetime.strptime("08:00 AM", "%I:%M %p").time(), key="proj_start_draft")
        with c_proj2: avg_stop = st.number_input("Avg Mins per Stop:", value=15, min_value=1, key="proj_mins_draft")
        with c_proj3: 
            st.write("")
            run_proj = st.button("⏱️ PROJECT SHIFT", use_container_width=True, key="proj_btn_draft")
            
        if run_proj:
            start_dt = datetime.combine(datetime.today(), shift_start)
            
            def calc_time(uids):
                if not uids: return 0, 0
                coords = [(hc[0], hc[1])]
                for u in uids:
                    node = next((n for n in st.session_state.raw_nodes if n['uid'] == u), None)
                    if node: coords.append((node['nav_lat'], node['nav_lon']))
                coords.append((hc[0], hc[1]))
                
                drive_sec = 0
                chunk_size = 50
                for i in range(0, len(coords) - 1, chunk_size - 1):
                    chunk = coords[i:i + chunk_size]
                    coords_str = ";".join([f"{lon},{lat}" for lat, lon in chunk])
                    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=false"
                    try:
                        resp = requests.get(osrm_url, timeout=3).json()
                        if resp.get('code') == 'Ok':
                            drive_sec += resp['routes'][0]['duration']
                        else: raise Exception()
                    except:
                        for j in range(len(chunk)-1):
                            dist = haversine_dist(chunk[j][0], chunk[j][1], chunk[j+1][0], chunk[j+1][1])
                            drive_sec += (dist / 48.28) * 3600 
                return drive_sec / 60.0, len(uids) * avg_stop
            
            if st.session_state.upload_strategy == "🔗 Merge All Maps into One Route":
                if st.session_state.manual_sequence:
                    d_mins, s_mins = calc_time(st.session_state.manual_sequence)
                    end_dt = start_dt + timedelta(minutes=(d_mins + s_mins))
                    st.success(f"**MERGED ROUTE:** {len(st.session_state.manual_sequence)} Stops")
                    st.write(f"🚗 Drive Time: {int(d_mins)} mins | 🛠️ Work Time: {int(s_mins)} mins")
                    st.info(f"🏁 **Projected Return Home: {end_dt.strftime('%I:%M %p')}**")
                else:
                    st.warning("Sequence some stops first!")
            else:
                has_data = False
                for day in st.session_state.active_files:
                    day_uids = [u for u in st.session_state.manual_sequence if any(n['uid'] == u and n['sheet'] == day for n in st.session_state.raw_nodes)]
                    if day_uids:
                        has_data = True
                        d_mins, s_mins = calc_time(day_uids)
                        end_dt = start_dt + timedelta(minutes=(d_mins + s_mins))
                        st.success(f"**{day}:** {len(day_uids)} Stops")
                        st.write(f"🚗 Drive Time: {int(d_mins)} mins | 🛠️ Work Time: {int(s_mins)} mins")
                        st.info(f"🏁 **Projected Return Home: {end_dt.strftime('%I:%M %p')}**")
                if not has_data:
                    st.warning("Sequence some stops first!")

# --- FINALIZED PHASE (SOLID-STATE MENU FIX) ---
elif st.session_state.routing_phase == "finalized":
    new_theme = st.radio("MODE:", ["☁️ Overcast", "🌞 Bright Sun"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: 
        st.session_state.theme = new_theme
        auto_save()
        st.rerun()
        
    map_tiles = "CartoDB dark_matter" if st.session_state.theme == "☁️ Overcast (Standard)" else "CartoDB positron"
    
    show_origin_tag = st.session_state.get("upload_strategy") == "🔗 Merge All Maps into One Route"
    
    if show_origin_tag:
        available_days = ["All Days"]
        selected_day = "All Days"
        st.info("🔗 Mission Filter locked: All maps merged into a single route.")
    else:
        available_days = ["All Days"] + st.session_state.active_files
        selected_day = st.selectbox("📅 MISSION FILTER:", available_days, index=1 if len(available_days) > 1 else 0)
    
    active_route = st.session_state.optimized_route if selected_day == "All Days" else [s for s in st.session_state.optimized_route if s['sheet'] == selected_day]
    active_uids = [s['uid'] for s in active_route]
    
    # SOLID STATE MENU (Replaces buggy st.tabs)
    tab_names = ["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL / AUDIT"]
    is_commander = str(st.session_state.driver_name).upper() == COMMANDER_NAME.upper()
    if is_commander:
        tab_names.append("👑 COMMANDER")
        
    if "active_main_tab" not in st.session_state:
        st.session_state.active_main_tab = "📁 ROUTE"
        
    main_view = st.radio("OPERATIONAL NAVIGATION:", tab_names, index=tab_names.index(st.session_state.active_main_tab) if st.session_state.active_main_tab in tab_names else 0, horizontal=True, label_visibility="collapsed")
    if main_view != st.session_state.active_main_tab:
        st.session_state.active_main_tab = main_view
        st.rerun()
    
    if main_view == "📁 ROUTE":
        st.success(f"STOPS IN VIEW: {len(active_route)}")
        
        hc = st.session_state.home_coords
        m = folium.Map(location=hc, zoom_start=11, tiles=map_tiles)
        
        bounds = get_map_bounds(active_route, hc)
        if bounds: m.fit_bounds(bounds)
        
        folium.Marker(hc, tooltip="STARTING POINT", icon=folium.Icon(color="blue", icon="home")).add_to(m)
        route_coords = [hc]
        
        for idx, s in enumerate(active_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            skipped = sd.get("Skipped") == "x"
            safe_lat, safe_lon = sd.get('LAT', sd.get('lat')), sd.get('LON', sd.get('lon'))
            
            if safe_lat and safe_lon:
                route_coords.append((safe_lat, safe_lon))
                color = "#FF0000" if skipped else ("#00FF00" if done else "#FFA500")
                
                tag = f" [{sd.get('Sheet')}]" if show_origin_tag else ""
                
                folium.CircleMarker(
                    location=(safe_lat, safe_lon), radius=10, color=color, fill=True, fill_color=color, fill_opacity=0.9,
                    tooltip=f"Stop {idx+1}: Site {sd.get('Site', s['id'])}{tag}"
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
        
        # HARD BYPASS FOR REACT ERROR 185
        st_folium(m, width=720, height=450, returned_objects=[], key="main_route_map")
            
        for idx, s in enumerate(active_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            skipped = sd.get("Skipped") == "x"
            status_icon = '❌' if skipped else ('✅' if done else '🟠')
            tag = f" [{sd.get('Sheet')}]" if show_origin_tag else ""
            if st.button(f"{status_icon} Stop {idx+1}: Site {sd.get('Site', s['id'])}{tag}", key=f"m_{s['uid']}_{st.session_state.session_id}", use_container_width=True):
                st.session_state.current_index = next((i for i, stop in enumerate(st.session_state.optimized_route) if stop['uid'] == s['uid']), 0)
                st.session_state.install_view_toggle = "Single Site Mode" 
                st.session_state.active_main_tab = "📍 INSTALL"
                st.rerun()
                
        if st.button("🗑️ RESET ROUTE (CLEAR DEVICE)"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            keys_to_wipe = ["optimized_route", "raw_nodes", "manual_sequence", "routing_phase", "site_data", "map_center", "map_zoom", "drafting_day", "active_main_tab"]
            for k in keys_to_wipe:
                if k in st.session_state: del st.session_state[k]
            st.session_state.routing_phase = "upload"
            st.rerun()
            
    elif main_view == "📍 INSTALL":
        installed_count = sum(1 for s in active_route if st.session_state.site_data[s['uid']].get("Installed") == "x" or st.session_state.site_data[s['uid']].get("Skipped") == "x")
        total_active = len(active_route)
        if total_active > 0:
            st.progress(installed_count / total_active, text=f"Install Progress: {installed_count} / {total_active} Sites")

        install_view = st.radio("Install View:", ["Single Site Mode", "Full Manifest List"], key="install_view_toggle", horizontal=True)
        
        if st.session_state.install_view_toggle == "Full Manifest List":
            st.markdown("### 📋 Active Manifest")
            for idx, s in enumerate(active_route):
                sd = st.session_state.site_data[s['uid']]
                status = "✅ Installed" if sd.get("Installed") == "x" else ("❌ Skipped" if sd.get("Skipped") == "x" else "⏳ Pending")
                tag = f" [{sd.get('Sheet')}]" if show_origin_tag else ""
                
                with st.container():
                    st.markdown(f"<div class='list-card'>", unsafe_allow_html=True)
                    c1, c2, c3 = st.columns([1, 3, 1])
                    c1.write(f"**{status}**")
                    c2.write(f"Stop {idx+1}: **Site {sd.get('Site')}**{tag} \n{sd.get('Street', 'Unknown Street')}")
                    
                    if c3.button("🔍 OPEN", key=f"jump_inst_{s['uid']}", use_container_width=True):
                        st.session_state.current_index = next((i for i, stop in enumerate(st.session_state.optimized_route) if stop['uid'] == s['uid']), 0)
                        st.session_state.install_view_toggle = "Single Site Mode"
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            render_backup_button("install")
        else:
            new_auto = st.checkbox("🚀 Auto-Open Next Stop Map on Install", value=st.session_state.auto_advance_nav)
            if new_auto != st.session_state.auto_advance_nav:
                st.session_state.auto_advance_nav = new_auto
                auto_save()
                
            cur = st.session_state.current_index
            if cur < len(st.session_state.optimized_route):
                if st.session_state.last_install_msg:
                    css_class = "success-recap" if st.session_state.msg_type == "success" else "skip-recap"
                    st.markdown(f"<div class='{css_class}'>{st.session_state.last_install_msg}</div>", unsafe_allow_html=True)
                    
                s = st.session_state.optimized_route[cur]
                sd = st.session_state.site_data[s['uid']]
                safe_lat, safe_lon = sd.get('LAT', sd.get('lat')), sd.get('LON', sd.get('lon'))
                tag = f" [{sd.get('Sheet')}]" if show_origin_tag else ""
                
                st.subheader(f"#{cur+1}: Site {sd.get('Site', s['id'])}{tag}")
                
                display_street = str(sd.get('Street', f"Site {s['id']}"))
                if display_street.lower() == 'nan': display_street = ""
                new_street = st.text_input("📍 STREET NAME (Auto-Fills on Install):", value=display_street)
                
                nav_url = f"https://www.google.com/maps/dir/?api=1&destination={safe_lat},{safe_lon}&dir_action=navigate"
                st.link_button("🚗 NAV TO SITE", nav_url, use_container_width=True)
                
                batch = []
                try:
                    active_idx = next(i for i, route_site in enumerate(active_route) if route_site['uid'] == s['uid'])
                    for bs in active_route[active_idx:active_idx+9]:
                        bsd = st.session_state.site_data[bs['uid']]
                        if bsd.get('Installed') != "x" and bsd.get('Skipped') != "x":
                            b_lat, b_lon = bsd.get('LAT', bsd.get('lat')), bsd.get('LON', bsd.get('lon'))
                            if b_lat and b_lon: batch.append(f"{b_lat},{b_lon}")
                except StopIteration:
                    pass
                            
                if len(batch) > 1:
                    waypoints_str = "|".join(batch[:-1])
                    dest_str = batch[-1]
                    batch_url = f"https://www.google.com/maps/dir/?api=1&destination={dest_str}&waypoints={requests.utils.quote(waypoints_str)}&dir_action=navigate"
                    st.link_button(f"🗺️ BATCH NAV (Next {len(batch)} Stops)", batch_url, use_container_width=True)
                
                st.info("📍 Grab precise GPS below to lock-in the exact field coordinate and auto-name the street.")
                if HAS_GPS:
                    loc_install = streamlit_geolocation() 
                else:
                    loc_install = None
                
                with st.form(f"form_{s['uid']}"):
                    st.info("🎙️ **VOICE PARSER:** Type or dictate notes below.")
                    dictation = st.text_area("📝 Field Notes / Dictation:", value=str(sd.get('Notes', '')))
                    
                    c1, c2, c3 = st.columns(3)
                    with c1: dr = st.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(sd.get('Directions', 'n')))
                    with c2: ln = st.number_input("LANES", min_value=1, value=int(sd.get('Lanes', 2)))
                    with c3: ser = st.text_input("SERIAL #", value=str(sd.get('Serial', '')))
                    
                    col_c, col_s = st.columns(2)
                    with col_c: submit_btn = st.form_submit_button("✅ INSTALL")
                    with col_s: skip_btn = st.form_submit_button("❌ SKIP")

                    if submit_btn or skip_btn:
                        old_notes = str(sd.get('Notes', ''))
                        if dictation != old_notes and dictation.strip() != "":
                            final_dr, final_ln, final_ser = parse_dictation(dictation, dr, ln, ser)
                        else:
                            final_dr, final_ln, final_ser = dr, ln, ser
                            
                        _, d, et = get_ca_time()
                        
                        final_lat = loc_install['latitude'] if loc_install and loc_install.get('latitude') else safe_lat
                        final_lon = loc_install['longitude'] if loc_install and loc_install.get('longitude') else safe_lon
                        
                        auto_street = get_street_from_coords(final_lat, final_lon) if submit_btn else str(sd.get('Street', ''))
                        if not auto_street: auto_street = str(new_street).strip()
                        
                        st.session_state.site_data[s['uid']].update({
                            "Street": auto_street,
                            "Date": d, 
                            "ExactTime": et, 
                            "Directions": final_dr, 
                            "Serial": str(final_ser), 
                            "Lanes": final_ln, 
                            "Notes": str(dictation), 
                            "Installed": "x" if submit_btn else "", 
                            "Skipped": "x" if skip_btn else "",
                            "LAT": final_lat,
                            "LON": final_lon
                        })
                        
                        if submit_btn:
                            st.session_state.msg_type = "success"
                            st.session_state.last_install_msg = f"✅ Site {sd.get('Site', s['id'])} SECURED at {auto_street}."
                            
                            if st.session_state.auto_advance_nav:
                                next_idx = get_next_valid_index(cur, active_uids, direction=1)
                                if next_idx != cur:
                                    n_lat = st.session_state.optimized_route[next_idx]['nav_lat']
                                    n_lon = st.session_state.optimized_route[next_idx]['nav_lon']
                                    st.session_state.auto_open_url = f"https://www.google.com/maps/dir/?api=1&destination={n_lat},{n_lon}&dir_action=navigate"

                        else:
                            st.session_state.msg_type = "skip"
                            st.session_state.last_install_msg = f"❌ Site {sd.get('Site', s['id'])} SKIPPED. Reason logged."
                            
                        st.session_state.current_index = get_next_valid_index(cur, active_uids, direction=1)
                        auto_save()
                        st.rerun()
                
                if sd.get('Installed') == "x" or sd.get('Skipped') == "x":
                    if st.button("⏪ UNDO STATUS (Re-open Site)", use_container_width=True):
                        st.session_state.site_data[s['uid']]['Installed'] = ""
                        st.session_state.site_data[s['uid']]['Skipped'] = ""
                        auto_save()
                        st.rerun()

                st.divider()
                nav1, nav2 = st.columns(2)
                with nav1:
                    if st.button("⬅️ PREV STOP", use_container_width=True, key=f"prev_{s['uid']}"):
                        st.session_state.current_index = get_next_valid_index(cur, active_uids, direction=-1)
                        st.session_state.last_install_msg = None
                        auto_save()
                        st.rerun()
                with nav2:
                    if st.button("NEXT ➡️", use_container_width=True, key=f"next_{s['uid']}"):
                        st.session_state.current_index = get_next_valid_index(cur, active_uids, direction=1)
                        st.session_state.last_install_msg = None
                        auto_save()
                        st.rerun()
            else:
                st.success("🎉 ALL STOPS ON THIS MANIFEST ARE COMPLETED!")
                if st.button("⬅️ GO BACK TO LAST STOP", use_container_width=True):
                    st.session_state.current_index = len(st.session_state.optimized_route) - 1
                    auto_save()
                    st.rerun()
            
            render_backup_button("install_bottom")
                    
    elif main_view == "♻️ PICK-UP":
        raw_itin = [sd for sd in st.session_state.site_data.values() if sd.get("Installed") == "x"]
        
        if raw_itin:
            st.subheader("♻️ Pick-Up Strategy Engine")
            
            available_targets = ["All Maps (Merged)"] + st.session_state.active_files
            safe_target_index = available_targets.index(st.session_state.pickup_target) if st.session_state.pickup_target in available_targets else 0
            
            new_target = st.selectbox("🎯 Select Pick-Up Target:", available_targets, index=safe_target_index)
            
            if new_target != st.session_state.pickup_target:
                st.session_state.pickup_target = new_target
                st.session_state.pickup_index = 0
                st.session_state.show_pickup_map = False
                auto_save()
                st.rerun()
                
            if st.session_state.pickup_target != "All Maps (Merged)":
                raw_itin = [sd for sd in raw_itin if sd.get("Sheet") == st.session_state.pickup_target]

            new_sort = st.radio("Sort Manifest By:", ["🔄 Route Efficiency", "⏱️ Order Installed"], index=0 if st.session_state.pickup_sort_method == "🔄 Route Efficiency" else 1, horizontal=True)
            
            if new_sort != st.session_state.pickup_sort_method:
                st.session_state.pickup_sort_method = new_sort
                st.session_state.pickup_index = 0
                st.session_state.show_pickup_map = False 
                auto_save()
                st.rerun()
                
            if st.session_state.pickup_sort_method == "⏱️ Order Installed":
                raw_itin.sort(key=lambda x: x.get('ExactTime', ''))
                itin = raw_itin
            else:
                itin = [site['sd'] for site in solve_tsp_fixed([{'uid': sd['UID'], 'nav_lat': float(sd['LAT']), 'nav_lon': float(sd['LON']), 'sd': sd} for sd in raw_itin], st.session_state.home_coords)]
                
            if st.session_state.pickup_index >= len(itin):
                st.session_state.pickup_index = max(0, len(itin) - 1)
                
            picked_count = sum(1 for sd in itin if sd.get("Picked up") == "x")
            if len(itin) > 0:
                st.progress(picked_count / len(itin), text=f"Pick-Up Progress: {picked_count} / {len(itin)} Sites")

            st.divider()

            if itin and st.button("🗺️ GENERATE PICK-UP MAP MANIFEST", use_container_width=True):
                st.session_state.show_pickup_map = not st.session_state.get("show_pickup_map", False)
                
            if st.session_state.get("show_pickup_map", False) and itin:
                st.success(f"TACTICAL PICK-UP MAP: {len(itin)} Secured Sites")
                m_pickup = folium.Map(location=st.session_state.home_coords, zoom_start=11, tiles=map_tiles)
                
                bounds = get_map_bounds(itin, st.session_state.home_coords)
                if bounds: m_pickup.fit_bounds(bounds)
                
                folium.Marker(st.session_state.home_coords, tooltip="STARTING POINT", icon=folium.Icon(color="blue", icon="home")).add_to(m_pickup)
                
                pickup_coords = [st.session_state.home_coords]
                for idx, p_site in enumerate(itin):
                    p_lat, p_lon = p_site.get('LAT'), p_site.get('LON')
                    is_picked_up = p_site.get("Picked up") == "x"
                    color = "#00FF00" if is_picked_up else "#FFA500" 
                    tag = f" [{p_site.get('Sheet')}]" if show_origin_tag else ""
                    
                    if p_lat and p_lon:
                        pickup_coords.append((p_lat, p_lon))
                        folium.CircleMarker(
                            location=(p_lat, p_lon), radius=10, color=color, fill=True, fill_color=color, fill_opacity=0.9,
                            tooltip=f"Pick-Up {idx+1}: Site {p_site.get('Site')}{tag}"
                        ).add_to(m_pickup)
                        
                        folium.Marker(
                            location=(p_lat, p_lon),
                            icon=DivIcon(
                                icon_size=(20,20), icon_anchor=(10,10),
                                html=f'<div style="font-size: 10pt; color: black; font-weight: 900; text-align: center; line-height: 20px;">{idx+1}</div>',
                            )
                        ).add_to(m_pickup)
                
                if len(pickup_coords) > 1:
                    chunk_size = 50
                    for i in range(0, len(pickup_coords) - 1, chunk_size - 1):
                        chunk = pickup_coords[i:i + chunk_size]
                        coords_str = ";".join([f"{lon},{lat}" for lat, lon in chunk])
                        osrm_url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
                        try:
                            resp = requests.get(osrm_url, timeout=3).json()
                            if resp.get('code') == 'Ok':
                                route_geo = resp['routes'][0]['geometry']['coordinates']
                                route_points = [(lat, lon) for lon, lat in route_geo]
                                folium.PolyLine(route_points, color="#00FFFF" if st.session_state.theme == "🌞 Bright Sun (OLED Contrast)" else "#FFD700", weight=4, opacity=0.7).add_to(m_pickup)
                        except: pass
                
                # HARD BYPASS FOR REACT ERROR 185
                st_folium(m_pickup, width=720, height=450, returned_objects=[], key="pickup_map_render")
                st.divider()
            elif not itin:
                st.warning("No installed sites found for the selected Pick-Up target.")

            if itin:
                pickup_view = st.radio("Pick-Up View:", ["Single Site Mode", "Full Manifest List"], key="pickup_view_toggle", horizontal=True)
                
                if st.session_state.pickup_view_toggle == "Full Manifest List":
                    st.markdown("### 📋 Pick-Up Manifest")
                    for p_idx, s in enumerate(itin):
                        status = "✅ Done" if s.get("Picked up") == "x" else "⏳ Pending"
                        tag = f" [{s.get('Sheet')}]" if show_origin_tag else ""
                        
                        with st.container():
                            st.markdown(f"<div class='list-card'>", unsafe_allow_html=True)
                            c1, c2, c3 = st.columns([1, 3, 1])
                            c1.write(f"**{status}**")
                            c2.write(f"Pick-Up {p_idx+1}: **Site {s.get('Site')}**{tag} \n{s.get('Street', 'Unknown Street')}")
                            
                            if c3.button("🔍 OPEN", key=f"jump_pickup_{s['UID']}", use_container_width=True):
                                st.session_state.pickup_index = p_idx
                                st.session_state.pickup_view_toggle = "Single Site Mode"
                                st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                    render_backup_button("pickup_bottom")
                else:
                    p_idx = st.session_state.pickup_index
                    if p_idx < len(itin):
                        if st.session_state.last_pickup_msg:
                            st.markdown(f"<div class='success-recap'>{st.session_state.last_pickup_msg}</div>", unsafe_allow_html=True)
                            
                        s = itin[p_idx]
                        p_lat, p_lon = s.get('LAT', s.get('lat')), s.get('LON', s.get('lon'))
                        tag = f" [{s.get('Sheet')}]" if show_origin_tag else ""
                        
                        st.subheader(f"PICK-UP #{p_idx+1}: Site {s.get('Site', s.get('id', 'Unknown'))}{tag}")
                        
                        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={p_lat},{p_lon}&dir_action=navigate"
                        st.link_button("🚗 NAV TO FIELD GPS", nav_url, use_container_width=True)
                        
                        if st.button("✅ SECURED", use_container_width=True, key=f"sec_{s['UID']}"):
                            st.session_state.site_data[s['UID']]["Picked up"] = "x"
                            st.session_state.last_pickup_msg = f"✅ Pick-Up {s.get('Site')} Confirmed."
                            st.session_state.pickup_index += 1
                            auto_save()
                            st.rerun()
                            
                        if s.get("Picked up") == "x":
                            if st.button("⏪ UNDO PICK-UP", use_container_width=True):
                                st.session_state.site_data[s['UID']]["Picked up"] = ""
                                auto_save()
                                st.rerun()
                        
                        st.divider()
                        p_nav1, p_nav2 = st.columns(2)
                        with p_nav1:
                            if p_idx > 0 and st.button("⬅️ PREV PICK-UP", use_container_width=True, key=f"p_prev_{s['UID']}"):
                                st.session_state.pickup_index -= 1
                                st.session_state.last_pickup_msg = None
                                auto_save()
                                st.rerun()
                        with p_nav2:
                            if p_idx < len(itin) - 1 and st.button("SKIP / NEXT ➡️", use_container_width=True, key=f"p_next_{s['UID']}"):
                                st.session_state.pickup_index += 1
                                st.session_state.last_pickup_msg = None
                                auto_save()
                                st.rerun()
                    else:
                        st.success("♻️ ALL PICK-UPS ARE SECURED!")
                        if p_idx > 0 and st.button("⬅️ REVIEW LAST PICK-UP", use_container_width=True):
                            st.session_state.pickup_index -= 1
                            auto_save()
                            st.rerun()
                    
                    render_backup_button("pickup_bottom_single")
                        
    elif main_view == "📊 EXCEL / AUDIT":
        st.subheader("📋 End of Day Audit")
        missing_data = []
        all_d = [d for d in st.session_state.site_data.values() if d.get("Installed") == "x" or d.get("Skipped") == "x"]
        
        for d in all_d:
            if d.get("Installed") == "x":
                if not d.get("Serial") or str(d.get("Serial")).strip() == "": 
                    missing_data.append(f"Site {d['Site']}: Missing Serial #")
                if not d.get("Street") or str(d.get("Street")).lower() == 'nan' or str(d.get("Street")).strip() == "": 
                    missing_data.append(f"Site {d['Site']}: Missing Street Name")
                
        if missing_data:
            st.error("⚠️ ACTION REQUIRED: You have missing data on installed sites.")
            for msg in missing_data: st.write(f"- {msg}")
        elif all_d:
            st.success("✅ All installed sites have complete data. Ready for export.")
            
        if all_d:
            try:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_all = pd.DataFrame(all_d)
                    
                    df_clean = df_all.drop(columns=['UID', 'Sheet'], errors='ignore')
                    df_clean.to_excel(writer, sheet_name='Master List', index=False)
                    
                    for sheet in df_all['Sheet'].unique():
                        df_sheet = df_all[df_all['Sheet'] == sheet].copy()
                        df_sheet_clean = df_sheet.drop(columns=['UID', 'Sheet'], errors='ignore')
                        safe_sheet_name = str(sheet)[:31].replace('[', '').replace(']', '').replace(':', '').replace('*', '').replace('?', '').replace('/', '').replace('\\', '')
                        df_sheet_clean.to_excel(writer, sheet_name=safe_sheet_name, index=False)
                        
                excel_data = output.getvalue()
                st.download_button(
                    label="📊 FINAL SUBMIT (DOWNLOAD EXCEL)", 
                    data=excel_data, 
                    file_name=f"TDS_Report_{st.session_state.driver_name}.xlsx", 
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                    use_container_width=True
                )
            except Exception as e:
                st.warning("Excel Engine blocked by Cloud Server. Generating standard CSV fallback.")
                df_csv = pd.DataFrame(all_d).drop(columns=['UID', 'Sheet'], errors='ignore')
                st.download_button(
                    label="📊 FINAL SUBMIT (DOWNLOAD CSV)", 
                    data=df_csv.to_csv(index=False), 
                    file_name=f"TDS_Report_{st.session_state.driver_name}.csv", 
                    use_container_width=True
                )
        
        render_backup_button("audit_bottom")
        
    elif is_commander and main_view == "👑 COMMANDER":
        st.subheader("👑 Commander Projection Engine")
        st.info("Live recalculation of your finalized shift based on completed work.")
        c_proj1, c_proj2, c_proj3 = st.columns(3)
        with c_proj1: shift_start = st.time_input("Shift Start Time:", value=datetime.strptime("08:00 AM", "%I:%M %p").time(), key="proj_start_fin")
        with c_proj2: avg_stop = st.number_input("Avg Mins per Stop:", value=15, min_value=1, key="proj_mins_fin")
        with c_proj3: 
            st.write("")
            run_proj = st.button("⏱️ PROJECT SHIFT", use_container_width=True, key="proj_btn_fin")
            
        if run_proj:
            start_dt = datetime.combine(datetime.today(), shift_start)
            
            def calc_time(nodes_to_route):
                if not nodes_to_route: return 0, 0
                coords = [(hc[0], hc[1])]
                for node in nodes_to_route:
                    coords.append((node['nav_lat'], node['nav_lon']))
                coords.append((hc[0], hc[1]))
                
                drive_sec = 0
                chunk_size = 50
                for i in range(0, len(coords) - 1, chunk_size - 1):
                    chunk = coords[i:i + chunk_size]
                    coords_str = ";".join([f"{lon},{lat}" for lat, lon in chunk])
                    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=false"
                    try:
                        resp = requests.get(osrm_url, timeout=3).json()
                        if resp.get('code') == 'Ok':
                            drive_sec += resp['routes'][0]['duration']
                        else: raise Exception()
                    except:
                        for j in range(len(chunk)-1):
                            dist = haversine_dist(chunk[j][0], chunk[j][1], chunk[j+1][0], chunk[j+1][1])
                            drive_sec += (dist / 48.28) * 3600 
                return drive_sec / 60.0, len(nodes_to_route) * avg_stop
            
            if st.session_state.upload_strategy == "🔗 Merge All Maps into One Route":
                if st.session_state.optimized_route:
                    d_mins, s_mins = calc_time(st.session_state.optimized_route)
                    end_dt = start_dt + timedelta(minutes=(d_mins + s_mins))
                    st.success(f"**MERGED ROUTE:** {len(st.session_state.optimized_route)} Total Stops")
                    st.write(f"🚗 Drive Time: {int(d_mins)} mins | 🛠️ Work Time: {int(s_mins)} mins")
                    st.info(f"🏁 **Projected Return Home: {end_dt.strftime('%I:%M %p')}**")
                else:
                    st.warning("No stops found in your route.")
            else:
                has_data = False
                for day in st.session_state.active_files:
                    day_nodes = [n for n in st.session_state.optimized_route if n['sheet'] == day]
                    if day_nodes:
                        has_data = True
                        d_mins, s_mins = calc_time(day_nodes)
                        end_dt = start_dt + timedelta(minutes=(d_mins + s_mins))
                        st.success(f"**{day}:** {len(day_nodes)} Total Stops")
                        st.write(f"🚗 Drive Time: {int(d_mins)} mins | 🛠️ Work Time: {int(s_mins)} mins")
                        st.info(f"🏁 **Projected Return Home: {end_dt.strftime('%I:%M %p')}**")
                if not has_data:
                    st.warning("No stops found in your route.")