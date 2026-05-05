import streamlit as st
import re
import pandas as pd
import math
import json
import io
import time
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V17 LED", layout="centered")

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

# --- NATIVE SAVE ENGINE ---
def auto_save():
    payload = {
        "active_files": st.session_state.get("active_files", []),
        "optimized_route": st.session_state.get("optimized_route", []),
        "site_data": st.session_state.get("site_data", {}),
        "current_index": st.session_state.get("current_index", 0)
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(payload, f)

if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                st.session_state.active_files = data.get("active_files", [])
                st.session_state.optimized_route = data.get("optimized_route", [])
                st.session_state.site_data = data.get("site_data", {})
                st.session_state.current_index = data.get("current_index", 0)
        except:
            st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
    else:
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

# --- HIGH-SPEED DATA SHREDDER (AGGRESSIVE STREET EXTRACTION) ---
def process_upload(configs):
    all_raw = []
    coord_pattern = re.compile(r'-?\d{1,3}\.\d{3,}')
    id_pattern = re.compile(r'\b(\d{4})\b')
    
    for cfg in configs:
        content = cfg['file'].getvalue().decode('latin-1', errors='ignore')
        for line in content.splitlines():
            if "3333" in line: continue
            if "." in line:
                coords = coord_pattern.findall(line)
                if len(coords) >= 2:
                    id_match = id_pattern.search(line)
                    if id_match:
                        sid = id_match.group(1)
                        c1, c2 = float(coords[0]), float(coords[1])
                        lat, lon = max(c1, c2), min(c1, c2)
                        
                        # Aggressively isolate the street name
                        clean_line = line.replace(sid, '') # Remove the Site ID
                        clean_line = re.sub(r'-?\d{1,3}\.\d{3,}', '', clean_line) # Remove GPS Coords
                        clean_line = re.sub(r'\b\d{5}\b', '', clean_line) # Remove Zip Codes
                        clean_line = re.sub(r'[^a-zA-Z0-9\s]', '', clean_line) # Remove weird symbols
                        street_name = " ".join(clean_line.split()).strip()
                        street_name = street_name[:40] if street_name else "NO STREET DATA"
                        
                        all_raw.append({"id": sid, "lat": lat, "lon": lon, "sheet": cfg['label'], "street": street_name.upper()})
    
    if all_raw:
        df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first','street':'first'}).reset_index()
        route, curr, rem = [], HOME_COORDS, df.to_dict('records')
        while rem:
            nxt = min(rem, key=lambda x: (curr[0] - x['lat'])**2 + (curr[1] - x['lon'])**2)
            route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
        
        st.session_state.optimized_route = route
        st.session_state.active_files = [c['label'] for c in configs]
        st.session_state.site_data = {s['id']: {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"Street":s['street']} for s in route}
        auto_save()
        return True, len(route)
    return False, 0

# ==========================================
# STAGE 1: THE UPLOAD GATEWAY
# ==========================================
if not st.session_state.get("optimized_route"):
    st.title("🚦 SECURE UPLOAD")
    
    up_files = st.file_uploader("DROP .EST / .TXT MAPS", type=["est", "txt"], accept_multiple_files=True)
    
    if up_files:
        st.success(f"✅ {len(up_files)} FILES READY.")
        configs = [{"file": f, "label": st.text_input(f"Label for Map {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        
        if st.button("🚀 CALCULATE & SYNC ROUTE", use_container_width=True):
            status = st.empty()
            status.warning("⚡ SHREDDING DATA & ROUTING...")
            
            start_time = time.time()
            success, count = process_upload(configs)
            end_time = time.time()
            
            if success:
                calc_time = round(end_time - start_time, 2)
                status.success(f"✅ COMPLETE! Found {count} sites in {calc_time} seconds.")
                time.sleep(1.5)
                st.rerun()
            else:
                status.error("❌ ERROR: Could not find valid data. Please check files.")

# ==========================================
# STAGE 2: MAIN DASHBOARD
# ==========================================
else:
    st.title("🚦 Field Ops Dashboard")
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

    with tab1:
        st.success(f"ACTIVE ROUTE: {len(st.session_state.optimized_route)} STOPS")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        
        st.divider()
        if st.button("🗑️ CLEAR ROUTE & START OVER", use_container_width=True):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            for key in ["active_files", "optimized_route", "site_data", "current_index"]:
                st.session_state[key] = [] if isinstance(st.session_state[key], list) else ({} if isinstance(st.session_state[key], dict) else 0)
            st.rerun()

    with tab2:
        total_sites = len(st.session_state.optimized_route)
        installed_count = sum(1 for d in st.session_state.site_data.values() if d["Installed"] == "x")
        skipped_count = sum(1 for d in st.session_state.site_data.values() if d.get("Skipped"))
        remaining = total_sites - installed_count - skipped_count

        m1, m2, m3 = st.columns(3)
        m1.metric("REMAINING", remaining)
        m2.metric("COMPLETED", installed_count)
        m3.metric("SKIPPED", skipped_count)
        st.divider()

        cur_idx = st.session_state.current_index
        if cur_idx < total_sites:
            s = st.session_state.optimized_route[cur_idx]; sid = s['id']; sd = st.session_state.site_data[sid]
            
            # 1. The Standard Header
            st.subheader(f"STOP #{cur_idx+1}: SITE {sid}")
            
            # 2. The LED Neon Billboard (Placed directly beneath the header)
            st.markdown(f"""
            <div style="
                background-color: #000000; 
                border: 3px solid #111111; 
                border-radius: 8px; 
                padding: 20px 10px; 
                margin-top: 5px;
                margin-bottom: 15px; 
                text-align: center; 
                box-shadow: 0 0 15px rgba(57, 255, 20, 0.2);
            ">
                <span style="
                    color: #39FF14; 
                    font-family: 'Courier New', Courier, monospace; 
                    font-size: 1.8rem; 
                    font-weight: 900; 
                    text-shadow: 0 0 5px #39FF14, 0 0 10px #39FF14, 0 0 20px #39FF14; 
                    letter-spacing: 1px;
                ">
                    {sd.get('Street', 'NO STREET DETECTED')}
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            st.caption(f"Sheet: {sd.get('Sheet')} | Raw GPS: `{s['lat']}, {s['lon']}`") 
            
            st.progress(cur_idx / total_sites)
            st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
            
            with st.form(key=f"f_v17_{sid}"):
                c1, c2 = st.columns(2)
                with c1: dr = st.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(sd["Directions"]))
                with c2: ln = st.number_input("LANES", min_value=1, value=int(sd["Lanes"]))
                ser = st.text_input("SERIAL #", value=sd["Serial"])
                nt = st.text_input("NOTES", value=sd["Notes"])
                
                col_a, col_b = st.columns(2)
                if col_a.form_submit_button("✅ COMPLETE", use_container_width=True):
                    t, d = get_ca_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if dr in ["n","s"] else "e","Serial":ser,"Lanes":ln,"Notes":nt,"Installed":"x"})
                    st.session_state.current_index += 1; auto_save(); st.rerun()
                if col_b.form_submit_button("🚨 UNABLE", use_container_width=True):
                    t, d = get_ca_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Notes":f"UNABLE: {nt.upper()}","Skipped":True})
                    st.session_state.current_index += 1; auto_save(); st.rerun()
            
            if cur_idx > 0 and st.button("⬅️ PREVIOUS STOP", use_container_width=True):
                st.session_state.current_index -= 1; auto_save(); st.rerun()
        else:
            st.balloons(); st.success("🏁 MISSION COMPLETED.")

    with tab3:
        installed = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
        if not installed: st.info("No sites installed yet.")
        else:
            if st.button("🔄 Optimize Pick-Up Order", use_container_width=True):
                curr, new_itin, rem = HOME_COORDS, [], installed.copy()
                while rem:
                    nxt = min(rem, key=lambda x: (curr[0]-x['LAT'])**2 + (curr[1]-x['LON'])**2)
                    new_itin.append(nxt); curr = (nxt['LAT'], nxt['LON']); rem.remove(nxt)
                st.session_state.pickup_itinerary = new_itin; st.success("Pick-Up sequence optimized.")

            itinerary = st.session_state.get("pickup_itinerary", installed)
            for i, s in enumerate(itinerary):
                sid, is_picked = s["Site"], s["Picked up"] == "x"
                status = "✅" if is_picked else "📦"
                with st.expander(f"{status} #{i+1} - Site {sid}"):
                    if not is_picked:
                        st.markdown(f"**📍 {s.get('Street')}**")
                        st.caption(f"Raw GPS: `{s['LAT']}, {s['LON']}`")
                        st.link_button("🚗 Navigate to Spot", f"https://www.google.com/maps/dir/?api=1&destination={s['LAT']},{s['LON']}", use_container_width=True)
                        with st.form(key=f"pu_v17_{sid}"):
                            p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                            if st.form_submit_button("MARK SECURED"):
                                st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip(); auto_save(); st.rerun()
                    else: st.write(f"Secured.")

    with tab4:
        all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x" or d.get("Skipped")]
        if all_d:
            try:
                full_df = pd.DataFrame(all_d)
                cols = ["Date", "Time", "Site", "Street", "Counter", "Serial", "Directions", "Lanes", "Notes", "Installed", "Picked up"]
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
                st.error("⚠️ Data Export Error. Please contact admin or download raw JSON backup.")
                st.write(e)
