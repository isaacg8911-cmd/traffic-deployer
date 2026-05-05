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

st.set_page_config(page_title="Live Wire Precision Pro", layout="centered")
st.title("🚦 Precision Field Collector")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "field_backup precision.json"

# --- AUTO-SAVE & Precision CAPTURE ---
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
tab1, tab2, tab3, tab4 = st.tabs(["📁 Vault", "📍 Install", "♻️ Pick-Up", "📊 Excel"])

# ==========================================
# TAB 1: VAULT (Merging & Verifying)
# ==========================================
with tab1:
    if not st.session_state.optimized_route:
        uploaded_files = st.file_uploader("Upload .est Maps", type=["est", "txt"], accept_multiple_files=True)
        if uploaded_files:
            configs = []
            for i, f in enumerate(uploaded_files):
                lbl = st.text_input(f"Sheet for {f.name}:", value=f"Day {i+1}", key=f"lbl_{i}")
                configs.append({"file": f, "label": lbl})
            
            if st.button("🚀 Calculate Master Efficiency Route"):
                all_raw = []
                for c in configs:
                    raw_text = "".join([chr(b) if 32 <= b < 127 else " " for b in c["file"].read()])
                    matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', raw_text)
                    for m in matches:
                        if m[0] == "3333": continue
                        all_raw.append({"id": m[0], "lat": float(m[2]), "lon": float(m[3]), "sheet": c["label"]})
                
                if all_raw:
                    df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    route = []
                    curr = HOME_COORDS
                    rem = df.to_dict('records')
                    while rem:
                        nxt = min(rem, key=lambda x: calculate_distance(curr, (x['lat'], x['lon'])))
                        route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
                    
                    st.session_state.optimized_route = route
                    st.session_state.active_files = [c["label"] for c in configs]
                    for s in route:
                        st.session_state.site_data[s['id']] = {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet'],"INSTALL_LAT":None,"INSTALL_LON":None}
                    save_state(); st.rerun()
    else:
        st.success("Merged Route Active")
        st.map(pd.DataFrame(st.session_state.optimized_route))
        if st.button("🗑️ Reset Everything"):
            st.session_state.active_files, st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], [], {}, 0
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# TAB 2: INSTALL (GPS CAPTURE)
# ==========================================
with tab2:
    if not st.session_state.optimized_route: st.info("Load maps first.")
    else:
        view = st.radio("Mode:", ["🎯 Focus", "📜 List"], horizontal=True)
        
        # --- INTERNAL GPS CAPTURE TOOL ---
        # This hidden component fetches the phone's chip coordinates
        loc = streamlit_js_eval(js_expressions='done(JSON.stringify([latitude,longitude]))', key='GPS_CHECK')
        
        def render_form(sid, site_coords):
            s_data = st.session_state.site_data[sid]
            st.markdown(f"**Verification:** Target is at `{site_coords[0]}, {site_coords[1]}`")
            st.link_button("🚗 Open Navigation", f"https://www.google.com/maps/dir/?api=1&destination={site_coords[0]},{site_coords[1]}", use_container_width=True)
            
            with st.form(key=f"precision_form_{sid}"):
                c1, c2 = st.columns(2)
                with c1: d_opt = ["n","e","s","w"]; direction = st.selectbox("Dir", d_opt, index=d_opt.index(s_data["Directions"]))
                with c2: lanes = st.number_input("Lanes", min_value=1, value=int(s_data["Lanes"]))
                serial = st.text_input("Serial Number", value=s_data["Serial"])
                notes = st.text_input("Notes", value=s_data["Notes"])
                
                b1, b2 = st.columns(2)
                if b1.form_submit_button("COMPLETE & LOG GPS ➡️"):
                    t, d = get_california_time()
                    lat_cap, lon_cap = site_coords # Default to target
                    if loc: # If phone GPS is shared, override with exact truck spot
                        coords = json.loads(loc)
                        lat_cap, lon_cap = coords[0], coords[1]
                    
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e","Serial":serial,"Lanes":lanes,"Notes":notes,"Installed":"x","INSTALL_LAT":lat_cap,"INSTALL_LON":lon_cap})
                    if view == "🎯 Focus": st.session_state.current_index += 1
                    save_state(); st.rerun()
                
                if b2.form_submit_button("🚨 UNABLE"):
                    t, d = get_california_time()
                    st.session_state.site_data[sid].update({"Date":d,"Time":t,"Notes":f"UNABLE: {notes.upper()}","Skipped":True})
                    if view == "🎯 Focus": st.session_state.current_index += 1
                    save_state(); st.rerun()

        if view == "🎯 Focus":
            idx = st.session_state.current_index
            if idx < len(st.session_state.optimized_route):
                s = st.session_state.optimized_route[idx]
                st.subheader(f"Stop {idx+1}: Site {s['id']}")
                render_form(s['id'], (s['lat'], s['lon']))
                if idx > 0 and st.button("⬅️ Previous"): st.session_state.current_index -= 1; st.rerun()
            else: st.success("🏁 Day Complete.")
        else:
            for i, s in enumerate(st.session_state.optimized_route):
                is_done = st.session_state.site_data[s['id']]["Installed"] == "x" or st.session_state.site_data[s['id']].get("Skipped")
                icon = "✅" if is_done else "📝"
                with st.expander(f"{icon} Site {s['id']}"):
                    if not is_done: render_form(s['id'], (s['lat'], s['lon']))
                    else: 
                        st.write("Logged.")
                        if st.button("✏️ Edit", key=f"ed_{s['id']}"): 
                            st.session_state.site_data[s['id']]["Installed"] = ""; st.session_state.site_data[s['id']]["Skipped"] = False; st.rerun()

