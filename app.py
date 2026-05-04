import streamlit as st
import re
import pandas as pd

# Mobile-friendly setup for your truck
st.set_page_config(page_title="Traffic Deployer", layout="centered")

st.title("🚦 Traffic Counter Navigator")

# Keeps track of which sites you've finished during your shift
if "installed_sites" not in st.session_state:
    st.session_state.installed_sites = {}

uploaded_file = st.file_uploader("Upload Today's .est Map", type="est")

if uploaded_file:
    content = uploaded_file.getvalue().decode("latin-1")
    
    # Regex to find Site ID, Street, City, and Coordinates from your .est file
    pattern = r'(\d{4})\s+([\w\s]+?)\s+(Upland|Ontario|Montclair|Pomona|Claremont|San Bernardino)\s+([\w\s]+)\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)'
    matches = re.findall(pattern, content)
    
    if matches:
        data = []
        for m in matches:
            data.append({
                "Site ID": m[0],
                "Location": f"{m[1]}, {m[2]}",
                "Lat": float(m[5]),
                "Lon": float(m[6]),
                "Maps": f"https://www.google.com/maps/dir/?api=1&destination={m[5]},{m[6]}"
            })
            
        df = pd.DataFrame(data).drop_duplicates(subset=["Site ID", "Lat"])
        
        # Progress Tracking for the day
        total = len(df)
        completed = sum(st.session_state.installed_sites.get(sid, False) for sid in df["Site ID"])
        st.metric("Work Progress", f"{completed} / {total} Sites")
        st.progress(completed / total if total > 0 else 0)

        # Installation List
        st.subheader("Your Route")
        for i, row in df.iterrows():
            sid = row['Site ID']
            
            # Identify the first 5 installations for required photos
            needs_photo = i < 5
            if sid not in st.session_state.installed_sites:
                st.session_state.installed_sites[sid] = False
            
            # Status styling
            icon = "✅" if st.session_state.installed_sites[sid] else ("📸" if needs_photo else "📍")
            
            with st.expander(f"{icon} Site {sid} - {row['Location']}"):
                if needs_photo and not st.session_state.installed_sites[sid]:
                    st.warning("⚠️ PHOTO REQUIRED: One of your first 5 installs.")
                
                st.write(f"**GPS:** {row['Lat']}, {row['Lon']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.link_button("🚗 Start Drive", row['Maps'])
                with col2:
                    if st.button("Complete", key=f"btn_{sid}"):
                        st.session_state.installed_sites[sid] = True
                        st.rerun()
    else:
        st.error("No valid site data detected in this .est file.")
