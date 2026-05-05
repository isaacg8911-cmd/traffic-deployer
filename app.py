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

st.set_page_config(page_title="Live Wire Field Pro", layout="centered")
st.title("🚦 Field Data Collector")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "field_backup.json"

# --- AUTO-SAVE LOGIC ---
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

# --- SESSION STATES ---
if "initialized" not in st.session_state:
    if not load_state():
        st.session_state.active_files = []
        st.session_state.optimized_route = []
        st.session_state.site_data = {} 
        st.session_state.current_index = 0
    st.session_state.initialized = True

def get_california_time():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.minute > 0 or now.second > 0:
        now += timedelta(hours=1)
    return now.strftime("%H00"), now.strftime("%Y-%m-%d")

def calculate_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --- NAVIGATION TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📁 Vault", "📍 Install", "♻️ Pick-Up", "📊 Excel"])

# ==========================================
# TAB 1: VAULT
# ==========================================
with tab1:
    st.subheader("Load Map Files")
    if not st.session_state.optimized_route:
        uploaded_files = st.file_uploader("Select .est Maps", type=["est", "txt"], accept_multiple_files=True)
        if uploaded_files:
            file_configs = []
            for i, f in enumerate(uploaded_files):
                label = st.text_input(f"Sheet Name for {f.name}:", value=f"Day {i+1}", key=f"label_{i}")
                file_configs.append({"file": f, "label": label})
            if st.button("🚀 Merge & Optimize", use_container_width=True):
                all_raw_sites = []
                active_labels = []
                for config in file_configs:
                    lbl = config["label"]
                    active_labels.append(lbl)
                    raw_data = config["file"].read()
                    readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_data])
                    matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', readable_text)
                    for m in matches:
                        if m[0] == "3333": continue 
                        all_raw_sites.append({"id": m[0], "lat": float(m[2]), "lon": float(m[3]), "sheet": lbl})
                if all_raw_sites:
                    midpoint_df = pd.DataFrame(all_raw_sites).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
                    temp_route = []
                    current_pos = HOME_COORDS
                    remaining = midpoint_df.to_dict('records')
                    while remaining:
                        next_stop = min(remaining, key=lambda x: calculate_distance(current_pos, (x['lat'], x['lon'])))
                        temp_route.append(next_stop)
                        current_pos = (next_stop['lat'], next_stop['lon'])
                        remaining.remove(next_stop)
                    st.session_state.optimized_route = temp_route
                    st.session_state.active_files = active_labels
                    for site in temp_route:
                        st.session_state.site_data[site['id']] = {"Date":"","Time":"","Site":site['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":site['lat'],"LON":site['lon'],"Skipped":False,"Sheet":site['sheet']}
                    save_state(); st.rerun()
    else:
        st.success(f"Merged: {', '.join(st.session_state.active_files)}")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        if st.button("🗑️ Reset All"):
            st.session_state.active_files=[]; st.session_state.optimized_route=[]; st.session_state.site_data={}; st.session_state.current_index=0
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            st.rerun()

# ==========================================
# TAB 2: INSTALL (WITH VIEW TOGGLE)
# ==========================================
with tab2:
    if not st.session_state.optimized_route:
        st.info("Load maps in Vault first.")
    else:
        view_mode = st.radio("View Style:", ["🎯 Focus Mode (Speed)", "📜 List Mode (Overview)"], horizontal=True)
        
        # --- FOCUS MODE (SINGLE SITE AUTO-ADVANCE) ---
        if view_mode == "🎯 Focus Mode (Speed)":
            idx = st.session_state.current_index
            if idx < len(st.session_state.optimized_route):
                site = st.session_state.optimized_route[idx]; sid = site['id']; s_data = st.session_state.site_data[sid]
                st.subheader(f"Stop {idx+1}: Site {sid} ({s_data.get('Sheet', 'Day')})")
                st.link_button("🚗 GPS", f"https://www.google.com/maps/dir/?api=1&destination={site['lat']},{site['lon']}", use_container_width=True)
                with st.form(key=f"focus_ins_{sid}"):
                    c1, c2 = st.columns(2)
                    with c1: direction = st.selectbox("Dir", ["n","e","s","w"], index=["n","e","s","w"].index(s_data["Directions"]))
                    with c2: lanes = st.number_input("Lanes", min_value=1, value=int(s_data["Lanes"]))
                    serial = st.text_input("Serial", value=s_data["Serial"]); notes = st.text_input("Notes", value=s_data["Notes"])
                    btn1, btn2 = st.columns(2)
                    if btn1.form_submit_button("COMPLETE ➡️"):
                        t, d = get_california_time()
                        st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e","Serial":serial,"Lanes":lanes,"Notes":notes,"Installed":"x","Skipped":False})
                        st.session_state.current_index += 1; save_state(); st.rerun()
                    if btn2.form_submit_button("🚨 UNABLE"):
                        t, d = get_california_time()
                        st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e","Serial":serial,"Lanes":lanes,"Notes":f"UNABLE: {notes.upper()}","Installed":"","Skipped":True})
                        st.session_state.current_index += 1; save_state(); st.rerun()
                if idx > 0:
                    if st.button("⬅️ Previous Site"): st.session_state.current_index -= 1; save_state(); st.rerun()
            else: st.success("🏁 All installations handled.")

        # --- LIST MODE (ALL SITES WITH CLICKING) ---
        else:
            st.subheader("Installation Overview")
            for i, site in enumerate(st.session_state.optimized_route):
                sid = site['id']; s_data = st.session_state.site_data[sid]; is_done = s_data["Installed"] == "x" or s_data.get("Skipped", False)
                icon = "✅" if s_data["Installed"] == "x" else ("🚫" if s_data.get("Skipped", False) else "📝")
                
                with st.expander(f"{icon} Stop {i+1}: Site {sid}"):
                    if not is_done:
                        st.link_button("🚗 GPS", f"https://www.google.com/maps/dir/?api=1&destination={site['lat']},{site['lon']}")
                        with st.form(key=f"list_ins_{sid}"):
                            c1, c2 = st.columns(2)
                            with c1: direction = st.selectbox("Dir", ["n","e","s","w"], index=["n","e","s","w"].index(s_data["Directions"]))
                            with c2: lanes = st.number_input("Lanes", min_value=1, value=int(s_data["Lanes"]))
                            serial = st.text_input("Serial", value=s_data["Serial"]); notes = st.text_input("Notes", value=s_data["Notes"])
                            lb1, lb2 = st.columns(2)
                            if lb1.form_submit_button("COMPLETE"):
                                t, d = get_california_time()
                                st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e","Serial":serial,"Lanes":lanes,"Notes":notes,"Installed":"x","Skipped":False})
                                save_state(); st.rerun()
                            if lb2.form_submit_button("UNABLE"):
                                t, d = get_california_time()
                                st.session_state.site_data[sid].update({"Date":d,"Time":t,"Directions":"n" if direction in ["n","s"] else "e","Serial":serial,"Lanes":lanes,"Notes":f"UNABLE: {notes.upper()}","Installed":"","Skipped":True})
                                save_state(); st.rerun()
                    else:
                        st.write(f"Logged as: {'Installed' if s_data['Installed'] == 'x' else 'Unable'}")
                        if st.button("✏️ Edit Site", key=f"edit_list_{sid}"):
                            st.session_state.site_data[sid].update({"Installed":"","Skipped":False})
                            save_state(); st.rerun()

# ==========================================
# TAB 3: PICK-UP
# ==========================================
with tab3:
    installed = [d for sid, d in st.session_state.site_data.items() if d["Installed"] == "x"]
    if not installed: st.info("No sites installed yet.")
    else:
        for s in installed:
            sid = s["Site"]; is_picked = s["Picked up"] == "x"
            if not is_picked:
                with st.expander(f"📦 {s.get('Sheet','Day')} - Site {sid}"):
                    st.link_button("🚗 GPS", f"https://www.google.com/maps/dir/?api=1&destination={s['LAT']},{s['LON']}")
                    with st.form(key=f"pu_{sid}"):
                        p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                        if st.form_submit_button("Mark Picked Up"):
                            st.session_state.site_data[sid]["Picked up"]="x"; st.session_state.site_data[sid]["Notes"]=p_notes.strip(); save_state(); st.rerun()
            else: st.write(f"✅ Site {sid} Secured")

# ==========================================
# TAB 4: EXCEL
# ==========================================
with tab4:
    all_data = [d for sid, d in st.session_state.site_data.items() if d["Installed"] == "x" or d.get("Skipped", False)]
    if all_data:
        full_df = pd.DataFrame(all_data); cols = ["Date", "Time", "Site", "Counter", "Serial", "Directions", "Lanes", "Notes", "Installed", "Picked up"]
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name in st.session_state.active_files:
                sheet_df = full_df[full_df["Sheet"] == sheet_name]
                if not sheet_df.empty:
                    final_df = sheet_df[cols]; final_df.to_excel(writer, index=False, sheet_name=sheet_name)
                    st.write(f"**Sheet: {sheet_name}**"); st.dataframe(final_df, use_container_width=True)
        st.download_button("📊 Download Excel Workbook", output.getvalue(), f"Traffic_Work_{datetime.now().strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
