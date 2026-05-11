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
st.set_page_config(page_title="Live Wire V51.9 Operator Core", layout="centered")

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

st.markdown(set_theme(st.session_state.theme), unsafe_allow_html=True)

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    return now.strftime("%H00"), now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")

def get_bearing(lat1, lon1, lat2, lon2):
    if abs(lat1 - lat2) < 0.00001 and abs(lon1 - lon2) < 0.00001: return "n" 
    dLon = math.radians(lon2 - lon1)
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    y = math.sin(dLon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dLon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    return "n" if (315 <= bearing <= 360) or (0 <= bearing < 45) or (135 <= bearing < 225) else "e"

def get_closest_point_on_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0: return ax, ay
    dist_sq = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dist_sq))
    return ax + t * dx, ay + t * dy

def process_upload(est_configs, excel_files, m_type):
    all_raw_master = []
    master_site_ids = []
    
    # 1. FAIL-SAFE EXCEL/TEXT READER
    if excel_files:
        for f in excel_files:
            try:
                # Try modern Excel
                if f.name.lower().endswith('.xlsx'):
                    df = pd.read_excel(f, engine='openpyxl')
                    ids = df.iloc[:, 0].dropna().astype(str).str.replace(r'\.0$', '', regex=True).tolist()
                    master_site_ids.extend([i.strip() for i in ids if i.strip().isdigit()])
                # Try CSV
                elif f.name.lower().endswith('.csv'):
                    df = pd.read_csv(f, encoding='latin-1')
                    ids = df.iloc[:, 0].dropna().astype(str).str.replace(r'\.0$', '', regex=True).tolist()
                    master_site_ids.extend([i.strip() for i in ids if i.strip().isdigit()])
                # Try Old Excel Fallback OR Raw Text Vacuum
                else:
                    try:
                        df = pd.read_excel(f) # Requires xlrd
                        ids = df.iloc[:, 0].dropna().astype(str).str.replace(r'\.0$', '', regex=True).tolist()
                        master_site_ids.extend([i.strip() for i in ids if i.strip().isdigit()])
                    except:
                        # V51.9: VACUUM MODE - If library fails, just read the binary as text and grab numbers
                        st.warning(f"⚠️ Direct import failed for {f.name}. Using Text-Vacuum mode...")
                        raw_content = f.getvalue().decode('latin-1', errors='ignore')
                        # Grab all 4 or 5 digit integers
                        found_nums = re.findall(r'\b\d{4,5}\b', raw_content)
                        master_site_ids.extend(found_nums)
            except Exception as e:
                st.error(f"Failed to read {f.name}: {str(e)}")

    master_site_ids = sorted(list(set(master_site_ids))) # Unique sites
    if not master_site_ids: return False, 0

    # 2. AGGRESSIVE MAP SCRAPER
    for cfg in est_configs:
        try:
            raw_bytes = cfg['file'].getvalue()
            text = re.sub(r'\s+', ' ', raw_bytes.decode('latin-1', errors='ignore').replace('\x00', ' '))
            
            for sid in master_site_ids:
                match = re.search(r'\b' + sid + r'\b(.{1,1500})', text)
                if match:
                    coords = [float(x) for x in re.findall(r'-?\d{2,3}\.\d{4,}', match.group(1))]
                    lats = [c for c in coords if 32.0 < c < 35.5]
                    lons = [c for c in coords if -120.0 < c < -114.0]
                    
                    if lats and lons:
                        all_raw_master.append({
                            "id": sid,
                            "lat_start": lats[0], "lon_start": lons[0],
                            "lat_end": lats[-1], "lon_end": lons[-1],
                            "sheet": cfg['label'], "lanes": 2
                        })
        except: pass

    if all_raw_master:
        df = pd.DataFrame(all_raw_master).drop_duplicates(subset=['id', 'sheet'])
        df['uid'] = df['sheet'] + "_" + df['id']
        master_rem, master_route, curr = df.to_dict('records'), [], HOME_COORDS
        
        while master_rem:
            best_nxt, best_dist, best_target = None, float('inf'), None
            for x in master_rem:
                tx, ty = get_closest_point_on_segment(curr[0], curr[1], x['lat_start'], x['lon_start'], x['lat_end'], x['lon_end'])
                dist = (curr[0] - tx)**2 + (curr[1] - ty)**2
                if dist < best_dist: best_dist, best_nxt, best_target = dist, x, (tx, ty)
            best_nxt['nav_lat'], best_nxt['nav_lon'] = best_target
            master_route.append(best_nxt); curr = best_target; master_rem.remove(best_nxt)
        
        st.session_state.optimized_route = master_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.site_data = {s['uid']: {"Date":"","Time":"","ExactTime":"","Site":s['id'],"UID":s['uid'],"Counter":"c1b","Serial":"","Directions": get_bearing(s['lat_start'], s['lon_start'], s['lat_end'], s['lon_end']), "Lanes":2,"Street":"","Notes":"","Installed":"","Lat_Start":s['lat_start'], "Lon_Start":s['lon_start'],"Lat_End":s['lat_end'], "Lon_End":s['lon_end'],"Picked up":"","LAT":s['nav_lat'],"LON":s['nav_lon'],"Skipped":False,"Sheet":s['sheet']} for s in master_route}
        st.session_state.mission_type, st.session_state.current_index, st.session_state.pickup_index = m_type, 0, 0
        auto_save(); return True, len(master_route)
    return False, 0

