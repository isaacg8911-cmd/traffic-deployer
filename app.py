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
st.set_page_config(page_title="Live Wire V45 Interactive", layout="centered")

st.markdown("""
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
    """, unsafe_allow_html=True)

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

def auto_save():
    payload = {
        "active_files": st.session_state.get("active_files", []),
        "optimized_route": st.session_state.get("optimized_route", []),
        "site_data": st.session_state.get("site_data", {}),
        "current_index": st.session_state.get("current_index", 0),
        "mission_type": st.session_state.get("mission_type", "📍 INSTALLATION"),
        "pickup_index": st.session_state.get("pickup_index", 0),
        "pickup_itinerary": st.session_state.get("pickup_itinerary", [])
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(payload, f)

if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k in data: st.session_state[k] = data[k]
        except: pass
    if "optimized_route" not in st.session_state:
        for k in ["active_files", "optimized_route", "pickup_itinerary"]: st.session_state[k] = []
        st.session_state.site_data = {}
        for k in ["current_index", "pickup_index"]: st.session_state[k] = 0
        st.session_state.mission_type = "📍 INSTALLATION"
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

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
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return ax + t * dx, ay + t * dy

def find_col(df, keywords):
    for kw in keywords:
        for c in df.columns:
            if kw in c: return c
    return None

def process_upload(est_configs, data_files, m_type):
    all_raw_master = []
    valid_uids_for_mission = set()
    is_pickup = "PICK-UP" in m_type
    
    csv_lookup = {}
    if data_files:
        dfs = []
        for f in data_files:
            try:
                if f.name.lower().endswith('.csv'): dfs.append(pd.read_csv(f, encoding='latin-1'))
                else: dfs.append(pd.read_excel(f))
            except: pass
            
        if dfs:
            master_df = pd.concat(dfs, ignore_index=True)
            master_df.columns = [str(c).strip().lower() for c in master_df.columns]
            
            id_col = find_col(master_df, ['tds', 'site', 'id'])
            lat1_col = find_col(master_df, ['begin_lat', 'lat1', 'lat'])
            lon1_col = find_col(master_df, ['begin_lon', 'lon1', 'lon'])
            lat2_col = find_col(master_df, ['end_lat', 'lat2'])
            lon2_col = find_col(master_df, ['end_lon', 'lon2'])
            lanes_col = find_col(master_df, ['lane'])
            street_col = find_col(master_df, ['street', 'road', 'name'])
            
            if id_col and lat1_col and lon1_col:
                for _, row in master_df.iterrows():
                    if pd.notna(row[id_col]):
                        raw_id = str(row[id_col])
                        match = re.search(r'(\d{4,5})', raw_id)
                        if match:
                            sid = match.group(1)
                            try:
                                csv_lookup[sid] = {
                                    'lat_start': float(row[lat1_col]), 'lon_start': float(row[lon1_col]),
                                    'lat_end': float(row[lat2_col]) if lat2_col and pd.notna(row[lat2_col]) else float(row[lat1_col]),
                                    'lon_end': float(row[lon2_col]) if lon2_col and pd.notna(row[lon2_col]) else float(row[lon1_col]),
                                    'lanes': int(float(row[lanes_col])) if lanes_col and pd.notna(row[lanes_col]) else 1,
                                    'street': str(row[street_col]) if street_col and pd.notna(row[street_col]) else ""
                                }
                            except: pass

    for cfg in est_configs:
        raw_bytes = cfg['file'].getvalue()
        text = raw_bytes.decode('latin-1', errors='ignore')
        
        clean_text = text.replace('\x00', ' ').replace('\n', ' ').replace('\r', ' ')
        clean_text = re.sub(r'[^\x20-\x7E]', ' ', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        base_route_sids = set(re.findall(r'\b(\d{4,5})\s+\1\s+', clean_text))
        
        if is_pickup:
            active_mission_sids = set(re.findall(r'\b(\d{4,5})[^\w\s]*\s*[xX]\b', clean_text, re.IGNORECASE))
        else:
            active_mission_sids = base_route_sids
            
        for sid in active_mission_sids:
            valid_uids_for_mission.add(f"{cfg['label']}_{sid}")
            
        for sid in base_route_sids.union(active_mission_sids):
            if sid in csv_lookup:
                d = csv_lookup[sid]
                all_raw_master.append({
                    "id": sid, "lat_start": d['lat_start'], "lon_start": d['lon_start'],
                    "lat_end": d['lat_end'], "lon_end": d['lon_end'],
                    "sheet": cfg['label'], "lanes": d['lanes'], "street": d['street']
                })
            else:
                match = re.search(r'\b' + sid + r'\b(.{1,600})', clean_text)
                if match:
                    block = match.group(1)
                    coords = [float(x) for x in re.findall(r'-?\d{2,3}\.\d{3,}', block)]
                    lats = [c for c in coords if 32.0 < c < 36.0]
                    lons = [c for c in coords if -125.0 < c < -114.0]
                    if lats and lons:
                        all_raw_master.append({
                            "id": sid, "lat_start": lats[0], "lon_start": lons[0],
                            "lat_end": lats[-1], "lon_end": lons[-1],
                            "sheet": cfg['label'], "lanes": 1, "street": ""
                        })
    
    if all_raw_master:
        df = pd.DataFrame(all_raw_master).groupby(["id", "sheet"]).agg({
            'lat_start':'first', 'lon_start':'first',
            'lat_end':'last', 'lon_end':'last',
            'lanes':'first', 'street':'first'
        }).reset_index()
        df['uid'] = df['sheet'] + "_" + df['id']
        
        master_rem = df.to_dict('records')
        master_route, curr = [], HOME_COORDS
        
        while master_rem:
            best_nxt, best_dist, best_target = None, float('inf'), None
            for x in master_rem:
                tx, ty = get_closest_point_on_segment(curr[0], curr[1], x['lat_start'], x['lon_start'], x['lat_end'], x['lon_end'])
                dist = (curr[0] - tx)**2 + (curr[1] - ty)**2
                if dist < best_dist:
                    best_dist = dist; best_nxt = x; best_target = (tx, ty)
            
            best_nxt['nav_lat'] = best_target[0]
            best_nxt['nav_lon'] = best_target[1]
            master_route.append(best_nxt)
            curr = best_target
            master_rem.remove(best_nxt)
            
        final_route = [stop for stop in master_route if stop['uid'] in valid_uids_for_mission]
        if not final_route: return False, 0
        
        installed_status = "x" if is_pickup else ""
        
        for s in final_route:
            s['auto_dir'] = get_bearing(s['lat_start'], s['lon_start'], s['lat_end'], s['lon_end'])
        
        st.session_state.optimized_route = final_route
        st.session_state.active_files = [c['label'] for c in est_configs]
        st.session_state.site_data = {
            s['uid']: {"Date":"","Time":"","Site":s['id'],"UID":s['uid'],"Counter":"c1b","Serial":"",
                      "Directions": s['auto_dir'], 
                      "Lanes":s.get('lanes', 1),"Street":s.get('street', ""),"Notes":"","Installed":installed_status,
                      "Picked up":"","LAT":s['nav_lat'],"LON":s['nav_lon'],"Skipped":False,"Sheet":s['sheet']} for s in final_route
        }
        
        st.session_state.mission_type = m_type
        st.session_state.current_index, st.session_state.pickup_index = 0, 0
        
        if is_pickup: st.session_state.pickup_itinerary = [st.session_state.site_data[s['uid']] for s in final_route]
        
        auto_save()
        return True, len(final_route)
    return False, 0

# ==========================================
# STAGE 1: UPLOAD GATEWAY
# ==========================================
if not st.session_state.get("optimized_route"):
    st.title("🚦 SECURE UPLOAD")
    
    st.markdown("### 🔄 MORNING RESTORE")
    restore_file = st.file_uploader("DROP YESTERDAY'S BACKUP JSON HERE", type=["json"])
    if restore_file:
        if st.button("🔓 RESTORE ROUTE PROGRESS", use_container_width=True):
            try:
                data = json.loads(restore_file.getvalue())
                for k in data: st.session_state[k] = data[k]
                auto_save(); st.success("✅ PROGRESS RESTORED!"); time.sleep(1); st.rerun()
            except: st.error("Invalid Backup File.")
    
    st.divider()

    st.markdown("### 🆕 START NEW MISSION")
    m_type = st.radio("SELECT MISSION TYPE:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    
    st.info("💡 OPTIONAL: Upload your Week Master Excel/CSV files here to pull exact coordinates and Street names.")
    data_files = st.file_uploader("1️⃣ DROP MASTER EXCEL / CSV DATA", type=["csv", "xls", "xlsx"], accept_multiple_files=True)
    
    up_files = st.file_uploader("2️⃣ DROP MAP FILES (.EST / .TXT)", type=["est", "txt"], accept_multiple_files=True)
    
    if up_files:
        st.success(f"✅ {len(up_files)} MAP FILES READY.")
        configs = [{"file": f, "label": st.text_input(f"Label for Map {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        
        if st.button("🚀 CROSS-REFERENCE & SYNC ROUTE", use_container_width=True):
            status = st.empty(); status.warning("⚡ MERGING EXCEL & MAP DATA...")
            success, count = process_upload(configs, data_files, m_type)
            if success:
                status.success(f"✅ COMPLETE! Locked {count} perfect sites."); time.sleep(1.5); st.rerun()
            else: status.error("❌ ERROR: Could not find valid data. Check files.")

# ==========================================
# STAGE 2: MAIN DASHBOARD
# ==========================================
else:
    st.title("🚦 Field Ops Dashboard")
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

    with tab1:
        st.success(f"MISSION: {st.session_state.mission_type} | {len(st.session_state.optimized_route)} STOPS")
        
        # V45: Advanced Map Colors (Green = Done, Red = Skipped, Orange = Pending)
        map_points = []
        is_pickup_mode = "PICK-UP" in st.session_state.mission_type
        for s in st.session_state.optimized_route:
            sd = st.session_state.site_data[s['uid']]
            is_done = sd["Picked up"] == "x" if is_pickup_mode else sd["Installed"] == "x"
            is_skipped = sd.get("Skipped", False)
            
            if is_done: color = "#00FF00"      # Green
            elif is_skipped: color = "#FF0000" # Red
            else: color = "#FFA500"            # Orange
            map_points.append({"lat": sd['LAT'], "lon": sd['LON'], "color": color})
        
        st.map(pd.DataFrame(map_points), color="color", zoom=9)
        
        # V45: Interactive Button Manifest
        st.markdown("### 📋 INTERACTIVE MANIFEST")
        st.caption("Tap any stop to instantly lock it in. Then switch to your Install/Pick-Up tab to view it.")
        
        for idx, s in enumerate(st.session_state.optimized_route):
            sd = st.session_state.site_data[s['uid']]
            is_done = sd["Picked up"] == "x" if is_pickup_mode else sd["Installed"] == "x"
            is_skipped = sd.get("Skipped", False)
            street_text = f" - {sd['Street']}" if sd.get('Street') else ""
            
            if is_done:
                label = f"✅ STOP {idx+1}: Site {sd['Site']}{street_text} (COMPLETED)"
            elif is_skipped:
                label = f"🚫 STOP {idx+1}: Site {sd['Site']}{street_text} (SKIPPED)"
            else:
                label = f"🟠 STOP {idx+1}: Site {sd['Site']}{street_text}"

            # If you click a list item, it automatically sets the index for the other tabs
            if st.button(label, key=f"manifest_btn_{idx}", use_container_width=True):
                if is_pickup_mode:
                    try:
                        # Find where this specific site lives in the pickup itinerary
                        p_idx = next(i for i, pu in enumerate(st.session_state.pickup_itinerary) if pu['UID'] == s['uid'])
                        st.session_state.pickup_index = p_idx
                        auto_save()
                        st.rerun()
                    except StopIteration: pass
                else:
                    st.session_state.current_index = idx
                    auto_save()
                    st.rerun()

        st.divider()
        st.markdown("### 🛑 END OF DAY CHECKLIST")
        st.info("⚠️ MUST DO: Download your backup now so Streamlit doesn't wipe your data overnight.")
        
        payload = {k: st.session_state.get(k) for k in ["active_files", "optimized_route", "site_data", "current_index", "mission_type", "pickup_index", "pickup_itinerary"]}
        st.download_button(label="💾 DOWNLOAD ROUTE BACKUP", data=json.dumps(payload), file_name=f"LiveWire_Backup_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json", use_container_width=True)

        st.divider()
        if st.button("🗑️ CLEAR ROUTE & START OVER", use_container_width=True):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            for k in ["active_files", "optimized_route", "pickup_itinerary"]: st.session_state[k] = []
            st.session_state.site_data = {}; st.session_state.current_index, st.session_state.pickup_index = 0, 0
            st.rerun()

    with tab2:
        if "PICK-UP" in st.session_state.mission_type:
            st.warning("⚠️ You are currently in Pick-Up Mode. Go to the ♻️ PICK-UP tab.")
        else:
            total_sites = len(st.session_state.optimized_route)
            installed_count = sum(1 for d in st.session_state.site_data.values() if d["Installed"] == "x")
            skipped_count = sum(1 for d in st.session_state.site_data.values() if d.get("Skipped"))
            
            m1, m2, m3 = st.columns(3)
            m1.metric("REMAINING", total_sites - installed_count - skipped_count)
            m2.metric("COMPLETED", installed_count)
            m3.metric("SKIPPED", skipped_count)
            st.divider()

            cur_idx = st.session_state.current_index
            if cur_idx < total_sites:
                s = st.session_state.optimized_route[cur_idx]; uid = s['uid']; sd = st.session_state.site_data[uid]
                
                street_display = f" | {sd['Street']}" if sd.get('Street') else ""
                st.subheader(f"STOP #{cur_idx+1}: SITE {sd['Site']}{street_display}")
                st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/search/?api=1&query={sd['LAT']},{sd['LON']}", use_container_width=True)
                
                st.divider()
                st.markdown("### 📍 GPS ANCHOR")
                st.caption("Tap the crosshairs FIRST to grab your exact physical location.")
                loc = streamlit_geolocation()
                live_lat, live_lon = None, None
                
                if loc and loc.get('latitude') and loc.get('longitude'):
                    live_lat, live_lon = loc['latitude'], loc['longitude']
                    st.success(f"✅ GPS Locked: {live_lat}, {live_lon}")
                
                with st.form(key=f"f_v45_{uid}"):
                    c1, c2 = st.columns(2)
                    dir_options = ["n","e","s","w"]
                    current_dir = sd.get("Directions", "n")
                    idx = dir_options.index(current_dir) if current_dir in dir_options else 0
                    with c1: dr = st.selectbox("DIR", dir_options, index=idx)
                    with c2: ln = st.number_input("LANES", min_value=1, value=int(sd.get("Lanes", 1)))
                    ser = st.text_input("SERIAL #", value=sd["Serial"])
                    nt = st.text_input("NOTES", value=sd["Notes"])
                    
                    col_a, col_b = st.columns(2)
                    if col_a.form_submit_button("✅ COMPLETE", use_container_width=True):
                        t, d = get_ca_time()
                        final_lat = live_lat if live_lat else sd['LAT']
                        final_lon = live_lon if live_lon else sd['LON']
                        
                        st.session_state.site_data[uid].update({
                            "Date": d, "Time": t, 
                            "Directions": "n" if dr in ["n","s"] else "e", 
                            "Serial": ser, "Lanes": ln, "Notes": nt, 
                            "Installed": "x", "LAT": final_lat, "LON": final_lon, "Skipped": False
                        })
                        st.session_state.current_index += 1; auto_save(); st.rerun()
                    if col_b.form_submit_button("🚨 UNABLE (SKIP)", use_container_width=True):
                        t, d = get_ca_time()
                        st.session_state.site_data[uid].update({"Date":d,"Time":t,"Notes":f"UNABLE: {nt.upper()}","Skipped":True})
                        st.session_state.current_index += 1; auto_save(); st.rerun()
                
                if cur_idx > 0 and st.button("⬅️ PREVIOUS STOP", use_container_width=True):
                    st.session_state.current_index -= 1; auto_save(); st.rerun()
            else: st.balloons(); st.success("🏁 INSTALLATION COMPLETED.")

    with tab3:
        if "INSTALL" in st.session_state.mission_type:
            st.warning("⚠️ You are currently in Install Mode.")
        else:
            itinerary = st.session_state.get("pickup_itinerary", [])
            view_mode = st.radio("VIEW MODE", ["Focus Mode (1-by-1)", "List View"], horizontal=True)
            st.divider()

            if view_mode == "List View":
                for i, s in enumerate(itinerary):
                    uid, sid = s["UID"], s["Site"]
                    is_picked = s["Picked up"] == "x"
                    is_skipped = s.get("Skipped", False)
                    street_txt = f" - {s['Street']}" if s.get('Street') else ""
                    
                    if is_picked:
                        st.markdown(f"<div style='color: #00FF00; font-weight: 900; padding: 10px; border: 1px solid #00FF00; border-radius: 5px; margin-bottom: 10px;'>✅ #{i+1} - SITE {sid}{street_txt} SECURED</div>", unsafe_allow_html=True)
                    elif is_skipped:
                        st.markdown(f"<div style='color: #FF0000; font-weight: 900; padding: 10px; border: 1px solid #FF0000; border-radius: 5px; margin-bottom: 10px;'>🚫 #{i+1} - SITE {sid}{street_txt} SKIPPED</div>", unsafe_allow_html=True)
                    else:
                        with st.expander(f"📦 #{i+1} - Site {sid}{street_txt} ({s['Sheet']})"):
                            st.link_button("🚗 Navigate to Spot", f"https://www.google.com/maps/search/?api=1&query={s['LAT']},{s['LON']}", use_container_width=True)
                            with st.form(key=f"pu_list_{uid}"):
                                p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                                if st.form_submit_button("MARK SECURED"):
                                    st.session_state.site_data[uid]["Picked up"] = "x"; st.session_state.site_data[uid]["Skipped"] = False; st.session_state.site_data[uid]["Notes"] = p_notes.strip(); auto_save(); st.rerun()
            else:
                p_idx = st.session_state.get("pickup_index", 0)
                if p_idx < len(itinerary):
                    s = itinerary[p_idx]; uid, sid = s["UID"], s["Site"]
                    street_txt = f" | {s['Street']}" if s.get('Street') else ""
                    st.subheader(f"PICK-UP #{p_idx+1}: SITE {sid}{street_txt}")
                    
                    st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/search/?api=1&query={s['LAT']},{s['LON']}", use_container_width=True)
                    
                    with st.form(key=f"pu_focus_{uid}"):
                        p_notes = st.text_input("NOTES", value=s["Notes"])
                        col_a, col_b = st.columns(2)
                        if col_a.form_submit_button("✅ SECURED", use_container_width=True):
                            st.session_state.site_data[uid]["Picked up"] = "x"
                            st.session_state.site_data[uid]["Skipped"] = False
                            st.session_state.site_data[uid]["Notes"] = p_notes.strip(); st.session_state.pickup_index += 1; auto_save(); st.rerun()
                        # V45: Skipped logic added to Pick-Ups
                        if col_b.form_submit_button("🚨 UNABLE (SKIP)", use_container_width=True):
                            st.session_state.site_data[uid]["Notes"] = f"UNABLE: {p_notes.upper()}"
                            st.session_state.site_data[uid]["Skipped"] = True
                            st.session_state.pickup_index += 1; auto_save(); st.rerun()
                    if p_idx > 0 and st.button("⬅️ PREVIOUS STOP", use_container_width=True):
                        st.session_state.pickup_index -= 1; auto_save(); st.rerun()
                else: st.balloons(); st.success("🏁 ALL EQUIPMENT SECURED.")

    with tab4:
        all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x" or d.get("Skipped")]
        if all_d:
            try:
                full_df = pd.DataFrame(all_d)
                cols = ["Date", "Time", "Site", "Counter", "Serial", "Directions", "Lanes", "Notes", "Installed", "Picked up"]
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for sheet_name in st.session_state.active_files:
                        sheet_df = full_df[full_df["Sheet"] == sheet_name]
                        if not sheet_df.empty:
                            final = sheet_df[cols]; final.to_excel(writer, index=False, sheet_name=sheet_name)
                            st.write(f"**Day: {sheet_name}**"); st.dataframe(final, use_container_width=True)
                st.divider()
                st.download_button("📊 DOWNLOAD MASTER WORKBOOK", output.getvalue(), f"Traffic_Precision.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
            except Exception as e:
                st.error("⚠️ Data Export Error.")
