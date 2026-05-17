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
from datetime import datetime
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
st.set_page_config(page_title="Traffic Data Service V51.99", layout="centered")

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

# --- 2. MASTER STATE SANITIZER (CRASH PREVENTION) ---
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
    "show_pickup_map": False,
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

# --- DUAL-ENGINE GEOCODER & REVERSE GEOCODER ---
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

# --- STRICT PROXIMITY CHAIN ROUTING ENGINE (FIXED NUMBERING) ---
def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371.0 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def solve_tsp(nodes_list, home_coords):
    """
    Pure Nearest-Neighbor sequence.
    Guarantees human-readable numbering by always jumping to the absolute closest dot.
    """
    if not nodes_list: return []
    
    unvisited = list(nodes_list)
    route = []
    curr = home_coords
    
    while unvisited:
        next_node = min(unvisited, key=lambda x: haversine_dist(curr[0], curr[1], x['nav_lat'], x['nav_lon']))
        route.append(next_node)
        curr = (next_node['nav_lat'], next_node['nav_lon'])
        unvisited.remove(next_node)
        
    return route

def process_upload(est_configs, excel_files, m_type, route_strategy):
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    st.session_state.last_install_msg = None
    st.session_state.last_pickup_msg = None
    st.session_state.upload_strategy = route_strategy 
    
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
                best_node = min(data['nodes'], key=lambda n: haversine_dist(st.session_state.home_coords[0], st.session_state.home_coords[1], n[0], n[1]))
                final_raw.append({
                    "id": sid, 
                    "uid": f"{cfg['label']}_{sid}", 
                    "nav_lat": best_node[0],
                    "nav_lon": best_node[1],
                    "sheet": cfg['label'], 
                    "street": data['street']
                })

    if final_raw:
        global_best_route = []
        if route_strategy == "📌 Keep Maps Separate (Day-by-Day)":
            for cfg in est_configs:
                sheet_name = cfg['label']
                sheet_raw = [x for x in final_raw if x['sheet'] == sheet_name]
                if not sheet_raw: continue
                sheet_route = solve_tsp(sheet_raw, st.session_state.home_coords)
                global_best_route.extend(sheet_route)
        else: 
            global_best_route = solve_tsp(final_raw, st.session_state.home_coords)
            
        st.session_state.optimized_route = global_best_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        
        st.session_state.site_data = {
            s['uid']: {
                "Date": "", "Time": "", "ExactTime": "", "Site": s['id'], "UID": s['uid'], "Counter": "c1b",
                "Serial": "", "Directions": "n", "Lanes": 2, "Street": s['street'], "Notes": "", "Installed": "",
                "LAT": s['nav_lat'], "LON": s['nav_lon'], "Skipped": "", "Sheet": s['sheet']
            } for s in global_best_route
        }
        
        st.session_state.mission_type = m_type
        st.session_state.current_index = 0
        st.session_state.pickup_index = 0
        auto_save()
        return True, len(global_best_route)
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
            
        keys_to_wipe = ["driver_name", "optimized_route", "site_data", "init", "pickup_index", "current_index", "active_files", "mission_type", "last_install_msg", "last_pickup_msg", "msg_type", "show_pickup_map", "pickup_sort_method", "pickup_target", "upload_strategy", "auto_advance_nav", "auto_open_url"]
        for k in keys_to_wipe:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

if st.session_state.get("auto_open_url"):
    components.html(f"<script>window.open('{st.session_state.auto_open_url}', '_blank');</script>", height=0)
    st.session_state.auto_open_url = ""

