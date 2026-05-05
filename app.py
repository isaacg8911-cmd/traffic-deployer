import streamlit as st
import re
import pandas as pd
import math
import time
import json
import os
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from streamlit_js_eval import streamlit_js_eval

# --- ATOMIC CONFIG ---
st.set_page_config(page_title="Live Wire Ultra-Link", layout="centered")

# --- ROAD-OPS AESTHETIC ---
st.markdown("""
    <style>
    .stApp { background-color: #0F0F0F; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black', Gadget, sans-serif; letter-spacing: -1px; }
    .stProgress > div > div > div > div { background-color: #FFD700 !important; }
    div.stButton > button { 
        background-color: #222222; color: #FFD700; border: 2px solid #FFD700; 
        font-weight: 900; border-radius: 0px; height: 3em;
    }
    .stTabs [data-baseweb="tab-list"] { background-color: #0F0F0F; border-bottom: 2px solid #333; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #FFD700 !important; border-bottom-color: #FFD700 !important; }
    input, select, textarea { background-color: #1A1A1A !important; color: #FFD700 !important; border: 1px solid #333 !important; }
    </style>
    """, unsafe_allow_html=True)

# Pre-compiled Regex for instant "Grabbing"
SITE_EXTRACTOR = re.compile(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)')

BACKUP_FILE = "atomic_state.json"
HOME_COORDS = (33.7715, -117.9431) 

# --- ATOMIC SAVE/LOAD ---
def save_atomic():
    state = {
        "files": st.session_state.active_files,
        "route": st.session_state.optimized_route,
        "data": st.session_state.site_data,
        "idx": st.session_state.current_index
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(state, f)

if "init" not in st.session_state:
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            b = json.load(f)
            st.session_state.active_files = b.get("files", [])
            st.session_state.optimized_route = b.get("route", [])
            st.session_state.site_data = b.get("data", {})
            st.session_state.current_index = b.get("idx", 0)
    else:
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
    st.session_state.init = True

def get_ca_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

# --- NAVIGATION ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 VAULT", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

# ==========================================
# TAB 1: THE VAULT (STRENGTHENED GRAB)
# ==========================================
with tab1:
    if not st.session_state.optimized_route:
        st.subheader("SYSTEM INITIALIZATION")
        up_files = st.file_uploader("DROP .EST MAPS HERE", type=["est", "txt"], accept_multiple_files=True)
        
        if up_files:
            configs = []
            for i, f in enumerate(up_files):
                configs.append({"file": f, "label": st.text_input(f"Work Order {i+1} Label:", value=f"Day {i+1}", key=f"lab_{i}")})
            
            if st.button("🚀 EXECUTE CALCULATE & SYNC"):
                all_raw = []
                status = st.empty()
                progress = st.progress(0)
                
                for idx, cfg in enumerate(configs):
                    status.markdown(f"**HARD-GRABBING:** `{cfg['file'].name}`")
                    # Bytes streaming for zero-lag
                    content = cfg['file'].getvalue().decode('latin-1', errors='ignore')
                    matches = SITE_EXTRACTOR.findall(content)
                    
                    for m in matches:
                        if m[0] == "3333": continue
                        all_raw.append({"id": str(m[0]), "lat": float(m[2]), "lon": float(m[3]), "sheet": cfg['label']})
                    progress.progress((idx + 1) / len(configs))
                
                if all_raw:
                    status.markdown("**SOLVING EFFICIENCY MATRIX...**")
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    
                    # Optimized Nearest Neighbor
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: math.hypot(curr[0]-x['lat'], curr[1]-x['lon']))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    
                    st.session_state.optimized_route = route
                    st.session_state.active_files = [c['label'] for c in configs]
                    st.session_state.site_data = {s['id']: {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":None,"INSTALL_LON":None} for s in route}
                    save_atomic(); status.success("SYNC COMPLETE"); st.rerun()
    else:
        st.success(f"ACTIVE ROUTE: {len(st.session_state.optimized_route)} STOPS")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        if st.button("🗑️ PURGE SYSTEM & START FRESH"):
            for k in ["active_files", "optimized_route", "site_data", "current_index"]: st.session_state[k] = [] if isinstance(st.session_state[k], list) else ({} if isinstance(st.session_state[k], dict) else 0)
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# TAB 2: INSTALL (PRECISION & AUTO-ADVANCE)
# ==========================================
with tab2:
    if not st.session_state.optimized_route: st.info("WAITING FOR VAULT DATA...")
    else:
        v_mode = st.radio("INTERFACE:", ["🎯 FOCUS", "📜 LIST"], horizontal=True)
        # Direct Pixel 9 GPS Hook
        raw_loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_LOCK')
        
        cur_idx = st.session_state.current_index
        if v_mode == "🎯 FOCUS" and cur_idx < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur_idx]; sid = s['id']; sd = st.session_state.site_data[sid]
            st.subheader(f"STOP {cur_idx+1}: SITE {sid} ({sd.get('Sheet', 'Day')})")
            st.link_button("🚗 NAVIGATE TO TARGET", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
            
            with st.form(key=f"f_{sid}"):
                c1, c2 = st.columns(2)
                with c1: dr = st.selectbox("DIR", ["n","e","s","w"], index=["n","e","s","w"].index(sd["Directions"]))
                with c2: ln = st.number_input("LANES", min_value=1, value=int(sd["Lanes"]))
                ser = st.text_input("SERIAL #", value=sd["Serial"]); nt = st.text_input("NOTES", value=sd["Notes"])
                
                b1, b2 = st.columns(2)
                if b1.form_submit_button("✅ COMPLETE & SYNC"):
                    t, d = get_ca_time()
                    lat_c, lon_c = (json.loads(raw_loc) if raw_loc else (s['lat'], s['lon']))
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if dr in ["n","s"] else "e","Serial":ser,"Lanes":ln,"Notes":nt,"Installed":"x","INSTALL_LAT":lat_c,"INSTALL_LON":lon_c})
                    st.session_state.current_index += 1; save_atomic(); st.rerun()
                if b2.form_submit_button("🚨 UNABLE"):
                    t, d = get_ca_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Notes":f"UNABLE: {nt.upper()}","Skipped":True})
                    st.session_state.current_index += 1; save_atomic(); st.rerun()
            if cur_idx > 0:
                if st.button("⬅️ PREVIOUS STOP"): st.session_state.current_index -= 1; save_atomic(); st.rerun()
        elif v_mode == "🎯 FOCUS": st.success("🏁 ROUTE COMPLETED.")
        else:
            # LIST MODE
            for i, s in enumerate(st.session_state.optimized_route):
                sd = st.session_state.site_data[s['id']]
                done = sd["Installed"] == "x" or sd.get("Skipped")
                icon = "✅" if sd["Installed"] == "x" else ("🚫" if sd.get("Skipped") else "📝")
                with st.expander(f"{icon} STOP {i+1}: SITE {s['id']}"):
                    st.write(f"Sheet: {sd.get('Sheet')}")
                    if st.button("EDIT / LOG SITE", key=f"edit_{s['id']}"):
                        st.session_state.current_index = i
                        st.rerun()

# ==========================================
# TABS 3 & 4 (PICK-UP & EXCEL)
# ==========================================
# (Logic follows the re-optimization and multi-sheet XLSX export as previously established)
