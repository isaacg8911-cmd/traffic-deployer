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
    
    div.stButton > button { 
        background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; 
        font-weight: 900; border-radius: 4px; transition: 0.3s;
    }
    div.stButton > button:active { transform: scale(0.95); background-color: #FFD700; color: #000; }
    
    .stTabs [data-baseweb="tab-list"] { background-color: #0A0A0A; border-bottom: 2px solid #333; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    input, select, textarea { background-color: #111 !important; color: #FFD700 !important; border: 1px solid #444 !important; }
    
    /* PIXEL 9 BOTTOM HUD LOADER */
    .bottom-hud {
        position: fixed;
        bottom: 0; left: 0; width: 100%;
        background-color: #0A0A0A; border-top: 4px solid #FFD700;
        padding: 15px 20px 30px 20px; z-index: 999999;
        box-shadow: 0px -10px 20px rgba(0,0,0,0.9); text-align: center;
    }
    .hud-text { color: #FFD700; font-family: 'Arial Black'; font-size: 14px; margin-bottom: 12px; letter-spacing: 1px;}
    .hud-bar-bg { background-color: #333; width: 100%; height: 14px; border-radius: 7px; overflow: hidden; }
    .hud-bar-fill { background-color: #FFD700; height: 100%; transition: width 0.2s ease-in-out; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 Ultra-Link V6")

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

# --- INITIALIZATION ---
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
# TAB 1: VAULT (IRON-GRIP UPLOADER)
# ==========================================
with tab1:
    if not st.session_state.get("optimized_route"):
        
        # Connection Wake-Up Button
        if st.button("🔄 WAKE UP CONNECTION", use_container_width=True):
            st.rerun()
            
        st.subheader("INITIALIZE DAILY MISSION")
        up_files = st.file_uploader("DROP MAPS (.EST / .TXT)", type=["est", "txt"], accept_multiple_files=True)
        
        # IRON GRIP: Only show the rest if files are 100% in memory
        if up_files:
            st.success(f"✅ {len(up_files)} FILES SECURED IN MEMORY.")
            
            configs = [{"file": f, "label": st.text_input(f"Work Order {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
            
            if st.button("🚀 SYNC & OPTIMIZE", use_container_width=True):
                hud_placeholder = st.empty()
                
                def update_hud(message, percentage):
                    hud_placeholder.markdown(f"""
                        <div class="bottom-hud">
                            <div class="hud-text">⏳ {message}</div>
                            <div class="hud-bar-bg"><div class="hud-bar-fill" style="width: {percentage}%;"></div></div>
                        </div>
                    """, unsafe_allow_html=True)

                update_hud("RECEIVING SECURE DATA...", 10)
                time.sleep(0.5) 
                
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
                    hud_placeholder.empty() 
                    st.rerun()
                else:
                    update_hud("ERROR: NO SITES FOUND IN FILES.", 0)
                    time.sleep(3)
                    hud_placeholder.empty()
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
        raw_loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_V6')
        
        cur_idx = st.session_state.current_index
        if cur_idx < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur_idx]; sid = s['id']; sd = st.session_state.site_data[sid]
            
            st.subheader(f"#{cur_idx+1}: SITE {sid} [{sd.get('Sheet')}]")
            st.progress(cur_idx / len(st.session_state.optimized_route))
            st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
            
            with st.form(key
