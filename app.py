import streamlit as st
import re
import pandas as pd
import math
import json
import io
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_js_eval import streamlit_js_eval
from streamlit_local_storage import LocalStorage

# --- HIGH-PERFORMANCE CONFIG ---
st.set_page_config(page_title="Live Wire Ultra-Link", layout="centered")
localS = LocalStorage()

# --- ROAD-OPS AESTHETIC & BOTTOM HUD ---
st.markdown("""
    <style>
    .stApp { background-color: #0A0A0A; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; letter-spacing: -1px; }
    
    /* Standard Button Styling */
    div.stButton > button { 
        background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; 
        font-weight: 900; border-radius: 4px; transition: 0.3s;
    }
    div.stButton > button:active { transform: scale(0.95); background-color: #FFD700; color: #000; }
    
    /* Tabs & Inputs */
    .stTabs [data-baseweb="tab-list"] { background-color: #0A0A0A; border-bottom: 2px solid #333; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    input, select, textarea { background-color: #111 !important; color: #FFD700 !important; border: 1px solid #444 !important; }
    
    /* PIXEL 9 BOTTOM HUD LOADER */
    .bottom-hud {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background-color: #0A0A0A;
        border-top: 4px solid #FFD700;
        padding: 15px 20px 30px 20px;
        z-index: 999999;
        box-shadow: 0px -10px 20px rgba(0,0,0,0.9);
        text-align: center;
    }
    .hud-text { color: #FFD700; font-family: 'Arial Black'; font-size: 14px; margin-bottom: 12px; letter-spacing: 1px;}
    .hud-bar-bg { background-color: #333; width: 100%; height: 14px; border-radius: 7px; overflow: hidden; }
    .hud-bar-fill { background-color: #FFD700; height: 100%; transition: width 0.2s ease-in-out; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 Ultra-Link V5")

HOME_COORDS = (33.7715, -117.9431) 
STORAGE_KEY = "LIVE_WIRE_P9_PRO"

# --- ASYNC STORAGE ENGINE ---
def lock_state():
    payload = {
        "files": st.session_state.get("active_files", []),
        "route": st.session_state.get("optimized_route", []),
        "data": st.session_state.get("site_data", {}),
        "idx": st.session_state.get("current_index", 0)
    }
    localS.set(STORAGE_KEY, payload)

# --- INITIALIZATION & RECOVERY ---
if "init" not in st.session_state:
    cached = localS.get(STORAGE_KEY)
    if cached:
        st.session_state.active_files = cached.get("files", [])
        st.session_state.optimized_route = cached.get("route", [])
        st.session_state.site_data = cached.get("data", {})
        st.session_state.current_index = cached.get("idx", 0)
    else:
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

# --- APP TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 VAULT", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

# ==========================================
# TAB 1: VAULT (WITH BOTTOM HUD)
# ==========================================
with tab1:
    if not st.session_state.get("optimized_route"):
        st.subheader("INITIALIZE DAILY MISSION")
        up_files = st.file_uploader("DROP MAPS", type=["est", "txt"], accept_multiple_files=True)
        
        if up_files:
            configs = [{"file": f, "label": st.text_input(f"Work Order {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
            
            if st.button("🚀 SYNC & OPTIMIZE", use_container_width=True):
                # Trigger the HUD at the bottom of the screen
                hud_placeholder = st.empty()
                
                def update_hud(message, percentage):
                    hud_placeholder.markdown(f"""
                        <div class="bottom-hud">
                            <div class="hud-text">⏳ {message}</div>
                            <div class="hud-bar-bg"><div class="hud-bar-fill" style="width: {percentage}%;"></div></div>
                        </div>
                    """, unsafe_allow_html=True)

                update_hud("RECEIVING SECURE DATA...", 10)
                time.sleep(0.5) # Give UI a moment to render
                
                all_raw = []
                for idx, cfg in enumerate(configs):
                    update_hud(f"EXTRACTING: {cfg['file'].name.upper()}", 20 + (40 * (idx / len(configs))))
                    
                    content = cfg['file'].getvalue().decode('latin-1', errors='ignore')
                    matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', content)
                    for m in matches:
                        if m[0] == "3333": continue
                        all_raw.append({"id": str(m[0]), "lat": float(m[2]), "lon": float(m[3]), "sheet": cfg['label']})
                
                if all_raw:
                    update_hud("COMPUTING BEST ROAD PATH...", 80)
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: math.hypot(curr[0]-x['lat'], curr[1]-x['lon']))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    
                    st.session_state.optimized_route = route
                    st.session_state.active_files = [c['label'] for c in configs]
                    st.session_state.site_data = {s['id']: {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":None,"INSTALL_LON":None} for s in route}
                    
                    update_hud("LOCKING TO DEVICE MEMORY...", 95)
                    lock_state()
                    
                    update_hud("SYNC COMPLETE! ✅", 100)
                    time.sleep(1)
                    hud_placeholder.empty() # Remove HUD
                    st.rerun()
    else:
        st.success(f"ACTIVE ROUTE: {len(st.session_state.optimized_route)} STOPS")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        if st.button("🗑️ PURGE & RESET ALL", use_container_width=True):
            localS.delete(STORAGE_KEY)
            for key in ["active_files", "optimized_route", "site_data", "current_index"]:
                st.session_state[key] = [] if isinstance(st.session_state[key], list) else ({} if isinstance(st.session_state[key], dict) else 0)
            st.rerun()

# ==========================================
# TAB 2: INSTALL (PRECISION & GPS LOCK)
# ==========================================
with tab2:
    if not st.session_state.get("optimized_route"): st.info("WAITING FOR VAULT DATA...")
    else:
        raw_loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_V5')
        
        cur_idx = st.session_state.current_index
        if cur_idx < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur_idx]; sid = s['id']; sd = st.session_state.site_data[sid]
            
            st.subheader(f"#{cur_idx+1}: SITE {sid} [{sd.get('Sheet')}]")
            # Top progress bar for route tracking
            st.progress(cur_idx / len(st.session_state.optimized_route))
            
            st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
            
            with st.form(key=f"f_v5_{sid}"):
                c1, c2 = st.columns(2)
                with c1: dr = st.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(sd["Directions"]))
                with c2: ln = st.number_input("LANES", min_value=1, value=int(sd["Lanes"]))
                ser = st.text_input("SERIAL #", value=sd["Serial"])
                nt = st.text_input("NOTES", value=sd["Notes"])
                
                col_a, col_b = st.columns(2)
                if col_a.form_submit_button("✅ COMPLETE", use_container_width=True):
                    t, d = get_ca_time()
                    lat_c, lon_c = (json.loads(raw_loc) if raw_loc else (s['lat'], s['lon']))
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if dr in ["n","s"] else "e","Serial":ser,"Lanes":ln,"Notes":nt,"Installed":"x","INSTALL_LAT":lat_c,"INSTALL_LON":lon_c})
                    st.session_state.current_index += 1; lock_state(); st.rerun()
                if col_b.form_submit_button("🚨 UNABLE", use_container_width=True):
                    t, d = get_ca_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Notes":f"UNABLE: {nt.upper()}","Skipped":True})
                    st.session_state.current_index += 1; lock_state(); st.rerun()
            
            if cur_idx > 0 and st.button("⬅️ PREVIOUS STOP", use_container_width=True):
                st.session_state.current_index -= 1; lock_state(); st.rerun()
        else:
            st.balloons(); st.success("🏁 MISSION COMPLETED.")

# ==========================================
# TABS 3 & 4 (PICK-UP & EXCEL)
# ==========================================
with tab3:
    installed = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
    if not installed: st.info("No sites installed yet.")
    else:
        if st.button("🔄 Optimize Pick-Up Order", use_container_width=True):
            curr, new_itin, rem = HOME_COORDS, [], installed.copy()
            while rem:
                nxt = min(rem, key=lambda x: math.hypot(curr[0]-x['INSTALL_LAT'], curr[1]-x['INSTALL_LON']))
                new_itin.append(nxt); curr = (nxt['INSTALL_LAT'], nxt['INSTALL_LON']); rem.remove(nxt)
            st.session_state.pickup_itinerary = new_itin; st.success("Pick-Up sequence optimized.")

        itinerary = st.session_state.get("pickup_itinerary", installed)
        for i, s in enumerate(itinerary):
            sid, is_picked = s["Site"], s["Picked up"] == "x"
            status = "✅" if is_picked else "📦"
            with st.expander(f"{status} #{i+1} - Site {sid}"):
                if not is_picked:
                    st.link_button("🚗 GPS to Actual Spot", f"https://www.google.com/maps/dir/?api=1&destination={s['INSTALL_LAT']},{s['INSTALL_LON']}", use_container_width=True)
                    with st.form(key=f"pu_{sid}"):
                        p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                        if st.form_submit_button("MARK SECURED"):
                            st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip(); lock_state(); st.rerun()
                else: st.write(f"Secured.")

with tab4:
    all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x" or d.get("Skipped")]
    if all_d:
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
