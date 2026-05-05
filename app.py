import streamlit as st
import re
import pandas as pd
import math
import json
import io
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- ROCK-SOLID CONFIG ---
st.set_page_config(page_title="Live Wire V10", layout="centered")

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

def process_raw_text(text_blocks, labels):
    all_raw = []
    for idx, text in enumerate(text_blocks):
        if not text.strip(): continue
        matches = re.findall(r'(\d{4})\s+.*?\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', text)
        for m in matches:
            if m[0] == "3333": continue
            all_raw.append({"id": str(m[0]), "lat": float(m[2]), "lon": float(m[3]), "sheet": labels[idx]})
    
    if all_raw:
        df = pd.DataFrame(all_raw).groupby("id").agg({'lat':'mean','lon':'mean','sheet':'first'}).reset_index()
        route, curr, rem = [], HOME_COORDS, df.to_dict('records')
        while rem:
            nxt = min(rem, key=lambda x: math.hypot(curr[0]-x['lat'], curr[1]-x['lon']))
            route.append(nxt); curr = (nxt['lat'], nxt['lon']); rem.remove(nxt)
        
        st.session_state.optimized_route = route
        st.session_state.active_files = [l for l in labels if l]
        st.session_state.site_data = {s['id']: {"Date":"","Time":"","Site":s['id'],"Counter":"c1b","Serial":"","Directions":"n","Lanes":1,"Notes":"","Installed":"","Picked up":"","LAT":s['lat'],"LON":s['lon'],"Skipped":False,"Sheet":s['sheet']} for s in route}
        auto_save()
        return True
    return False

# ==========================================
# STAGE 1: TERMINAL INPUT
# ==========================================
if not st.session_state.get("optimized_route"):
    st.title("🚦 TERMINAL GATEWAY")
    st.warning("Uploader bypassed for Pixel 9 stability. Open your .est files, copy all text, and paste below.")
    
    col1, col2 = st.columns(2)
    with col1: lbl_1 = st.text_input("Label 1:", value="Day 1")
    with col2: lbl_2 = st.text_input("Label 2:", value="Day 2")
    
    text_1 = st.text_area(f"PASTE {lbl_1} DATA HERE:", height=150)
    text_2 = st.text_area(f"PASTE {lbl_2} DATA HERE (Optional):", height=150)
    
    if st.button("🚀 PROCESS ROUTE DATA", use_container_width=True):
        if text_1.strip() or text_2.strip():
            with st.spinner("CRUNCHING COORDINATES..."):
                if process_raw_text([text_1, text_2], [lbl_1, lbl_2]):
                    st.success("SYNC COMPLETE!")
                    st.rerun()
                else: st.error("No valid site data found in pasted text.")
        else:
            st.error("Text boxes are empty.")

# ==========================================
# STAGE 2: MAIN DASHBOARD
# ==========================================
else:
    st.title("🚦 Live Wire Field Ops")
    tab1, tab2, tab3, tab4 = st.tabs(["📁 ROUTE", "📍 INSTALL", "♻️ PICK-UP", "📊 EXCEL"])

    with tab1:
        st.success(f"ACTIVE ROUTE: {len(st.session_state.optimized_route)} STOPS")
        st.map(pd.DataFrame(st.session_state.optimized_route), zoom=9)
        
        st.divider()
        if st.button("🗑️ PURGE & START FRESH", use_container_width=True):
            if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
            for key in ["active_files", "optimized_route", "site_data", "current_index"]:
                st.session_state[key] = [] if isinstance(st.session_state[key], list) else ({} if isinstance(st.session_state[key], dict) else 0)
            st.rerun()

    with tab2:
        cur_idx = st.session_state.current_index
        if cur_idx < len(st.session_state.optimized_route):
            s = st.session_state.optimized_route[cur_idx]; sid = s['id']; sd = st.session_state.site_data[sid]
            
            st.subheader(f"#{cur_idx+1}: SITE {sid} [{sd.get('Sheet')}]")
            st.progress(cur_idx / len(st.session_state.optimized_route))
            st.link_button("🚗 START NAVIGATION", f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}", use_container_width=True)
            
            with st.form(key=f"f_v10_{sid}"):
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
                    nxt = min(rem, key=lambda x: math.hypot(curr[0]-x['LAT'], curr[1]-x['LON']))
                    new_itin.append(nxt); curr = (nxt['LAT'], nxt['LON']); rem.remove(nxt)
                st.session_state.pickup_itinerary = new_itin; st.success("Pick-Up sequence optimized.")

            itinerary = st.session_state.get("pickup_itinerary", installed)
            for i, s in enumerate(itinerary):
                sid, is_picked = s["Site"], s["Picked up"] == "x"
                status = "✅" if is_picked else "📦"
                with st.expander(f"{status} #{i+1} - Site {sid}"):
                    if not is_picked:
                        st.link_button("🚗 Navigate to Spot", f"https://www.google.com/maps/dir/?api=1&destination={s['LAT']},{s['LON']}", use_container_width=True)
                        with st.form(key=f"pu_v10_{sid}"):
                            p_notes = st.text_input("Pick-Up Notes", value=s["Notes"])
                            if st.form_submit_button("MARK SECURED"):
                                st.session_state.site_data[sid]["Picked up"] = "x"; st.session_state.site_data[sid]["Notes"] = p_notes.strip(); auto_save(); st.rerun()
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
