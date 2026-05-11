import streamlit as st
import re
import pandas as pd
import json
import io
import time
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_geolocation import streamlit_geolocation

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V51.61 Intersection Snapper", layout="centered")

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
    # ATOMIC RESET
    st.session_state.optimized_route = []
    st.session_state.site_data = {}
    
    excel_data = {}
    for f in excel_files:
        try:
            df = pd.read_csv(f, encoding='latin-1') if f.name.lower().endswith('.csv') else pd.read_excel(f)
            
            # Find the ID and coordinate columns
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
                            
                            # Verify valid California GPS limits for Begin
                            if 30.0 < b_lat < 40.0 and -125.0 < b_lon < -110.0:
                                nodes = [(b_lat, b_lon)] # Add the Begin point
                                
                                # If End points exist, add them to the options
                                if e_lat_c and e_lon_c and pd.notna(row[e_lat_c]) and pd.notna(row[e_lon_c]):
                                    e_lat, e_lon = float(row[e_lat_c]), float(row[e_lon_c])
                                    if 30.0 < e_lat < 40.0 and -125.0 < e_lon < -110.0:
                                        nodes.append((e_lat, e_lon)) # Add the End point
                                
                                street_name = str(row.get('Street', f'Site {sid}'))
                                # Save BOTH exact, verified street points for the engine to test
                                excel_data[sid] = {"nodes": nodes, "street": street_name}
                        except:
                            pass
        except: pass

    if not excel_data: return False, 0

    final_raw = []
    for cfg in est_configs:
        raw_map = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for sid, data in excel_data.items():
            
            # Strict boundary check so Site '23' doesn't match '2335'
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
        # FASTEST ROUTE ALGORITHM: Start home -> test both ends of the street -> pick the nearest -> repeat.
        master_route, curr = [], HOME_COORDS
        while final_raw:
            best_site, best_dist, best_node = None, float('inf'), None
            for site in final_raw:
                for node in site['nodes']:
                    d = (curr[0]-node[0])**2 + (curr[1]-node[1])**2
                    if d < best_dist:
                        best_dist, best_site, best_node = d, site, node
            
            # Lock in the end of the street that was closest to the truck
            best_site['nav_lat'], best_site['nav_lon'] = best_node
            master_route.append(best_site)
            curr = best_node
            final_raw.remove(best_site)
            
        st.session_state.optimized_route = master_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.site_data = {s['uid']: {"Date":"","Time":"","ExactTime":"","Site":s['id'],"UID":s['uid'],"Counter":"c1b","Serial":"","Directions": "n", "Lanes":2,"Street":s['street'],"Notes":"","Installed":"","LAT":s['nav_lat'],"LON":s['nav_lon'],"Skipped":False,"Sheet":s['sheet']} for s in master_route}
        st.session_state.mission_type, st.session_state.current_index, st.session_state.pickup_index = m_type, 0, 0
        auto_save(); return True, len(master_route)
    return False, 0

