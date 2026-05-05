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

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="Live Wire Precision Pro", layout="centered")

# Custom CSS for Road Aesthetic
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
    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        color: #CCCCCC;
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #FFD700 !important;
        border-bottom-color: #FFD700 !important;
    }
    /* Buttons */
    div.stButton > button:first-child {
        background-color: #444444;
        color: #FFD700;
        border: 2px solid #FFD700;
        border-radius: 10px;
    }
    /* Success/Green Action */
    div[data-testid="stForm"] button[kind="primary"] {
        background-color: #28a745 !important;
        color: white !important;
        border: none !important;
    }
    /* Alert/Red Action */
    .unable-btn {
        background-color: #dc3545 !important;
        color: white !important;
    }
    /* Metric Cards */
    [data-testid="stMetricValue"] {
        color: #FFD700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚦 Precision Field Collector")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "field_backup_precision.json"

# --- CORE LOGIC ---
def save_state():
    backup_data = {
        "active_files": st.session_state.active_files,
        "optimized_route": st.session_state.optimized_route,
        "site_data": st.session_state.site_data,
        "current_index": st.session_state.current_index
    }
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup_data, f)

def load_state():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                backup_data = json.load(f)
                st.session_state.active_files = backup_data.get("active_files", [])
                st.session_state.optimized_route = backup_data.get("optimized_route", [])
                st.session_state.site_data = backup_data.get("site_data", {})
                st.session_state.current_index = backup_data.get("current_index", 0)
                return True
        except: return False
    return False

if "initialized" not in st.session_state:
    if not load_state():
        st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
    st.session_state.initialized = True

def get_california_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0: now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- NAVIGATION ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 VAULT", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

# ==========================================
# TAB 1: VAULT
# ==========================================
with tab1:
    st.subheader("Load Work Orders")
    if not st.session_state.optimized_route:
        uploaded_files = st.file_uploader("Upload .est Maps", type=["est", "txt"], accept_multiple_files=True)
        if uploaded_files:
            configs = []
            for i, f in enumerate(uploaded_files):
                lbl = st.text_input(f"Sheet Label for {f.name}:", value=f"Day {i+1}", key=f"lbl_{i}")
                configs.append({"file": f, "label": lbl})
            
            if st.button("🚀 Calculate Efficiency Route", use_container_width=True):
                all_raw = []
                for c in configs:
                    raw_text = "".join([chr(b) if 32 <= b < 127 else " " for b in c["file"].read()])
                    matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', raw_text)
                    for m in matches:
                        if m[0] == "3333": continue
                        all_raw.append({"id": m[0], "lat": float(m[2]), "lon": float(m[3]), "sheet": c["label"]})
                
                if all_raw:
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    route, curr, rem = [], HOME_COORDS, df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: calculate_distance(curr, (x['lat'], x['lon'])))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    
                    st.session_state.optimized_route = route
                    st.session_state.active_files = [c["label"] for c in configs]
                    for s in route:
                        st.session_state.site_data[s['id']] = {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":None,"INSTALL_LON":None}
                    save_state(); st.rerun()
    else:
        st.success("Master Route Optimized")
        st.map(pd.DataFrame(st.session_state.optimized_route))
        if st.button("🗑️ Reset Application", use_container_width=True):
            st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# TAB 2: INSTALL (AESTHETIC UPGRADE)
# ==========================================
with tab2:
    if not st.session_state.optimized_route: st.info("Load maps first.")
    else:
        view = st.radio("Display Mode:", ["🎯 Focus", "📜 List"], horizontal=True)
        loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_CHECK')
        
        def render_form(sid, site_coords, index):
            s_data = st.session_state.site_data[sid]
            st.markdown(f"### Site {sid} ({s_data['Sheet']})")
            st.link_button("🚗 Start GPS Navigation", f"https://www.google.com/maps/dir/?api=1&destination={site_coords[0]},{site_coords[1]}", use_container_width=True)
            
            with st.form(key=f"prec_form_{sid}"):
                c1, c2 = st.columns(2)
                with c1: d_opt = ["n","e","s","w"]; direction = st.selectbox("Direction", d_opt, index=d_opt.index(s_data["Directions"]))
                with c2: lanes = st.number_input("Lanes", min_value=1, value=int(s_data["Lanes"]))
                serial = st.text_input("Serial Number", value=s_data["Serial"])
                notes = st.text_input("Notes (Field Observations)", value=s_data["Notes"])
                
                b1, b2 = st.columns(2)
                if b1.form_submit_button("✅ COMPLETE & LOG GPS", use_container_width=True):
                    t, d = get_california_time()
                    lat_cap, lon_cap = site_coords
                    if loc: 
                        coords = json.loads(loc)
                        lat_cap, lon_cap = coords[0], coords[1]
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e","Serial":serial,"Lanes":lanes,"Notes":notes,"Installed":"x","INSTALL_LAT":lat_cap,"INSTALL_LON":lon_cap})
                    if view == "🎯 Focus": st.session_state.current_index += 1
                    save_state(); st.rerun()
                
                if b2.form_submit_button("🚨 UNABLE TO INSTALL", use_container_width=True):
                    t, d = get_california_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Notes":f"SKIPPED: {notes.upper()}","Skipped":True})
                    if view == "🎯 Focus": st.session_state.current_index += 1
                    save_state(); st.rerun()

        if view == "🎯 Focus":
            idx = st.session_state.current_index
            if idx < len(st.session_state.optimized_route):
                s = st.session_state.optimized_route[idx]
                st.subheader(f"Stop #{idx+1} of {len(st.session_state.optimized_route)}")
                st.progress((idx) / len(st.session_state.optimized_route))
                render_form(s['id'], (s['lat'], s['lon']), idx)
                if idx > 0 and st.button("⬅️ PREVIOUS STOP"): st.session_state.current_index -= 1; st.rerun()
            else: st.balloons(); st.success("🏁 All installations handled.")
        else:
            for i, s in enumerate(st.session_state.optimized_route):
                s_data = st.session_state.site_data[s['id']]
                is_done = s_data["Installed"] == "x" or s_data.get("Skipped")
                icon = "✅" if s_data["Installed"] == "x" else ("🚫" if s_data.get("Skipped") else "📝")
                with st.expander(f"{icon} #{i+1} - SITE {s['id']}"):
                    if not is_done: render_form(s['id'], (s['lat'], s['lon']), i)
                    else: 
                        st.write(f"Logged: {s_data['Time']} | Dir: {s_data['Directions']}")
                        if st.button("✏️ EDIT", key=f"ed_{s['id']}"): 
                            st.session_state.site_data[s['id']]["Installed"] = ""; st.session_state.site_data[s['id']]["Skipped"] = False; st.rerun()

# ==========================================
# TAB 3: PICK-UP
# ==========================================
with tab3:
    installed = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
    if not installed: st.info("No sites installed yet.")
    else:
        if st.button("🔄 Optimize Pick-Up Order", use_container_width=True):
            curr, new_itin, rem = HOME_COORDS, [], installed.copy()
            while rem:
                nxt = min(rem, key=lambda x: calculate_distance(curr, (x['INSTALL_LAT'], x['INSTALL_LON'])))
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
                            st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip(); save_state(); st.rerun()
                else: st.write(f"Secured.")

# ==========================================
# TAB 4: EXCEL
# ==========================================
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
