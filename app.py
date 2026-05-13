import streamlit as st
import re
import pandas as pd
import json
import time
import os
import random
import requests
import folium
import uuid
from folium.features import DivIcon
from streamlit_folium import st_folium
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_geolocation import streamlit_geolocation

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V51.81 Address Locator", layout="centered")

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
    st.stop()

BACKUP_FILE = f"live_wire_backup_{st.session_state.driver_name}.json"

# --- 2. STATE MANAGEMENT ---
if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except Exception: pass
        
    if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())[:8]
    if "home_coords" not in st.session_state: st.session_state.home_coords = (33.7715, -117.9431) 
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
    payload = {
        "home_coords": st.session_state.get("home_coords", (33.7715, -117.9431)),
        "active_files": st.session_state.get("active_files", []),
        "optimized_route": st.session_state.get("optimized_route", []),
        "site_data": st.session_state.get("site_data", {}),
        "current_index": st.session_state.get("current_index", 0),
        "mission_type": st.session_state.get("mission_type", "📍 INSTALLATION"),
        "pickup_index": st.session_state.get("pickup_index", 0),
        "pickup_itinerary": st.session_state.get("pickup_itinerary", []),
        "theme": st.session_state.get("theme", "☁️ Overcast (Standard)")
    }
    try:
        with open(BACKUP_FILE, "w") as f:
            json.dump(payload, f, default=str)
    except Exception as e: 
        print(f"Save Error: {e}")

# --- ELITE CLUSTER SOLVER ---
def calc_scaled_dist(lat1, lon1, lat2, lon2):
    return ((lon1 - lon2) * 0.832)**2 + (lat1 - lat2)**2

def calc_total_distance(path):
    if not path: return 0
    hc = st.session_state.home_coords
    d = calc_scaled_dist(hc[0], hc[1], path[0]['nav_lat'], path[0]['nav_lon'])
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
        master_route, curr = [], st.session_state.home_coords
        temp_raw = list(final_raw)
        while temp_raw:
            best_site = min(temp_raw, key=lambda x: calc_scaled_dist(curr[0], curr[1], x['nodes'][0][0], x['nodes'][0][1]))
            best_node = min(best_site['nodes'], key=lambda n: calc_scaled_dist(curr[0], curr[1], n[0], n[1]))
            best_site['nav_lat'], best_site['nav_lon'] = best_node
            master_route.append(best_site)
            curr = best_node
            temp_raw.remove(best_site)
            
        best_route, best_dist = untangle_route(master_route)
        
        restarts = 5 if len(master_route) > 50 else 15
        for _ in range(restarts):
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
                "Date": "", "Time": "", "ExactTime": "", "Site": s['id'], "UID": s['uid'], "Counter": "c1b",
                "Serial": "", "Directions": "n", "Lanes": 2, "Street": s['street'], "Notes": "", "Installed": "",
                "LAT": s['nav_lat'], "LON": s['nav_lon'], "Skipped": "", "Sheet": s['sheet']
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
    ln = current_ln
    ln_match = re.search(r'(\d+)\s*lane', t)
    if ln_match: ln = int(ln_match.group(1))
    ser = current_ser
    ser_match = re.search(r'serial.*?(\w+)', t)
    if ser_match: ser = str(ser_match.group(1)).upper()
    return dr, ln, ser

# --- NAVIGATION HELPER ---
def get_next_valid_index(current_idx, active_uids, direction=1):
    if not active_uids: return current_idx
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
        keys_to_delete = list(st.session_state.keys())
        for k in keys_to_delete:
            del st.session_state[k]
        st.rerun()