# --- UI ---
if not st.session_state.get("optimized_route"):
    st.title("🚦 Live Wire Stability")
    restore_file = st.file_uploader("🔄 RESTORE", type=["json"])
    if restore_file and st.button("🔓 LOAD"):
        data = json.loads(restore_file.getvalue()); [st.session_state.update({k: v}) for k, v in data.items()]; st.rerun()
    st.divider()
    m_type = st.radio("MISSION:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    excel_files = st.file_uploader("1️⃣ EXCEL DATA", accept_multiple_files=True)
    up_files = st.file_uploader("2️⃣ MAPS (.EST)", accept_multiple_files=True)
    if up_files and excel_files:
        configs = [{"file": f, "label": st.text_input(f"Map {i+1}:", value=f"Map {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        if st.button("🚀 SYNC STABLE"):
            success, count = process_upload(configs, excel_files, m_type)
            if success: st.success(f"Locked {count} sites."); time.sleep(1); st.rerun()
            else: st.error("Sync error. No matching sites found.")
else:
    new_theme = st.radio("MODE:", ["☁️ Overcast", "🌞 Bright Sun"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: st.session_state.theme = new_theme; auto_save(); st.rerun()
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])
    
    with tab1:
        st.success(f"STOPS: {len(st.session_state.optimized_route)}")
        map_points = [{"lat": HOME_COORDS[0], "lon": HOME_COORDS[1], "color": "#FFFFFF", "size": 12}]
        for s in st.session_state.optimized_route:
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            safe_lat = sd.get('LAT', sd.get('lat'))
            safe_lon = sd.get('LON', sd.get('lon'))
            if safe_lat and safe_lon:
                map_points.append({"lat": safe_lat, "lon": safe_lon, "color": "#00FF00" if done else "#FFA500", "size": 8})
        
        if map_points:
            st.map(pd.DataFrame(map_points), color="color", size="size")
            
        for idx, s in enumerate(st.session_state.optimized_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd.get("Installed") == "x" or sd.get("Picked up") == "x"
            if st.button(f"{'✅' if done else '🟠'} Stop {idx+1}: {sd.get('Site', s['id'])}", key=f"m_{idx}", use_container_width=True):
                st.session_state.current_index = idx; st.rerun()
        if st.button("🗑️ RESET"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.session_state.optimized_route = []; st.rerun()
            
    with tab2:
        cur = st.session_state.current_index
        if cur < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur]
            sd = st.session_state.site_data[s['uid']]
            safe_lat = sd.get('LAT', sd.get('lat'))
            safe_lon = sd.get('LON', sd.get('lon'))
            
            st.subheader(f"#{cur+1}: Site {sd.get('Site', s['id'])}")
            st.link_button("🚗 NAV TO INTERSECTION NODE", f"https://www.google.com/maps/search/?api=1&query={safe_lat},{safe_lon}", use_container_width=True)
            
            batch = []
            for bs in st.session_state.optimized_route[cur:cur+9]:
                bsd = st.session_state.site_data[bs['uid']]
                if bsd.get('Installed') != "x":
                    b_lat = bsd.get('LAT', bsd.get('lat'))
                    b_lon = bsd.get('LON', bsd.get('lon'))
                    if b_lat and b_lon:
                        batch.append(f"{b_lat},{b_lon}")
                        
            if len(batch) > 1: st.link_button(f"🗺️ BATCH NAV", "https://www.google.com/maps/dir/" + "/".join(batch), use_container_width=True)
            
            loc = streamlit_geolocation()
            with st.form(f"f_{cur}"):
                dr = st.selectbox("DIR", ["n","e","s","w"])
                ln = st.number_input("LANES", min_value=1, value=2)
                ser, nt = st.text_input("SERIAL #"), st.text_input("NOTES")
                if st.form_submit_button("✅ COMPLETE", use_container_width=True):
                    _, d, et = get_ca_time()
                    st.session_state.site_data[s['uid']].update({
                        "Date":d, "ExactTime":et, "Directions":dr, "Serial":ser, "Lanes":ln, "Notes":nt, "Installed":"x", 
                        "LAT":loc['latitude'] if loc and loc.get('latitude') else safe_lat, 
                        "LON":loc['longitude'] if loc and loc.get('longitude') else safe_lon
                    })
                    st.session_state.current_index += 1; auto_save(); st.rerun()
                    
    with tab3:
        itin = [sd for sd in st.session_state.site_data.values() if sd.get("Installed") == "x"]
        if itin:
            p_idx = st.session_state.pickup_index
            if p_idx < len(itin):
                s = itin[p_idx]
                p_lat = s.get('LAT', s.get('lat'))
                p_lon = s.get('LON', s.get('lon'))
                st.subheader(f"PICK-UP #{p_idx+1}: Site {s.get('Site', s.get('id', 'Unknown'))}")
                st.link_button("🚗 NAV", f"https://www.google.com/maps/search/?api=1&query={p_lat},{p_lon}", use_container_width=True)
                if st.button("✅ SECURED", use_container_width=True):
                    st.session_state.site_data[s['UID']]["Picked up"] = "x"; st.session_state.pickup_index += 1; auto_save(); st.rerun()
                    
    with tab4:
        all_d = [d for d in st.session_state.site_data.values() if d.get("Installed") == "x"]
        if all_d:
            st.download_button("📊 DOWNLOAD EXCEL", pd.DataFrame(all_d).to_csv(index=False), "Report.csv", use_container_width=True)