if not st.session_state.get("optimized_route"):
    restore_file = st.file_uploader("🔄 RESTORE BACKUP", type=["json"])
    if restore_file and st.button("🔓 LOAD BACKUP"):
        data = json.loads(restore_file.getvalue())
        for k, v in data.items(): st.session_state[k] = v
        st.rerun()
        
    st.divider()
    
    st.subheader("🏠 1. SET STARTING POINT")
    st.write(f"**Saved Origin:** `{st.session_state.home_coords[0]:.5f}, {st.session_state.home_coords[1]:.5f}`")
    
    tab_gps, tab_addr, tab_coords = st.tabs(["📍 1-Tap GPS", "🏠 Search Address", "✏️ Manual Coords"])
    
    with tab_gps:
        st.write("Grab your live phone/truck location:")
        if HAS_GPS:
            # NO KEY PARAMETER: Fixes TypeError Crash
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
        if st.button("🚀 SYNC TACTICAL MAP"):
            success, count = process_upload(configs, excel_files, m_type, r_strat)
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
        
    map_tiles = "CartoDB dark_matter" if st.session_state.theme == "☁️ Overcast (Standard)" else "CartoDB positron"
    
    if st.session_state.get("upload_strategy") == "🔗 Merge All Maps into One Route":
        available_days = ["All Days"]
        selected_day = "All Days"
        st.info("🔗 Mission Filter locked: All maps merged into a single route.")
    else:
        available_days = ["All Days"] + st.session_state.active_files
        selected_day = st.selectbox("📅 MISSION FILTER:", available_days)
    
    active_route = st.session_state.optimized_route if selected_day == "All Days" else [s for s in st.session_state.optimized_route if s['sheet'] == selected_day]
    active_uids = [s['uid'] for s in active_route]
    
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL / AUDIT"])
    
    with tab1:
        st.success(f"STOPS IN VIEW: {len(active_route)}")
        
        hc = st.session_state.home_coords
        m = folium.Map(location=hc, zoom_start=11, tiles=map_tiles)
        folium.Marker(hc, popup="STARTING POINT", icon=folium.Icon(color="blue", icon="home")).add_to(m)
        route_coords = [hc]
        
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
        
        st_folium(m, height=450, use_container_width=True, returned_objects=[], key="main_route_map")
            
        for idx, s in enumerate(active_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            skipped = sd.get("Skipped") == "x"
            status_icon = '❌' if skipped else ('✅' if done else '🟠')
            if st.button(f"{status_icon} Stop {idx+1}: {sd.get('Site', s['id'])}", key=f"m_{s['uid']}_{st.session_state.session_id}", use_container_width=True):
                st.session_state.current_index = next((i for i, stop in enumerate(st.session_state.optimized_route) if stop['uid'] == s['uid']), 0)
                st.rerun()
                
        if st.button("🗑️ RESET ROUTE (CLEAR DEVICE)"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.session_state.optimized_route = []
            st.rerun()
            
    with tab2:
        install_view = st.radio("Install View:", ["Single Site Mode", "Full Manifest List"], horizontal=True)
        
        if install_view == "Full Manifest List":
            df_display = pd.DataFrame([{
                "Site": s["Site"], 
                "Street": s["Street"], 
                "Status": "✅ Installed" if s.get("Installed") == "x" else ("❌ Skipped" if s.get("Skipped") == "x" else "⏳ Pending")
            } for s in [st.session_state.site_data[uid] for uid in active_uids]])
            st.dataframe(df_display, use_container_width=True)
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
                
                st.subheader(f"#{cur+1}: Site {sd.get('Site', s['id'])}")
                
                display_street = str(sd.get('Street', f"Site {s['id']}"))
                if display_street.lower() == 'nan': display_street = ""
                new_street = st.text_input("📍 STREET NAME (Auto-Fills on Install):", value=display_street)
                
                # FIXED: Force Maps to use Current Location and bypass preview
                nav_url = f"https://www.google.com/maps/dir/?api=1&origin=Current+Location...{safe_lat},{safe_lon}&dir_action=navigate"
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
                    batch_url = f"https://www.google.com/maps/dir/?api=1&origin=Current+Location...{dest_str}&waypoints={requests.utils.quote(waypoints_str)}&dir_action=navigate"
                    st.link_button(f"🗺️ BATCH NAV (Next {len(batch)} Stops)", batch_url, use_container_width=True)
                
                st.info("📍 Grab precise GPS below to lock-in the exact field coordinate and auto-name the street.")
                if HAS_GPS:
                    # NO KEY PARAMETER: Crash Prevented
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
                                    st.session_state.auto_open_url = f"https://www.google.com/maps/dir/?api=1&origin=Current+Location...{n_lat},{n_lon}&dir_action=navigate"

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
                    
    with tab3:
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
                itin = [site['sd'] for site in solve_tsp([{'uid': sd['UID'], 'nav_lat': float(sd['LAT']), 'nav_lon': float(sd['LON']), 'sd': sd} for sd in raw_itin], st.session_state.home_coords)]
                
            if st.session_state.pickup_index >= len(itin):
                st.session_state.pickup_index = max(0, len(itin) - 1)

            st.divider()

            if itin and st.button("🗺️ GENERATE PICK-UP MAP MANIFEST", use_container_width=True):
                st.session_state.show_pickup_map = not st.session_state.get("show_pickup_map", False)
                
            if st.session_state.get("show_pickup_map", False) and itin:
                st.success(f"TACTICAL PICK-UP MAP: {len(itin)} Secured Sites")
                m_pickup = folium.Map(location=st.session_state.home_coords, zoom_start=11, tiles=map_tiles)
                folium.Marker(st.session_state.home_coords, popup="STARTING POINT", icon=folium.Icon(color="blue", icon="home")).add_to(m_pickup)
                
                pickup_coords = [st.session_state.home_coords]
                for idx, p_site in enumerate(itin):
                    p_lat, p_lon = p_site.get('LAT'), p_site.get('LON')
                    is_picked_up = p_site.get("Picked up") == "x"
                    color = "#00FF00" if is_picked_up else "#FFA500" 
                    
                    if p_lat and p_lon:
                        pickup_coords.append((p_lat, p_lon))
                        folium.CircleMarker(
                            location=(p_lat, p_lon), radius=10, color=color, fill=True, fill_color=color, fill_opacity=0.9,
                            popup=f"Pick-Up {idx+1}: Site {p_site.get('Site')}"
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
                
                st_folium(m_pickup, height=450, use_container_width=True, returned_objects=[], key="pickup_map_render")
                st.divider()
            elif not itin:
                st.warning("No installed sites found for the selected Pick-Up target.")

            if itin:
                view_mode = st.radio("Pick-Up View:", ["Single Site Mode", "Full Manifest List"], horizontal=True)
                
                if view_mode == "Full Manifest List":
                    st.dataframe(pd.DataFrame([{
                        "Site": s["Site"], "Street": s["Street"], "Status": "✅ Done" if s.get("Picked up") == "x" else "⏳ Pending"
                    } for s in itin]), use_container_width=True)
                else:
                    p_idx = st.session_state.pickup_index
                    if p_idx < len(itin):
                        if st.session_state.last_pickup_msg:
                            st.markdown(f"<div class='success-recap'>{st.session_state.last_pickup_msg}</div>", unsafe_allow_html=True)
                            
                        s = itin[p_idx]
                        p_lat, p_lon = s.get('LAT', s.get('lat')), s.get('LON', s.get('lon'))
                        st.subheader(f"PICK-UP #{p_idx+1}: Site {s.get('Site', s.get('id', 'Unknown'))}")
                        
                        nav_url = f"https://www.google.com/maps/dir/?api=1&origin=Current+Location...{p_lat},{p_lon}&dir_action=navigate"
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
                        
    with tab4:
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
        
        st.divider()
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, "r") as f: backup_data = f.read()
                st.download_button("💾 DOWNLOAD BACKUP JSON", backup_data, f"tds_backup_{st.session_state.driver_name}.json", mime="application/json", use_container_width=True)
            except Exception: pass