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

# --- THEME & AESTHETIC ---
st.set_page_config(page_title="Live Wire Precision Pro", layout="centered")

st.markdown("""
    <style>
    /* Main Background - Asphalt Grey */
    .stApp {
        background-color: #2F2F2F;
        color: #FFFFFF;
    }
    /* Headers - Caution Yellow */
    h1, h2, h3 {
        color: #FFD700 !important;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    /* Tabs Customization */
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #FFD700 !important;
        border-bottom-color: #FFD700 !important;
    }
    /* Buttons - Heavy Duty Style */
    div.stButton > button:first-child {
        background-color: #444444;
        color: #FFD700;
        border: 2px solid #FFD700;
        border-radius: 10px;
        font-weight: bold;
    }
    /* Progress Bar - Road Stripe Yellow */
    .stProgress > div > div > div > div {
        background-color: #FFD700;
    }
    /* GPS Status Styling */
    .gps-locked { 
        color: #1DA1F2; 
        font-weight: bold; 
        border: 2px solid #1DA1F2; 
        padding: 10px; 
        border-radius: 10px; 
        text-align: center; 
        margin-bottom: 15px;
        background-color: rgba(29, 161, 242, 0.1);
    }
    .gps-warning { 
        color: #FF4B4B; 
        font-weight: bold; 
        border: 2px solid #FF4B4B; 
        padding: 10px; 
        border-radius: 10px; 
        text-align: center; 
        margin-bottom: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 Field Data Collector")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "field_backup_precision.json"

# --- PERSISTENCE ENGINE ---
def save_state():
    try:
        backup_data = {
            "active_files": st.session_state.active_files,
            "optimized_route": st.session_state.optimized_route,
            "site_data": st.session_state.site_data,
            "current_index": st.session_state.current_index,
            "last_sync": datetime.now().strftime("%H:%M:%S")
        }
        with open(BACKUP_FILE, "w") as f:
            json.dump(backup_data, f)
    except: pass

def load_state():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                st.session_state.active_files = data.get("active_files", [])
                st.session_state.optimized_route = data.get("optimized_route", [])
                st.session_state.site_data = data.get("site_data", {})
                st.session_state.current_index = data.get("current_index", 0)
                st.session_state.last_sync = data.get("last_sync", "N/A")
                return True
        except: return False
    return False

if "initialized" not in st.session_state:
    if not load_state():
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data = [], [], {}
        st.session_state.current_index, st.session_state.last_sync = 0, "N/A"
    st.session_state.initialized = True

def get_california_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

# --- NAVIGATION TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 VAULT", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

# ==========================================
# TAB 1: VAULT (MULTI-FILE MERGING)
# ==========================================
with tab1:
    if not st.session_state.optimized_route:
        st.subheader("Load Route Files")
        files = st.file_uploader("Upload .est Maps", accept_multiple_files=True)
        if files:
            configs = []
            for i, f in enumerate(files):
                lbl = st.text_input(f"Sheet Name for {f.name}:", value=f"Day {i+1}", key=f"label_{i}")
                configs.append({"file": f, "label": lbl})
            
            if st.button("🚀 Calculate & Sync Route", use_container_width=True):
                all_raw = []
                for c in configs:
                    raw = "".join([chr(b) if 32 <= b < 127 else " " for b in c["file"].read()])
                    matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', raw)
                    for m in matches:
                        if m[0] == "3333": continue
                        all_raw.append({"id": m[0], "lat": float(m[2]), "lon": float(m[3]), "sheet": c["label"]})
                
                if all_raw:
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: math.sqrt((curr[0]-x['lat'])**2 + (curr[1]-x['lon'])**2))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    st.session_state.optimized_route = route
                    st.session_state.active_files = [c["label"] for c in configs]
                    for s in route:
                        st.session_state.site_data[s['id']] = {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":s['lat'],"INSTALL_LON":s['lon']}
                    save_state(); st.rerun()
    else:
        st.success(f"Route Active: {len(st.session_state.optimized_route)} Stops")
        st.map(pd.DataFrame(st.session_state.optimized_route))
        with st.expander("⚠️ Danger Zone"):
            if st.checkbox("Confirm: I want to wipe all current progress"):
                if st.button("🗑️ Reset Application", type="primary", use_container_width=True):
                    if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
                    st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
                    st.rerun()

# ==========================================
# TAB 2: INSTALL (BLUE CHECK GPS VERIFICATION)
# ==========================================
with tab2:
    if not st.session_state.optimized_route: st.info("Load maps in Vault.")
    else:
        view = st.radio("Display View:", ["🎯 Focus Mode", "📜 List Mode"], horizontal=True)
        # Fetch Hardware GPS from Pixel 9
        loc_raw = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_PRO_LOCK')
        
        def run_install(sid, coords, i):
            sd = st.session_state.site_data[sid]
            st.markdown(f"### Stop #{i+1}: Site {sid} ({sd.get('Sheet','Day')})")
            st.link_button("🚗 Start GPS Navigation", f"https://www.google.com/maps/dir/?api=1&destination={coords[0]},{coords[1]}", use_container_width=True)
            
            # THE BLUE CHECK INDICATOR
            if loc_raw:
                st.markdown('<div class="gps-locked">✅ GPS LOCK ACQUIRED</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="gps-warning">⚠️ WAITING FOR PIXEL GPS SIGNAL...</div>', unsafe_allow_html=True)
            
            with st.form(key=f"form_{sid}"):
                c1, c2 = st.columns(2)
                with c1: d_opt = ["n","e","s","w"]; direction = st.selectbox("Direction", d_opt, index=d_opt.index(sd["Directions"]))
                with c2: lanes = st.number_input("Lanes", min_value=1, value=int(sd["Lanes"]))
                serial = st.text_input("Serial Number", value=sd["Serial"])
                notes = st.text_input("Notes", value=sd["Notes"])
                
                ca, cb = st.columns(2)
                if ca.form_submit_button("✅ COMPLETE ➡️"):
                    t, d = get_california_time()
                    lat_c, lon_c = coords
                    if loc_raw: 
                        c_vals = json.loads(loc_raw); lat_c, lon_c = c_vals[0], c_vals[1]
                    st.session_state.site_data[sid].update({
                        "Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e",
                        "Serial":serial,"Lanes":lanes,"Notes":notes.upper(),"Installed":"x",
                        "INSTALL_LAT":lat_c,"INSTALL_LON":lon_c
                    })
                    if view == "🎯 Focus Mode": st.session_state.current_index += 1
                    save_state(); st.rerun()
                
                if cb.form_submit_button("🚨 UNABLE"):
                    t, d = get_california_time()
                    st.session_state.site_data[sid].update({
                        "Date":d,"Time":t,"Notes":f"SKIPPED: {notes.upper()}","Skipped":True
                    })
                    if view == "🎯 Focus Mode": st.session_state.current_index += 1
                    save_state(); st.rerun()

        if view == "🎯 Focus Mode":
            idx = st.session_state.current_index
            if idx < len(st.session_state.optimized_route):
                s = st.session_state.optimized_route[idx]
                st.progress(idx / len(st.session_state.optimized_route))
                run_install(s['id'], (s['lat'], s['lon']), idx)
                if idx > 0 and st.button("⬅️ Back"): st.session_state.current_index -= 1; st.rerun()
            else: st.success("🏁 All installations complete.")
        else:
            for i, s in enumerate(st.session_state.optimized_route):
                sd = st.session_state.site_data[s['id']]
                is_done = sd["Installed"] == "x" or sd.get("Skipped")
                icon = "✅" if sd["Installed"] == "x" else ("🚫" if sd.get("Skipped") else "📝")
                with st.expander(f"{icon} Stop #{i+1} - Site {s['id']}"):
                    if not is_done: run_install(s['id'], (s['lat'], s['lon']), i)
                    else:
                        if st.button("✏️ Edit Entry", key=f"ed_{s['id']}"):
                            st.session_state.site_data[s['id']]["Installed"] = ""; st.session_state.site_data[s['id']]["Skipped"] = False; save_state(); st.rerun()

# ==========================================
# TAB 3: PICK-UP (ACTUAL LOCATION ROUTING)
# ==========================================
with tab3:
    installed = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
    if not installed: st.info("No sites to pick up.")
    else:
        if st.button("🔄 Optimize Pick-Up Sequence", use_container_width=True):
            curr, itin, rem = HOME_COORDS, [], installed.copy()
            while rem:
                nxt = min(rem, key=lambda x: math.sqrt((curr[0]-x['INSTALL_LAT'])**2 + (curr[1]-x['INSTALL_LON'])**2))
                itin.append(nxt); curr = (nxt['INSTALL_LAT'], nxt['INSTALL_LON']); rem.remove(nxt)
            st.session_state.pickup_itinerary = itin; st.success("Pick-up sequence updated.")

        itin = st.session_state.get("pickup_itinerary", installed)
        for i, s in enumerate(itin):
            sid, done = s["Site"], s["Picked up"] == "x"
            status = "✅" if done else "📦"
            with st.expander(f"{status} #{i+1} - Site {sid}"):
                if not done:
                    st.link_button("🚗 GPS to Actual Truck Spot", f"https://www.google.com/maps/dir/?api=1&destination={s['INSTALL_LAT']},{s['INSTALL_LON']}")
                    with st.form(key=f"pu_{sid}"):
                        p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                        if st.form_submit_button("MARK SECURED"):
                            st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip().upper(); save_state(); st.rerun()

# ==========================================
# TAB 4: MULTI-SHEET EXCEL
# ==========================================
with tab4:
    all_d = [d for d in st.session_state.site_data.values() if d["Installed"] == "x" or d.get("Skipped")]
    if all_d:
        full_df = pd.DataFrame(all_d)
        cols = ["Date", "Time", "Site", "Counter", "Serial", "Directions", "Lanes", "Notes", "Installed", "Picked up"]
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            for name in st.session_state.active_files:
                df = full_df[full_df["Sheet"] == name]
                if not df.empty:
                    df[cols].to_excel(writer, index=False, sheet_name=name)
                    st.write(f"**Day: {name}**"); st.dataframe(df[cols], use_container_width=True)
        st.divider()
        st.download_button("📊 DOWNLOAD MASTER WORKBOOK", out.getvalue(), f"Traffic_Precision.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)

# --- SIDEBAR SYNC STATUS ---
st.sidebar.markdown(f"**Disk Sync:** ✅ ACTIVE")
st.sidebar.markdown(f"**Last Backup:** {st.session_state.get('last_sync', 'N/A')}")
