import streamlit as st
import pandas as pd
import json
import re
import os
import time
from streamlit_folium import st_folium
import folium

# --- CORE CONFIG ---
st.set_page_config(page_title="Live Wire V51.40 Precision", layout="centered")

HOME_COORDS = (33.7715, -117.9431) 
BACKUP_FILE = "live_wire_backup.json"

# --- THEME ---
st.markdown("""
    <style>
    .stApp { background-color: #0A0A0A; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700 !important; font-family: 'Arial Black'; }
    div.stButton > button { 
        background-color: #1E1E1E; color: #FFD700; border: 2px solid #FFD700; 
        font-weight: bold; border-radius: 8px; height: 3.5em; width: 100%;
    }
    .stInfo { background-color: #111 !important; border: 1px solid #FFD700 !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

if "init" not in st.session_state:
    st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], {}, 0
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items(): st.session_state[k] = v
        except: pass
    st.session_state.init = True

def auto_save():
    payload = {"optimized_route": st.session_state.optimized_route, "site_data": st.session_state.site_data, "current_index": st.session_state.current_index}
    with open(BACKUP_FILE, "w") as f: json.dump(payload, f)

# --- UI ---
if not st.session_state.optimized_route:
    st.title("🚦 Live Wire: Sync")
    ex = st.file_uploader("1️⃣ Excel List", accept_multiple_files=True)
    maps = st.file_uploader("2️⃣ Map Files (.EST)", accept_multiple_files=True)
    if ex and maps and st.button("🚀 SYNC & DRIVE"):
        # Processing logic here... (Same as V51.39)
        pass 
else:
    st.title("📁 Active Manifest")
    
    # 1. THE INTERACTIVE TUNING MAP (Click-to-Edit)
    st.subheader("Interactive Route Map")
    m = folium.Map(location=HOME_COORDS, zoom_start=11)
    
    # Render dots 1/4 smaller (radius=4-6)
    for s in st.session_state.optimized_route:
        sd = st.session_state.site_data[s['uid']]
        color = 'green' if sd['Installed'] else 'orange'
        folium.CircleMarker(
            location=[sd['lat'], sd['lon']],
            radius=5,
            color=color,
            fill=True,
            popup=f"Site {sd['id']}"
        ).add_to(m)

    map_data = st_folium(m, height=350, width=700, key="interactive_map")

    # 2. THE EDIT DECK
    with st.expander("🛠️ EDIT SITE POSITION"):
        edit_uid = st.selectbox("Select Site to Move:", [s['uid'] for s in st.session_state.optimized_route])
        if map_data and map_data.get("last_clicked"):
            new_lat, new_lon = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
            st.write(f"Target: {new_lat:.6f}, {new_lon:.6f}")
            if st.button("📍 UPDATE POSITION FOR THIS SITE"):
                st.session_state.site_data[edit_uid]['lat'] = new_lat
                st.session_state.site_data[edit_uid]['lon'] = new_lon
                # Update in list for navigation logic
                for s in st.session_state.optimized_route:
                    if s['uid'] == edit_uid:
                        s['lat'], s['lon'] = new_lat, new_lon
                auto_save(); st.rerun()

    st.divider()

    # 3. DRIVING & BATCH NAV
    idx = st.session_state.current_index
    if idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        sd = st.session_state.site_data[active['uid']]
        
        st.info(f"**STOP {idx+1}: SITE {sd['id']}**\n\n{sd['street']}")
        st.link_button("🚗 NAVIGATE TO THIS STOP", f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}", use_container_width=True)
        
        # BATCH 9 LOGIC
        batch = []
        for i in range(idx, min(idx + 9, len(st.session_state.optimized_route))):
            b_site = st.session_state.optimized_route[i]
            b_sd = st.session_state.site_data[b_site['uid']]
            if not b_sd['Installed']:
                batch.append(f"{b_sd['lat']},{b_sd['lon']}")
        
        if len(batch) > 1:
            st.link_button(f"🗺️ BATCH NAV NEXT {len(batch)} SITES", f"https://www.google.com/maps/dir/{'/'.join(batch)}", use_container_width=True)

        if st.button("✅ MARK INSTALLED & NEXT", use_container_width=True):
            st.session_state.site_data[active['uid']]['Installed'] = True
            st.session_state.current_index += 1; auto_save(); st.rerun()
    else:
        st.success("🏁 All sites installed.")

    if st.button("🗑️ RESET"):
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
        st.session_state.optimized_route = []; st.rerun()