# --- UI ---
if not st.session_state.get("optimized_route"):
    st.title("🚦 SECURE UPLOAD")
    restore_file = st.file_uploader("🔄 RESTORE (.JSON)", type=["json"])
    if restore_file and st.button("🔓 LOAD"):
        try:
            data = json.loads(restore_file.getvalue()); [st.session_state.update({k: v}) for k, v in data.items()]; st.rerun()
        except: st.error("Error")
    st.divider()
    m_type = st.radio("MISSION TYPE:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    excel_files = st.file_uploader("1️⃣ DATA (SITES IN COL A OR RAW XLS)", accept_multiple_files=True)
    up_files = st.file_uploader("2️⃣ MAPS (.EST / .TXT)", accept_multiple_files=True)
    if up_files and excel_files:
        configs = [{"file": f, "label": st.text_input(f"Label for Map {i+1}:", value=f"Map {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        if st.button("🚀 SYNC"):
            success, count = process_upload(configs, excel_files, m_type)
            if success: st.success(f"Locked {count} Sites."); time.sleep(1); st.rerun()
            else: st.error("Sync Failed. Please save Excel as .CSV for best results.")
else:
    new_theme = st.radio("📱 DISPLAY:", ["☁️ Overcast (Standard)", "🌞 Bright Sun (OLED Contrast)"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: st.session_state.theme = new_theme; auto_save(); st.rerun()
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])
    with tab1:
        st.success(f"{st.session_state.mission_type} | {len(st.session_state.optimized_route)} STOPS")
        map_points = [{"lat": HOME_COORDS[0], "lon": HOME_COORDS[1], "color": "#FFFFFF"}]
        for s in st.session_state.optimized_route:
            sd = st.session_state.site_data[s['uid']]
            color = "#00FF00" if (sd["Picked up"] == "x" if "PICK-UP" in st.session_state.mission_type else sd["Installed"] == "x") else ("#FF0000" if sd.get("Skipped") else "#FFA500")
            map_points.append({"lat": sd['LAT'], "lon": sd['LON'], "color": color})
        st.map(pd.DataFrame(map_points), color="color")
        for idx, s in enumerate(st.session_state.optimized_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd["Picked up"] == "x" if "PICK-UP" in st.session_state.mission_type else sd["Installed"] == "x"
            if st.button(f"{'✅' if done else '🟠'} {idx+1}: Site {sd['Site']}", key=f"m_{idx}", use_container_width=True):
                st.session_state.current_index = idx; st.rerun()
        st.download_button("💾 DOWNLOAD MASTER SHIFT FILE", json.dumps({k: st.session_state.get(k) for k in ["active_files", "optimized_route", "site_data", "current_index", "mission_type", "pickup_index", "pickup_itinerary", "theme"]}), f"LiveWire_Save.json", use_container_width=True)
        if st.button("🗑️ CLEAR"):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.session_state.optimized_route = []; st.rerun()
    with tab2:
        cur = st.session_state.current_index
        if cur < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur]; sd = st.session_state.site_data[s['uid']]
            st.subheader(f"#{cur+1}: SITE {sd['Site']}")
            st.link_button("🚗 SINGLE NAV", f"https://www.google.com/maps/search/?api=1&query={sd['LAT']},{sd['LON']}", use_container_width=True)
            batch = [f"{st.session_state.site_data[bs['uid']]['LAT']},{st.session_state.site_data[bs['uid']]['LON']}" for bs in st.session_state.optimized_route[cur:cur+9] if st.session_state.site_data[bs['uid']]['Installed'] != "x"]
            if len(batch) > 1: st.link_button(f"🗺️ BATCH NAV {len(batch)}", "https://www.google.com/maps/dir/" + "/".join(batch), use_container_width=True)
            loc = streamlit_geolocation()
            with st.form(f"f_{cur}"):
                c1, c2 = st.columns(2)
                dr = c1.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(sd["Directions"]))
                ln = c2.number_input("LANES", min_value=1, value=int(sd["Lanes"]))
                ser, nt = st.text_input("SERIAL #", value=sd["Serial"]), st.text_input("NOTES", value=sd["Notes"])
                if st.form_submit_button("✅ COMPLETE", use_container_width=True):
                    _, d, et = get_ca_time()
                    st.session_state.site_data[s['uid']].update({"Date":d, "ExactTime":et, "Directions":dr, "Serial":ser, "Lanes":ln, "Notes":nt, "Installed":"x", "LAT":loc['latitude'] if loc and loc.get('latitude') else sd['LAT'], "LON":loc['longitude'] if loc and loc.get('longitude') else sd['LON'], "Skipped":False})
                    st.session_state.current_index += 1; auto_save(); st.rerun()
    with tab3:
        if not st.session_state.get('pickup_itinerary'):
            st.session_state.pickup_itinerary = [sd for sd in st.session_state.site_data.values() if sd.get("Installed") == "x"]
        itin = st.session_state.pickup_itinerary
        if itin:
            p_idx = st.session_state.pickup_index
            if p_idx < len(itin):
                s = itin[p_idx]; uid = s['UID']
                st.subheader(f"PICK-UP #{p_idx+1}: SITE {s['Site']}")
                st.link_button("🚗 NAV", f"https://www.google.com/maps/search/?api=1&query={s['LAT']},{s['LON']}", use_container_width=True)
                if st.button("✅ SECURED", use_container_width=True):
                    st.session_state.site_data[uid].update({"Picked up":"x"}); st.session_state.pickup_index += 1; auto_save(); st.rerun()
    with tab4:
        all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x" or d.get("Skipped")]
        if all_d:
            full_df = pd.DataFrame(all_d)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for sheet_name in st.session_state.active_files:
                    sheet_df = full_df[full_df["Sheet"] == sheet_name]
                    if not sheet_df.empty: sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)
            st.download_button("📊 DOWNLOAD EXCEL", output.getvalue(), f"Traffic_Report.xlsx", use_container_width=True)
