import streamlit as st
import re
import pandas as pd
import json
import io
import time
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V23 Protocol", layout="centered")

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

# Garden Grove Basecamp
HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

# --- NATIVE SAVE ENGINE ---
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
                st.session_state.active_files = data.get("active_files", [])
                st.session_state.optimized_route = data.get("optimized_route", [])
                st.session_state.site_data = data.get("site_data", {})
                st.session_state.current_index = data.get("current_index", 0)
                st.session_state.mission_type = data.get("mission_type", "📍 INSTALLATION")
                st.session_state.pickup_index = data.get("pickup_index", 0)
                st.session_state.pickup_itinerary = data.get("pickup_itinerary", [])
        except:
            for k in ["active_files", "optimized_route", "pickup_itinerary"]: st.session_state[k] = []
            st.session_state.site_data = {}
            for k in ["current_index", "pickup_index"]: st.session_state[k] = 0
            st.session_state.mission_type = "📍 INSTALLATION"
    else:
        for k in ["active_files", "optimized_route", "pickup_itinerary"]: st.session_state[k] = []
        st.session_state.site_data = {}
        for k in ["current_index", "pickup_index"]: st.session_state[k] = 0
        st.session_state.mission_type = "📍 INSTALLATION"
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

# --- V23 JET DB SANITIZER & ROUTER ---
def process_upload(configs, m_type):
    all_raw = []
    
    for cfg in configs:
        raw_bytes = cfg['file'].getvalue()
        text = raw_bytes.decode('latin-1', errors='ignore')
        
        clean_text = text.replace('\x00', ' ').replace('\n', ' ').replace('\r', ' ')
        clean_text = re.sub(r'[^\x20-\x7E]', ' ', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        # Split blocks by double ID pattern (e.g., "4716 4716 ")
        tokens = re.split(r'\b(\d{4})\s+\1\s+', clean_text)
        
        for i in range(1, len(tokens) - 1, 2):
            sid = tokens[i]
            block = tokens[i+1]
            
            coords = re.findall(r'-?\d{2,3}\.\d{3,}', block)
            if len(coords) >= 2:
                c1, c2 = float(coords[0]), float(coords[1])
                lat, lon = max(c1, c2), min(c1, c2)
                
                # Verify coordinates are in Southern California
                if 32.0 < lat < 36.0 and -125.0 < lon < -114.0:
                    all_raw.append({"id": sid, "lat": lat, "lon": lon, "sheet": cfg['label']})
    
    if all_raw:
        df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
        route, curr, rem = [], HOME_COORDS, df.to_dict('records')
        
        # Calculates fastest path from basecamp to all pins
        while rem:
            nxt = min(rem, key=lambda x: (curr[0] - x['lat'])**2 + (curr[1] - x['lon'])**2)
            route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
        
        is_pickup = "PICK-UP" in m_type
        installed_status = "x" if is_pickup else ""
        
        st.session_state.optimized_route = route
        st.session_state.active_files = [c['label'] for c in configs]
        st.session_state.site_data = {
            s['id']: {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n",
                      "Lanes":1,"Notes":"","Installed":installed_status,"Picked up":"","LAT":s['lat'],
                      "LON":s['lon'],"Skipped":False,"Sheet":s['sheet']} for s in route
        }
        
        st.session_state.mission_type = m_type
        st.session_state.current_index = 0
        st.session_state.pickup_index = 0
        
        if is_pickup:
            st.session_state.pickup_itinerary = [st.session_state.site_data[s['id']] for s in route]
        
        auto_save()
        return True, len(route)
    return False, 0

# ==========================================
# STAGE 1: THE UPLOAD GATEWAY
# ==========================================
if not st.session_state.get("optimized_route"):
    st.title("🚦 SECURE UPLOAD")
    
    st.markdown("### 🔄 MORNING RESTORE")
    restore_file = st.file_uploader("DROP YESTERDAY'S BACKUP JSON HERE", type=["json"])
    if restore_file:
        if st.button("🔓 RESTORE ROUTE PROGRESS", use_container_width=True):
            try:
                data = json.loads(restore_file.getvalue())
                for k in ["active_files", "optimized_route", "site_data", "current_index", "mission_type", "pickup_index", "pickup_itinerary"]:
                    if k in data: st.session_state[k] = data[k]
                auto_save()
                st.success("✅ PROGRESS RESTORED!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error("Invalid Backup File.")
    
    st.divider()

    st.markdown("### 🆕 START NEW MISSION")
    m_type = st.radio("SELECT MISSION TYPE:", ["📍 INSTALLATION", "♻️ PICK-UP"], horizontal=True)
    up_files = st.file_uploader("DROP .EST / .TXT MAPS", type=["est", "txt"], accept_multiple_files=True)
    
    if up_files:
        st.success(f"✅ {len(up_files)} FILES READY.")
        configs = [{"file": f, "label": st.text_input(f"Label for Map {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
        
        if st.button("🚀 CALCULATE & SYNC ROUTE", use_container_width=True):
            status = st.empty()
            status.warning("⚡ PURIFYING BINARY DATA & ROUTING...")
            
            start_time = time.time()
            success, count = process_upload(configs, m_type)
            end_time = time.time()
            
            if success:
                calc_time = round(end_time - start_time, 2)
                status.success(f"✅ COMPLETE! Found {count} valid sites in {calc_time} seconds.")
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
        st.success(f"MISSION: {st.session_state.mission_type} | {len(st.session_state.optimized_route)} STOPS")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        
        st.divider()
        st.markdown("### 🛑 END OF DAY CHECKLIST")
        st.info("Streamlit servers delete their memory overnight. Download your backup now to resume your exact progress tomorrow.")
        
        payload = {
            "active_files": st.session_state.active_files,
            "optimized_route": st.session_state.optimized_route,
            "site_data": st.session_state.site_data,
            "current_index": st.session_state.current_index,
            "mission_type": st.session_state.mission_type,
            "pickup_index": st.session_state.get("pickup_index", 0),
            "pickup_itinerary": st.session_state.get("pickup_itinerary", [])
        }
        st.download_button(
            label="💾 DOWNLOAD ROUTE BACKUP",
            data=json.dumps(payload),
            file_name=f"LiveWire_Backup_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )

        st.divider()
        if st.button("🗑️ CLEAR ROUTE & START OVER", use_container_width=True):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            for k in ["active_files", "optimized_route", "pickup_itinerary"]: st.session_state[k] = []
            st.session_state.site_data = {}
            for k in ["current_index", "pickup_index"]: st.session_state[k] = 0
            st.rerun()

    with tab2:
        if "PICK-UP" in st.session_state.mission_type:
            st.warning("⚠️ You are currently in Pick-Up Mode. Go to the ♻️ PICK-UP tab.")
        else:
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
                
                st.subheader(f"STOP #{cur_idx+1}: SITE {sid}")
                st.caption(f"Sheet: {sd.get('Sheet')} | Raw GPS: `{s['lat']}, {s['lon']}`") 
                
                st.progress(cur_idx / total_sites)
                st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
                
                with st.form(key=f"f_v23_{sid}"):
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
                st.balloons(); st.success("🏁 INSTALLATION COMPLETED.")

    with tab3:
        installed = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
        if not installed: 
            st.info("No sites installed/ready yet. Ensure you are uploading a 'PICK-UP' mission map.")
        else:
            view_mode = st.radio("VIEW MODE", ["Focus Mode (1-by-1)", "List View"], horizontal=True)
            st.divider()

            itinerary = st.session_state.get("pickup_itinerary", installed)

            if view_mode == "List View":
                if st.button("🔄 Re-Optimize Pick-Up Order", use_container_width=True):
                    curr, new_itin, rem = HOME_COORDS, [], installed.copy()
                    while rem:
                        nxt = min(rem, key=lambda x: (curr[0]-x['LAT'])**2 + (curr[1]-x['LON'])**2)
                        new_itin.append(nxt); curr = (nxt['LAT'], nxt['LON']); rem.remove(nxt)
                    st.session_state.pickup_itinerary = new_itin; auto_save(); st.rerun()

                for i, s in enumerate(itinerary):
                    sid, is_picked = s["Site"], s["Picked up"] == "x"
                    status = "✅" if is_picked else "📦"
                    with st.expander(f"{status} #{i+1} - Site {sid}"):
                        if not is_picked:
                            st.caption(f"Raw GPS: `{s['LAT']}, {s['LON']}`")
                            st.link_button("🚗 Navigate to Spot", f"https://www.google.com/maps/dir/?api=1&destination={s['LAT']},{s['LON']}", use_container_width=True)
                            with st.form(key=f"pu_list_{sid}"):
                                p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                                if st.form_submit_button("MARK SECURED"):
                                    st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip(); auto_save(); st.rerun()
                        else: st.write(f"Secured.")
            
            else:
                # 1-by-1 Focus Mode
                p_idx = st.session_state.get("pickup_index", 0)
                if p_idx < len(itinerary):
                    s = itinerary[p_idx]
                    sid = s["Site"]
                    
                    st.subheader(f"PICK-UP #{p_idx+1}: SITE {sid}")
                    st.caption(f"Sheet: {s.get('Sheet')} | Raw GPS: `{s['LAT']}, {s['LON']}`") 
                    
                    st.progress(p_idx / len(itinerary))
                    st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['LAT']},{s['LON']}", use_container_width=True)
                    
                    with st.form(key=f"pu_focus_{sid}"):
                        p_notes = st.text_input("NOTES", value=s["Notes"])
                        
                        col_a, col_b = st.columns(2)
                        if col_a.form_submit_button("✅ SECURED", use_container_width=True):
                            st.session_state.site_data[sid]["Picked up"] = "x"
                            st.session_state.site_data[sid]["Notes"] = p_notes.strip()
                            st.session_state.pickup_index += 1
                            auto_save()
                            st.rerun()
                        if col_b.form_submit_button("🚨 MISSING/UNABLE", use_container_width=True):
                            st.session_state.site_data[sid]["Notes"] = f"UNABLE: {p_notes.upper()}"
                            st.session_state.pickup_index += 1
                            auto_save()
                            st.rerun()
                    
                    if p_idx > 0 and st.button("⬅️ PREVIOUS STOP", use_container_width=True):
                        st.session_state.pickup_index -= 1
                        auto_save()
                        st.rerun()
                else:
                    st.balloons()
                    st.success("🏁 ALL EQUIPMENT SECURED.")

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
                st.error("⚠️ Data Export Error. Please contact admin or download raw JSON backup.")
                st.write(e)


```
