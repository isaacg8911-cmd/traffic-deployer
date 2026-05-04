import streamlit as st
import re
import pandas as pd

st.set_page_config(page_title="Traffic Deployer", layout="centered")
st.title("🚦 Traffic Counter Navigator")

if "installed_sites" not in st.session_state:
    st.session_state.installed_sites = {}

uploaded_file = st.file_uploader("Upload Today's .est Map", type="est")

if uploaded_file:
    # Read the binary data 
    raw_data = uploaded_file.read()
    
    # Extract only readable strings (3+ characters) from the binary container 
    readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_data])
    
    # Pattern tuned for Streets & Trips: [SiteID] [Address/City] [Zip] [Lat] [Lon] [cite: 10, 11]
    # We look for a 4-digit ID followed by a zip code and then two decimal numbers
    pattern = r'(\d{4})\s+(.*?)\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)'
    matches = re.findall(pattern, readable_text)
    
    if matches:
        data = []
        for m in matches:
            sid = m[0]
            data.append({
                "Site ID": sid,
                "Location": m[1].strip(),
                "Lat": float(m[3]),
                "Lon": float(m[4]),
                "Maps": f"https://www.google.com/maps/dir/?api=1&destination={m[3]},{m[4]}"
            })
            
        df = pd.DataFrame(data).drop_duplicates(subset=["Site ID", "Lat"])
        
        # Dashboard
        total = len(df)
        completed = sum(st.session_state.installed_sites.get(sid, False) for sid in df["Site ID"])
        st.metric("Work Progress", f"{completed} / {total} Sites")
        st.progress(completed / total if total > 0 else 0)

        st.subheader("Installation Route")
        for i, row in df.iterrows():
            sid = row['Site ID']
            needs_photo = i < 5 # Requirement: First 5 installs need photos
            
            if sid not in st.session_state.installed_sites:
                st.session_state.installed_sites[sid] = False
            
            icon = "✅" if st.session_state.installed_sites[sid] else ("📸" if needs_photo else "📍")
            
            with st.expander(f"{icon} Site {sid} - {row['Location']}"):
                if needs_photo and not st.session_state.installed_sites[sid]:
                    st.warning("📸 PHOTO REQUIRED: This is one of your first 5 installs.")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.link_button("🚗 Start Drive", row['Maps'])
                with col2:
                    if st.button("Mark Complete", key=f"btn_{sid}"):
                        st.session_state.installed_sites[sid] = True
                        st.rerun()
    else:
        st.error("No data found in binary stream.")
        st.info("The coordinates might be stored as raw doubles (not text).")
        # Fallback: Show a snippet of the 'cleaned' text to help us debug
        with st.expander("Debug: Cleaned Text Snippet"):
            st.text(readable_text[2000:5000])