if not st.session_state.get("optimized_route"):
    restore_file = st.file_uploader("🔄 RESTORE BACKUP", type=["json"])
    if restore_file and st.button("🔓 LOAD BACKUP"):
        data = json.loads(restore_file.getvalue())
        for k, v in data.items(): st.session_state[k] = v
        st.rerun()
        
    st.divider()
    
    # --- MANUAL ORIGIN SETUP (NO GPS CRASHES) ---
    st.subheader("🏠 1. SET STARTING POINT")
    st.write(f"**Current Saved Origin:** `{st.session_state.home_coords[0]:.5f}, {st.session_state.home_coords[1]:.5f}`")
    
    tab_addr, tab_coords = st.tabs(["📍 Search Address", "✏️ Enter Coordinates"])
    
    with tab_addr:
        address_input = st.text_input("Enter Starting Address (Home or Dispatch Yard):", placeholder="e.g., 123 Main St, Garden Grove, CA")
        if st.button("🔍 LOCATE & SAVE ADDRESS", use_container_width=True):
            if address_input:
                try:
                    url = f"https://nominatim.openstreetmap.org/search?format=json&q={requests.utils.quote(address_input)}"
                    resp = requests.get(url, headers={'User-Agent': 'LiveWire-Ops'}).json()
                    if resp:
                        st.session_state.home_coords = (float(resp[0]['lat']), float(resp[0]['lon']))
                        auto_save()
                        st.success("✅ Origin Updated!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Address not found. Try adding the city and state.")
                except Exception:
                    st.error("❌ Network error. Please use the Coordinates tab.")

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
    excel_files = st.file_uploader("EXCEL DATA", accept_multiple_files=True)
    up_files = st.file_uploader("MAPS (.EST)", accept_multiple_files=True)
    
    if up_files and excel_files:
        configs = [{"file": f, "label": st.text_input(f"Map {i+1} Name (e.g. Day 1):", value=f"Day {i+1}", key=f"l_{i}_{st.session_state.session_id}")} for i, f in enumerate(up_files)]
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
    active_uids = [s['uid'] for s in active_route]
    
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL / AUDIT"])
    
    with tab1:
        st.success(f"STOPS IN VIEW: {len(active_route)}")
        
        hc = st.session_state.home_coords
        m = folium.Map(location=hc, zoom_start=11, tiles="CartoDB dark_matter")
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
        
        st_folium(m, height=450, use_container_width=True, returned_objects=[])
            
        for idx, s in enumerate(active_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            skipped = sd.get("Skipped") == "x"
            status_icon = '❌' if skipped else ('✅' if done else '🟠')
            if st.button(f"{status_icon} Stop {idx+1}: {sd.get('Site', s['id'])}", key=f"m_{s['uid']}_{st.session_state.session_id}", use_container_width=True):
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
            
            st.info("🎙️ **VOICE PARSER:** Tap the box, use phone keyboard mic, and speak. Example: *'Facing south, 4 lanes, serial 5678, wide road'*")
            dictation = st.text_area("Field Notes / Dictation:")
            
            # Left the Geolocation widget here purely for logging field coordinates. 
            # If this also causes crashes, let me know and we will amputate this one too.
            loc = streamlit_geolocation(key=f"loc_{s['uid']}_{st.session_state.session_id}")
            
            with st.form(f"f_{s['uid']}_{st.session_state.session_id}"):
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
                        "Date": d, "ExactTime": et, "Directions": dr, "Serial": str(ser), "Lanes": ln, 
                        "Notes": str(dictation), "Installed": "x" if submit_btn else "", "Skipped": "x" if skip_btn else "",
                        "LAT": final_lat, "LON": final_lon
                    })
                    
                    if submit_btn:
                        st.session_state.msg_type = "success"
                        st.session_state.last_install_msg = f"✅ Site {sd.get('Site', s['id'])} SECURED."
                    else:
                        st.session_state.msg_type = "skip"
                        st.session_state.last_install_msg = f"❌ Site {sd.get('Site', s['id'])} SKIPPED. Reason logged."
                        
                    st.session_state.current_index = get_next_valid_index(cur, active_uids, direction=1)
                    auto_save()
                    st.rerun()
            
            st.divider()
            nav1, nav2 = st.columns(2)
            with nav1:
                if st.button("⬅️ PREV STOP", use_container_width=True):
                    st.session_state.current_index = get_next_valid_index(cur, active_uids, direction=-1)
                    st.session_state.last_install_msg = None
                    auto_save()
                    st.rerun()
            with nav2:
                if st.button("NEXT ➡️", use_container_width=True):
                    st.session_state.current_index = get_next_valid_index(cur, active_uids, direction=1)
                    st.session_state.last_install_msg = None
                    auto_save()
                    st.rerun()
                    
    with tab3:
        itin = [sd for sd in st.session_state.site_data.values() if sd.get("Installed") == "x"]
        if itin:
            view_mode = st.radio("Pick-Up View:", ["Active Route", "Full Manifest List"], horizontal=True)
            
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
                    st.link_button("🚗 NAV", f"https://www.google.com/maps/search/?api=1&query={p_lat},{p_lon}", use_container_width=True)
                    
                    if st.button("✅ SECURED", use_container_width=True):
                        st.session_state.site_data[s['UID']]["Picked up"] = "x"
                        st.session_state.last_pickup_msg = f"✅ Pick-Up {s.get('Site')} Confirmed."
                        st.session_state.pickup_index += 1
                        auto_save()
                        st.rerun()
                    
                    st.divider()
                    p_nav1, p_nav2 = st.columns(2)
                    with p_nav1:
                        if p_idx > 0 and st.button("⬅️ PREV PICK-UP", use_container_width=True):
                            st.session_state.pickup_index -= 1
                            st.session_state.last_pickup_msg = None
                            auto_save()
                            st.rerun()
                    with p_nav2:
                        if p_idx < len(itin) - 1 and st.button("SKIP / NEXT ➡️", use_container_width=True):
                            st.session_state.pickup_index += 1
                            st.session_state.last_pickup_msg = None
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
            st.download_button("📊 FINAL SUBMIT (DOWNLOAD EXCEL)", pd.DataFrame(all_d).to_csv(index=False), "Report.csv", use_container_width=True)
        
        st.divider()
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, "r") as f: backup_data = f.read()
                st.download_button("💾 DOWNLOAD BACKUP JSON", backup_data, f"live_wire_backup_{st.session_state.driver_name}.json", mime="application/json", use_container_width=True)
            except Exception: pass