# ==========================================
# TAB 3: PICK-UP (Precision Routing)
# ==========================================
with tab3:
    # Get all sites that were actually installed
    installed = [d for d in st.session_state.site_data.values() if d["Installed"] == "x"]
    
    if not installed: st.info("No installations to pick up yet.")
    else:
        st.subheader("Optimized Pick-Up Route")
        # --- RE-OPTIMIZE PICK UP BASED ON INSTALL GPS ---
        if st.button("🔄 Re-Calculate Pick-Up Efficiency"):
            curr = HOME_COORDS
            new_itinerary = []
            rem = installed.copy()
            while rem:
                # Use the INSTALL_LAT/LON (where you actually parked) for the calculation
                nxt = min(rem, key=lambda x: calculate_distance(curr, (x['INSTALL_LAT'], x['INSTALL_LON'])))
                new_itinerary.append(nxt); curr = (nxt['INSTALL_LAT'], nxt['INSTALL_LON']); rem.remove(nxt)
            st.session_state.pickup_itinerary = new_itinerary
            st.success("Pick-Up route optimized based on your exact install locations.")

        itinerary = st.session_state.get("pickup_itinerary", installed)
        for s in itinerary:
            sid = s["Site"]; is_picked = s["Picked up"] == "x"
            if not is_picked:
                with st.expander(f"📦 {s['Sheet']} - Site {sid}"):
                    # Direct navigation to the EXACT spot you clicked "Complete" during install
                    st.link_button("🚗 GPS to Install Spot", f"https://www.google.com/maps/dir/?api=1&destination={s['INSTALL_LAT']},{s['INSTALL_LON']}")
                    with st.form(key=f"pu_{sid}"):
                        p_notes = st.text_input("Notes", value=s["Notes"])
                        if st.form_submit_button("Mark Picked Up"):
                            st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip(); save_state(); st.rerun()

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
                    st.write(f"**Sheet: {sheet_name}**"); st.dataframe(final, use_container_width=True)
        st.download_button("📊 Download Precise Workbook", output.getvalue(), f"Traffic_Precision_{datetime.now().strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
