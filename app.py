import streamlit as st
import pandas as pd
import json
import re
import os
import time
from streamlit_folium import st_folium
import folium

# --- CORE CONFIG ---
st.set_page_config(page_title="Live Wire V51.41 Command", layout="centered")

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
    .pending-card { border-left: 5px solid #FFD700; padding: 10px; background: #222; margin: 5px 0; }
    </style>
""", unsafe_allow_html=True)

if "init" not in st.session_state:
    st.session_state.optimized_route, st.session_state.site_data, st.session_state.current_index = [], {}, 0
    st.session_state.pending_changes = {} # Store {uid: (lat, lon)}
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
    st.title("🚦 Live Wire: Command Sync")
    # [Upload Logic Same as Previous Stable Versions]
    pass 
else:
    st.title("📁 Tactical Manifest")
    
    # 1. INTERACTIVE MAP
    st.subheader("Interactive Plotter")
    m = folium.Map(location=HOME_COORDS, zoom_start=11)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite').add_to(m)

    for s in st.session_state.optimized_route:
        sd = st.session_state.site_data[s['uid']]
        # Use pending coords if they exist
        lat, lon = st.session_state.pending_changes.get(s['uid'], (sd['lat'], sd['lon']))
        color = 'blue' if s['uid'] in st.session_state.pending_changes else ('green' if sd['Installed'] else 'orange')
        folium.CircleMarker(location=[lat, lon], radius=5, color=color, fill=True, popup=f"Site {sd['id']}").add_to(m)

    map_data = st_folium(m, height=400, width=700, key="command_map")

    # 2. THE EDIT & BATCH QUEUE
    col_edit, col_queue = st.columns([1, 1])

    with col_edit:
        st.write("### 🛠️ Edit Position")
        edit_uid = st.selectbox("Select Site:", [s['uid'] for s in st.session_state.optimized_route])
        if map_data and map_data.get("last_clicked"):
            c_lat, c_lon = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
            if st.button("➕ STAGE CHANGE"):
                st.session_state.pending_changes[edit_uid] = (c_lat, c_lon)
                st.rerun()

    with col_queue:
        st.write("### 📥 Pending Changes")
        if not st.session_state.pending_changes:
            st.write("No changes staged.")
        else:
            for uid, coords in st.session_state.pending_changes.items():
                sid = st.session_state.site_data[uid]['id']
                st.markdown(f"<div class='pending-card'>Site {sid}: {coords[0]:.4f}, {coords[1]:.4f}</div>", unsafe_allow_html=True)
            
            if st.button("🔄 APPLY ALL & REFRESH NAV"):
                for uid, (new_lat, new_lon) in st.session_state.pending_changes.items():
                    st.session_state.site_data[uid]['lat'] = new_lat
                    st.session_state.site_data[uid]['lon'] = new_lon
                    for s in st.session_state.optimized_route:
                        if s['uid'] == uid:
                            s['lat'], s['lon'] = new_lat, new_lon
                st.session_state.pending_changes = {}
                auto_save()
                st.success("Navigation Updated!")
                st.rerun()

    st.divider()

    # 3. DRIVING & BATCH NAV
    idx = st.session_state.current_index
    if idx < len(st.session_state.optimized_route):
        active = st.session_state.optimized_route[idx]
        sd = st.session_state.site_data[active['uid']]
        
        st.info(f"**STOP {idx+1}: SITE {sd['id']}**\n{sd['street']}")
        st.link_button("🚗 NAVIGATE TO THIS STOP", f"https://www.google.com/maps/search/?api=1&query={sd['lat']},{sd['lon']}", use_container_width=True)
        
        # Batch 9
        batch = [f"{st.session_state.site_data[s['uid']]['lat']},{st.session_state.site_data[s['uid']]['lon']}" 
                 for s in st.session_state.optimized_route[idx:idx+9] if not st.session_state.site_data[s['uid']]['Installed']]
        if len(batch) > 1:
            st.link_button(f"🗺️ BATCH NAV NEXT {len(batch)}", f"https://www.google.com/maps/dir/{'/'.join(batch)}", use_container_width=True)

        if st.button("✅ MARK INSTALLED & NEXT", use_container_width=True):
            st.session_state.site_data[active['uid']]['Installed'] = True
            st.session_state.current_index += 1; auto_save(); st.rerun()
