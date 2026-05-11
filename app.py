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
st.set_page_config(page_title="Live Wire V51.2 Precision", layout="centered")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

# --- THEME ENGINE (OLED SAVER) ---
if "theme" not in st.session_state:
    st.session_state.theme = "☁️ Overcast (Standard)"

def set_theme(theme_choice):
    if theme_choice == "🌞 Bright Sun (OLED Contrast)":
        return """
        <style>
        .stApp { background-color: #000000; color: #FFFFFF; }
        h1, h2, h3 { color: #00FFFF !important; font-family: 'Arial Black'; letter-spacing: -1px; font-weight: 900;}
        div.stButton > button { 
            background-color: #000000; color: #00FFFF; border: 3px solid #00FFFF; 
            font-weight: 900; border-radius: 4px; transition: 0.3s;
        }
        div.stButton > button:active { transform: scale(0.95); background-color: #00FFFF; color: #000000; }
        .stTabs [data-baseweb="tab-list"] { background-color: #000000; border-bottom: 3px solid #333; }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #00FFFF !important; border-bottom-color: #00FFFF !important; }
        input, select, textarea { background-color: #000000 !important; color: #00FFFF !important; border: 2px solid #00FFFF !important; font-weight: bold;}
        div[data-testid="stMetricValue"] { color: #00FFFF !important; font-size: 2rem !important; font-weight: 900; }
        div[data-testid="stMetricLabel"] { color: #FFFFFF !important; font-weight: bold; }
        </style>
        """
    else:
        return """
        <style>
        .stApp { background-color: #0A0A0A; color: #FFFFFF; }
        h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; letter-spacing: -1px; }
        div.stButton > button { 
            background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; 
            font-weight: 900; border-radius: 4px; transition: 0.3s;
        }
        div.stButton > button:active { transform: scale(0.95); background-color: #FFD700; color: #000; }
        .stTabs [data-baseweb="tab-list"] { background-color: #0A0A0A; border-bottom: 2px solid #333; }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
        input, select, textarea { background-color: #111 !important; color: #FFD700 !important; border: 1px solid #444 !important; }
        div[data-testid="stMetricValue"] { color: #FFD700 !important; font-size: 2rem !important; }
        div[data-testid="stMetricLabel"] { color: #CCCCCC !important; font-weight: bold; }
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
            "theme": st.session_state.get("theme", "☁️ Overcast (Standard)"),
            "last_sort_mode": st.session_state.get("last_sort_mode", "⏳ Chronological (Install Order)")
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
        st.session_state.last_sort_mode = "⏳ Chronological (Install Order)"
    st.session_state.init = True

st.markdown(set_theme(st.session_state.theme), unsafe_allow_html=True)

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    exact_t = now.strftime("%Y-%m-%d %H:%M:%S")
    if now.minute > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d"), exact_t

def get_bearing(lat1, lon1, lat2, lon2):
    if abs(lat1 - lat2) < 0.00001 and abs(lon1 - lon2) < 0.00001: return "n" 
    try:
        dLon = math.radians(lon2 - lon1)
        lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
        y = math.sin(dLon) * math.cos(lat2_r)
        x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dLon)
        bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
        return "n" if (315 <= bearing <= 360) or (0 <= bearing < 45) or (135 <= bearing < 225) else "e"
    except: return "n"

def get_closest_point_on_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0: return ax, ay
    dist_sq = dx * dx + dy * dy
    if dist_sq == 0: return ax, ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dist_sq))
    return ax + t * dx, ay + t * dy

def find_col(df, keywords):
    for kw in keywords:
        for c in df.columns:
            if kw == c or f"_{kw}" in c or f"{kw}_" in c: return c
    for kw in keywords:
        for c in df.columns:
            if kw in c: return c
    return None

def process_upload(est_configs, data_files, m_type):
    all_raw_master, valid_uids_for_mission, is_pickup = [], set(), "PICK-UP" in m_type
    csv_lookup = {}
    if data_files:
        dfs = []
        for f in data_files:
            try:
                if f.name.lower().endswith('.csv'): dfs.append(pd.read_csv(f, encoding='latin-1', on_bad_lines='skip'))
                else: dfs.append(pd.read_excel(f))
            except: pass
        if dfs:
            try:
                master_df = pd.concat(dfs, ignore_index=True)
                master_df.columns = [str(c).strip().lower() for c in master_df.columns]
                id_col, lat1_col, lon1_col = find_col(master_df, ['tds', 'site', 'id']), find_col(master_df, ['begin_lat', 'lat1', 'lat']), find_col(master_df, ['begin_lon', 'lon1', 'lon'])
                lat2_col, lon2_col, lanes_col, street_col = find_col(master_df, ['end_lat', 'lat2']), find_col(master_df, ['end_lon', 'lon2']), find_col(master_df, ['lane']), find_col(master_df, ['street', 'road', 'name'])
                if id_col and lat1_col and lon1_col:
                    for _, row in master_df.iterrows():
                        if pd.notna(row[id_col]):
                            sid = re.search(r'(\d{4,5})', str(row[id_col]))
                            if sid:
                                csv_lookup[sid.group(1)] = {'lat_start': float(row[lat1_col]), 'lon_start': float(row[lon1_col]), 'lat_end': float(row[lat2_col]) if lat2_col and pd.notna(row[lat2_col]) else float(row[lat1_col]), 'lon_end': float(row[lon2_col]) if lon2_col and pd.notna(row[lon2_col]) else float(row[lon1_col]), 'lanes': int(float(row[lanes_col])) if lanes_col and pd.notna(row[lanes_col]) else 2, 'street': str(row[street_col]) if street_col and pd.notna(row[street_col]) else ""}
            except: pass
    for cfg in est_configs:
        try:
            raw_bytes = cfg['file'].getvalue()
            text = re.sub(r'\s+', ' ', raw_bytes.decode('latin-1', errors='ignore').replace('\x00', ' ').replace('\n', ' ').replace('\r', ' '))
            base_route_sids = set(re.findall(r'\b(\d{4,5})\s+\1\s+', text))
            if is_pickup: active_mission_sids = set(re.findall(r'\b(\d{4,5})[^\w\s]*\s*[xX]\b', text, re.IGNORECASE))
            else: active_mission_sids = base_route_sids
            for sid in active_mission_sids: valid_uids_for_mission.add(f"{cfg['label']}_{sid}")
            for sid in base_route_sids.union(active_mission_sids):
                if sid in csv_lookup:
                    d = csv_lookup[sid]
                    all_raw_master.append({"id": sid, "lat_start": d['lat_start'], "lon_start": d['lon_start'], "lat_end": d['lat_end'], "lon_end": d['lon_end'], "sheet": cfg['label'], "lanes": d['lanes'], "street": d['street']})
                else:
                    match = re.search(r'\b' + sid + r'\b(.{1,600})', text)
                    if match:
                        coords = [float(x) for x in re.findall(r'-?\d{2,3}\.\d{3,}', match.group(1))]
                        lats, lons = [c for c in coords if 32.0 < c < 36.0], [c for c in coords if -125.0 < c < -114.0]
                        if lats and lons:
                            l1, n1, l2, n2 = lats[0], lons[0], lats[-1], lons[-1]
                            if abs(l1-l2) > 0.05: l2, n2 = l1, n1
                            all_raw_master.append({"id": sid, "lat_start": l1, "lon_start": n1, "lat_end": l2, "lon_end": n2, "sheet": cfg['label'], "lanes": 2, "street": ""})
        except: return False, 0
    if all_raw_master:
        df = pd.DataFrame(all_raw_master).groupby(["id", "sheet"]).agg({'lat_start':'first', 'lon_start':'first','lat_end':'last', 'lon_end':'last','lanes':'first', 'street':'first'}).reset_index()
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
        final_route = [stop for stop in master_route if stop['uid'] in valid_uids_for_mission]
        if not final_route: return False, 0
        st.session_state.optimized_route = final_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.site_data = {s['uid']: {"Date":"","Time":"","ExactTime":"","Site":s['id'],"UID":s['uid'],"Counter":"c1b","Serial":"","Directions": get_bearing(s['lat_start'], s['lon_start'], s['lat_end'], s['lon_end']), "Lanes":s.get('lanes', 2),"Street":s.get('street', ""),"Notes":"","Installed":"x" if is_pickup else "","Lat_Start":s['lat_start'], "Lon_Start":s['lon_start'],"Lat_End":s['lat_end'], "Lon_End":s['lon_end'],"Picked up":"","LAT":s['nav_lat'],"LON":s['nav_lon'],"Skipped":False,"Sheet":s['sheet']} for s in final_route}
        st.session_state.mission_type, st.session_state.current_index, st.session_state.pickup_index = m_type, 0, 0
        if is_pickup: st.session_state.pickup_itinerary = [st.session_state.site_data[s['uid']] for s in final_route]
        auto_save(); return True, len(final_route)
    return False, 0

# --- UI START ---
if not st.session_state.get("optimized_route"):
    st.title("🚦 SECURE UPLOAD")
    restore_file = st.file_uploader("🔄 MORNING RESTORE (JSON)", type=["json"])
    if restore_file and st.button("🔓 RESTORE", use_container_width=True):
        try:
            data = json.loads(restore_file.getvalue())
            for k, v in data.items(): st.session_state[k] = v
            installed_sites = [sd for sd in st.session_state.site_data.values() if sd.get("Installed") == "x"]
            st.session_state.pickup_itinerary = sorted(installed_sites, key=lambda x: x.get('ExactTime', ''))
            st.success("✅ RESTORED!"); time.sleep(1); st.rerun()
        except: st.error("Invalid File.")
    st.divider()
    m_type = st.radio("MISSION:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    data_files = st.file_uploader("1️⃣ MASTER DATA (EXCEL/CSV)", type=["csv", "xls", "xlsx"], accept_multiple_files=True)
    up_files = st.file_uploader("2️⃣ MAP FILES (.EST / .TXT)", type=["est", "txt"], accept_multiple_files=True)
    if up_files:
        configs = [{"file": f, "label": st.text_input(f"Label {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        if st.button("🚀 SYNC ROUTE", use_container_width=True):
            success, count = process_upload(configs, data_files, m_type)
            if success: st.success(f"✅ Locked {count} sites."); time.sleep(1); st.rerun()
            else: st.error("No valid data.")
else:
    new_theme = st.radio("📱 DISPLAY:", ["☁️ Overcast (Standard)", "🌞 Bright Sun (OLED Contrast)"], index=0 if st.session_state.theme == "☁️ Overcast (Standard)" else 1, horizontal=True)
    if new_theme != st.session_state.theme: st.session_state.theme = new_theme; auto_save(); st.rerun()
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])
    with tab1:
        st.success(f"{st.session_state.mission_type} | {len(st.session_state.optimized_route)} STOPS")
        map_points = []
        is_p = "PICK-UP" in st.session_state.mission_type
        # Add Home with high precision
        map_points.append({"lat": HOME_COORDS[0], "lon": HOME_COORDS[1], "color": "#FFFFFF"})
        for s in st.session_state.optimized_route:
            sd = st.session_state.site_data[s['uid']]
            done = sd["Picked up"] == "x" if is_p else sd["Installed"] == "x"
            color = "#00FF00" if done else ("#FF0000" if sd.get("Skipped") else "#FFA500")
            map_points.append({"lat": sd['LAT'], "lon": sd['LON'], "color": color})
        # V51.2 Snap to work area logic:
        st.map(pd.DataFrame(map_points), color="color", zoom=None) # Zoom=None triggers auto-snap to pins
        st.markdown("### 📋 MANIFEST")
        for idx, s in enumerate(st.session_state.optimized_route):
            sd = st.session_state.site_data[s['uid']]
            done = sd["Picked up"] == "x" if is_p else sd["Installed"] == "x"
            label = f"{'✅' if done else ('🚫' if sd.get('Skipped') else '🟠')} STOP {idx+1}: Site {sd['Site']} {sd.get('Street','')}"
            if st.button(label, key=f"m_{idx}", use_container_width=True):
                if is_p:
                    try: st.session_state.pickup_index = next(i for i, pu in enumerate(st.session_state.pickup_itinerary) if pu['UID'] == s['uid'])
                    except: pass
                else: st.session_state.current_index = idx
                auto_save(); st.rerun()
        st.divider()
        payload = {k: st.session_state.get(k) for k in ["active_files", "optimized_route", "site_data", "current_index", "mission_type", "pickup_index", "pickup_itinerary", "theme", "last_sort_mode"]}
        st.download_button("💾 DOWNLOAD MASTER SHIFT FILE", json.dumps(payload), f"LiveWire_Save_{datetime.now().strftime('%Y%m%d')}.json", "application/json", use_container_width=True)
        if st.button("🗑️ CLEAR & START OVER", use_container_width=True):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            for k in ["active_files", "optimized_route", "pickup_itinerary"]: st.session_state[k] = []
            st.session_state.site_data = {}; st.rerun()
    with tab2:
        if "PICK-UP" in st.session_state.mission_type: st.warning("Go to ♻️ PICK-UP tab.")
        else:
            cur = st.session_state.current_index
            if cur < len(st.session_state.optimized_route):
                s = st.session_state.optimized_route[cur]; sd = st.session_state.site_data[s['uid']]
                st.subheader(f"STOP #{cur+1}: SITE {sd['Site']} | {sd['Street']}")
                st.link_button("🚗 SINGLE NAV", f"https://www.google.com/maps/search/?api=1&query={sd['LAT']},{sd['LON']}", use_container_width=True)
                batch = [f"{st.session_state.site_data[bs['uid']]['LAT']},{st.session_state.site_data[bs['uid']]['LON']}" for bs in st.session_state.optimized_route[cur:cur+9] if st.session_state.site_data[bs['uid']]['Installed'] != "x"]
                if len(batch) > 1: st.link_button(f"🗺️ BATCH NAV NEXT {len(batch)}", "https://www.google.com/maps/dir/" + "/".join(batch), use_container_width=True)
                loc = streamlit_geolocation()
                live_lat, live_lon = (loc['latitude'], loc['longitude']) if loc and loc.get('latitude') else (None, None)
                if live_lat: st.success("✅ GPS ANCHOR LOCKED")
                with st.form(f"f_{cur}"):
                    c1, c2 = st.columns(2)
                    dr = c1.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(sd["Directions"]))
                    ln = c2.number_input("LANES", min_value=1, value=int(sd["Lanes"]))
                    ser, nt = st.text_input("SERIAL #", value=sd["Serial"]), st.text_input("NOTES", value=sd["Notes"])
                    if st.form_submit_button("✅ COMPLETE", use_container_width=True):
                        t, d, et = get_ca_time()
                        st.session_state.site_data[s['uid']].update({"Date":d, "Time":t, "ExactTime":et, "Directions":dr, "Serial":ser, "Lanes":ln, "Notes":nt, "Installed":"x", "LAT":live_lat if live_lat else sd['LAT'], "LON":live_lon if live_lon else sd['LON'], "Skipped":False})
                        st.session_state.current_index += 1; auto_save(); st.rerun()
                    if st.form_submit_button("🚨 UNABLE (SKIP)", use_container_width=True):
                        t, d, et = get_ca_time()
                        st.session_state.site_data[s['uid']].update({"Date":d,"Time":t,"ExactTime":et,"Notes":f"UNABLE: {nt}","Skipped":True})
                        st.session_state.current_index += 1; auto_save(); st.rerun()
                if cur > 0 and st.button("⬅️ PREVIOUS"): st.session_state.current_index -= 1; st.rerun()
            else: st.balloons(); st.success("🏁 DONE.")
    with tab3:
        itin = st.session_state.get("pickup_itinerary", [])
        if not itin: st.info("Upload your file in Tab 1.")
        else:
            sm = st.radio("Order:", ["⏳ Chronological", "🚀 Fastest"], horizontal=True, index=0 if st.session_state.last_sort_mode == "⏳ Chronological" else 1)
            if sm != st.session_state.last_sort_mode:
                if sm == "⏳ Chronological": st.session_state.pickup_itinerary = sorted(itin, key=lambda x: x.get('ExactTime', ''))
                else:
                    rem, new, c = itin.copy(), [], HOME_COORDS
                    while rem:
                        nxt = min(rem, key=lambda x: (c[0]-x['LAT'])**2 + (c[1]-x['LON'])**2)
                        new.append(nxt); c = (nxt['LAT'], nxt['LON']); rem.remove(nxt)
                    st.session_state.pickup_itinerary = new
                st.session_state.last_sort_mode, st.session_state.pickup_index = sm, 0; auto_save(); st.rerun()
            p_idx = st.session_state.pickup_index
            if p_idx < len(itin):
                s = itin[p_idx]; uid = s['UID']
                st.subheader(f"PICK-UP #{p_idx+1}: SITE {s['Site']} | {s['Street']}")
                st.link_button("🚗 NAV TO SPOT", f"https://www.google.com/maps/search/?api=1&query={s['LAT']},{s['LON']}", use_container_width=True)
                batch_p = [f"{st.session_state.site_data[bs['UID']]['LAT']},{st.session_state.site_data[bs['UID']]['LON']}" for bs in itin[p_idx:p_idx+9] if st.session_state.site_data[bs['UID']]['Picked up'] != "x"]
                if len(batch_p) > 1: st.link_button(f"🗺️ BATCH NAV NEXT {len(batch_p)}", "https://www.google.com/maps/dir/" + "/".join(batch_p), use_container_width=True)
                with st.form(f"pu_{p_idx}"):
                    pn = st.text_input("NOTES", value=s["Notes"])
                    if st.form_submit_button("✅ SECURED"):
                        st.session_state.site_data[uid].update({"Picked up":"x","Skipped":False,"Notes":pn}); st.session_state.pickup_index += 1; auto_save(); st.rerun()
                    if st.form_submit_button("🚨 SKIP"):
                        st.session_state.site_data[uid].update({"Skipped":True}); st.session_state.pickup_index += 1; auto_save(); st.rerun()
                if p_idx > 0 and st.button("⬅️ PREV"): st.session_state.pickup_index -= 1; auto_save(); st.rerun()
            else: st.balloons(); st.success("🏁 SECURED.")
    with tab4:
        all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x" or d.get("Skipped")]
        if all_d:
            try:
                full_df = pd.DataFrame(all_d)
                cols = ["Date", "Time", "ExactTime", "Site", "Counter", "Serial", "Directions", "Lanes", "Notes", "Installed", "Picked up"]
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for sheet_name in st.session_state.active_files:
                        sheet_df = full_df[full_df["Sheet"] == sheet_name]
                        if not sheet_df.empty: sheet_df[cols].to_excel(writer, index=False, sheet_name=sheet_name)
                st.download_button("📊 DOWNLOAD EXCEL", output.getvalue(), f"Traffic_Report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except: st.error("Export Error.")
