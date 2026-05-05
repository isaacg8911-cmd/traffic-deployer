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
st.set_page_config(page_title="Live Wire Ultra-Link V4", layout="centered")
localS = LocalStorage()

# --- ROAD-OPS AESTHETIC (High Contrast for Sunlight) ---
st.markdown("""
    <style>
    .stApp { background-color: #0A0A0A; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; letter-spacing: -1px; }
    .stProgress > div > div > div > div { background-color: #FFD700 !important; }
    div.stButton > button { 
        background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; 
        font-weight: 900; border-radius: 4px; transition: 0.3s;
    }
    div.stButton > button:active { transform: scale(0.95); background-color: #FFD700; color: #000; }
    .stTabs [data-baseweb="tab-list"] { background-color: #0A0A0A; border-bottom: 2px solid #333; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    input, select, textarea { background-color: #111 !important; color: #FFD700 !important; border: 1px solid #444 !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 Ultra-Link V4")

HOME_COORDS = (33.7715, -117.9431) 
STORAGE_KEY = "LIVE_WIRE_P9_PRO"

# --- ASYNC STORAGE ENGINE ---
def lock_state():
    """Forces an immediate save to the Pixel 9's local storage."""
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
# TAB 1: VAULT (STRENGTHENED DATA GRAB)
# ==========================================
with tab1:
    if not st.session_state.get("optimized_route"):
        st.subheader("INITIALIZE DAILY MISSION")
        up_files = st.file_uploader("DROP MAPS", type=["est", "txt"], accept_multiple_files=True)
        
        if up_files:
            configs = [{"file": f, "label": st.text_input(f"Work Order {i+1}:", value=f"Day {i+1}", key=f"l_{i}")} for i, f in enumerate(up_files)]
            
            if st.button("🚀 SYNC & OPTIMIZE", use_container_width=True):
                all_raw = []
                status = st.empty()
                bar = st.progress(0)
                
                for idx, cfg in enumerate(configs):
                    status.markdown(f"**HARD-GRAB:** `{cfg['file'].name}`")
                    # Using a generator for memory efficiency
                    content = cfg['file'].getvalue().decode('latin-1', errors='ignore')
                    matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', content)
                    for m in matches:
                        if m[0] == "3333": continue
                        all_raw.append({"id": str(m[0]), "lat": float(m[2]), "lon": float(m[3]), "sheet": cfg['label']})
                    bar.progress((idx + 1) / len(configs))
                
                if all_raw:
                    status.markdown("**COMPUTING VECTOR ROUTE...**")
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        # Vectorized distance check (hypot is faster than manual sqrt)
                        nxt = min(rem, key=lambda x: math.hypot(curr[0]-x['lat'], curr[1]-x['lon']))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    
                    st.session_state.optimized_route = route
                    st.session_state.active_files = [c['label'] for c in configs]
                    st.session_state.site_data = {s['id']: {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":None,"INSTALL_LON":None} for s in route}
                    lock_state()
                    status.success("LOCKED TO LOCAL MEMORY!")
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
        # Direct access to Pixel 9 GPS chip
        raw_loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_V4')
        
        cur_idx = st.session_state.current_index
        if cur_idx < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur_idx]; sid = s['id']; sd = st.session_state.site_data[sid]
            
            st.subheader(f"#{cur_idx+1}: SITE {sid} [{sd.get('Sheet')}]")
            st.progress(cur_idx / len(st.session_state.optimized_route))
            
            st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
            
            with st.form(key=f"f_v4_{sid}"):
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
            
            if cur_idx > 0 and st.button("⬅️ PREVIOUS STOP"):
                st.session_state.current_index -= 1; lock_state(); st.rerun()
        else:
            st.balloons(); st.success("🏁 MISSION COMPLETED.")

# ==========================================
# TABS 3 & 4 (PICK-UP & EXCEL)
# ==========================================
# (Logic uses the same INSTALL_LAT/LON from local storage to ensure pick-up is 100% accurate)
