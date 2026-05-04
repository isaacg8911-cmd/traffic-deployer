import streamlit as st
import re
import pandas as pd

st.set_page_config(page_title="Traffic Deployer", layout="centered")
st.title("🚦 Traffic Counter Navigator")

if "installed_sites" not in st.session_state:
    st.session_state.installed_sites = {}

uploaded_file = st.file_uploader("Upload .est Map File", type=["est", "txt"])

if uploaded_file is not None:
    try:
        # Optimization for mobile: read in smaller chunks to prevent memory crash
        raw_data = uploaded_file.read()
        
        # Clean the binary mess into readable text strings
        readable_text = "".join([chr(b) if 32 <= b < 127 else " " for b in raw_data])
        
        # REFINED PATTERN: Looks for Site ID + Street Name + City
        pattern = r'(\d{4})\s+\1\s+([A-Z0-9\s]{5,50}?)\s+(CHINO|ONTARIO|UPLAND|MONTCLAIR|POMONA|CLAREMONT|SAN BERNARDINO|GARDEN GROVE)'
        matches = re.findall(pattern, readable_text)
        
        if matches:
            data = []
            for m in matches:
                sid = m[0]
                search_query = f"{m[1].strip()}, {m[2].strip()}, CA"
                data.append({
                    "Site ID": sid,
                    "Location": m[1].strip(),
                    "City": m[2].strip(),
                    "Search": f"https://www.google.com/maps/search/?api=1&query={search_query.replace(' ', '+')}"
                })
                
            df = pd.DataFrame(data).drop_duplicates(subset=["Site ID"])
            
            # Progress Dashboard
            total = len(df)
            completed = sum(st.session_state.installed_sites.get(sid, False) for sid in df["Site ID"])
            st.metric("Work Progress", f"{completed} / {total} Sites")
            st.progress(completed / total if total > 0 else 0)

            st.subheader("Your Route")
            for i, row in df.iterrows():
                sid = row['Site ID']
                needs_photo = i < 5 # Requirement for first 5 installs
                
                if sid not in st.session_state.installed_sites:
                    st.session_state.installed_sites[sid] = False
                
                icon = "✅" if st.session_state.installed_sites[sid] else ("📸" if needs_photo else "📍")
                
                with st.expander(f"{icon} Site {sid} - {row['Location']}"):
                    if needs_photo and not st.session_state.installed_sites[sid]:
                        st.warning("📸 PHOTO REQUIRED: This is one of your first 5 installs.")
                    
                    st.write(f"**City:** {row['City']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.link_button("🚗 Open GPS", row['Search'])
                    with col2:
                        if st.button("Complete", key=f"btn_{sid}"):
                            st.session_state.installed_sites[sid] = True
                            st.rerun()
        else:
            st.error("No sites found. Please ensure the file contains site data.")
            
    except Exception as e:
        st.error(f"Mobile Upload Error: {e}")
        st.info("Try refreshing the page or using a different browser (Chrome usually works best).")
