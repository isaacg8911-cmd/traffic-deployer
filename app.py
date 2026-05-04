import streamlit as st
import re
import pandas as pd

st.set_page_config(page_title="Traffic Deployer", layout="centered")
st.title("🚦 Traffic Counter Navigator")

if "installed_sites" not in st.session_state:
    st.session_state.installed_sites = {}

uploaded_file = st.file_uploader("Upload Today's .est Map", type="est")

if uploaded_file:
    # Read as raw bytes first since it's an OLE binary file
    raw_bytes = uploaded_file.read()
    
    # Convert to string while ignoring binary errors
    content = raw_bytes.decode("latin-1", errors="ignore")
    
    # This pattern is specifically tuned for the Streets & Trips data dump format
    # It looks for: [4-digit ID] [Address/City] [5-digit Zip] [Lat] [Lon]
    pattern = r'(\d{4})\s+([\w\s]+?)\s+\d{5}\s+(-?\d{2,3}\.\d+)\s+(-?\d{2,3}\.\d+)'
    matches = re.findall(pattern, content)
    
    if matches:
        data = []
        for m in matches:
            sid = m[0]
            # Coordinates in Streets & Trips are sometimes flipped or duplicated
            # We ensure we capture them correctly as floats
            data.append({
                "Site ID": sid,
                "Location": m[1].strip(),
                "Lat": float(m[2]),
                "Lon": float(m[3]),
                "Maps": f"https://www.google.com/maps/dir/?api=1&destination={m[2]},{m[3]}"
            })
            
        # Clean up duplicates (common in .est binary exports)
        df = pd.DataFrame(data).drop_duplicates(subset=["Site ID", "Lat"])
        
        # Dashboard
        total = len(df)
        completed = sum(st.session_state.installed_sites.get(sid, False) for sid in df["Site ID"])
        st.metric("Work Progress", f"{completed} / {total} Sites")
        st.progress(completed / total if total > 0 else 0)

        st.subheader("Installation Route")
        for i, row in df.iterrows():
            sid = row['Site ID']
            needs_photo = i < 5 #
            
            if sid not in st.session_state.installed_sites:
                st.session_state.installed_sites[sid] = False
            
            icon = "✅" if st.session_state.installed_sites[sid] else ("📸" if needs_photo else "📍")
            
            with st.expander(f"{icon} Site {sid} - {row['Location']}"):
                if needs_photo and not st.session_state.installed_sites[sid]:
                    st.warning("📸 PHOTO REQUIRED: This is one of your first 5 installs.")
                
                st.write(f"**GPS:** {row['Lat']}, {row['Lon']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    # Direct Directions Link
                    st.link_button("🚗 Start Drive", row['Maps'])
                with col2:
                    if st.button("Complete", key=f"btn_{sid}"):
                        st.session_state.installed_sites[sid] = True
                        st.rerun()
    else:
        st.error("Still no data detected.")
        st.info("The file is encrypted or uses a different binary structure. Try opening the .est file in Notepad on your PC and paste a small piece of the actual 'readable' text here.")
