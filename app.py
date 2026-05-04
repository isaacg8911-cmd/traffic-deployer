import streamlit as st
import re
import pandas as pd

st.set_page_config(page_title="Traffic Deployer", layout="centered")
st.title("🚦 Traffic Counter Navigator")

if "installed_sites" not in st.session_state:
    st.session_state.installed_sites = {}

uploaded_file = st.file_uploader("Upload Today's .est Map", type="est")

if uploaded_file:
    content = uploaded_file.getvalue().decode("latin-1")
    
    # NEW FLEXIBLE PATTERN: 
    # Looks for: [4 digits] [Street/City Info] [5-digit Zip] [Lat] [Lon]
    # This ignores the specific city names to ensure it catches everything.
    pattern = r'(\d{4})\s+(.*?)\s+(\d{5})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)'
    matches = re.findall(pattern, content)
    
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
        
        # Progress Metric 
        total = len(df)
        completed = sum(st.session_state.installed_sites.get(sid, False) for sid in df["Site ID"])
        st.metric("Work Progress", f"{completed} / {total} Sites")
        st.progress(completed / total if total > 0 else 0)

        st.subheader("Your Route")
        for i, row in df.iterrows():
            sid = row['Site ID']
            needs_photo = i < 5 # 
            
            if sid not in st.session_state.installed_sites:
                st.session_state.installed_sites[sid] = False
            
            icon = "✅" if st.session_state.installed_sites[sid] else ("📸" if needs_photo else "📍")
            
            with st.expander(f"{icon} Site {sid} - {row['Location']}"):
                if needs_photo and not st.session_state.installed_sites[sid]:
                    st.warning("⚠️ PHOTO REQUIRED: One of your first 5 installs.") [cite: 1]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.link_button("🚗 Start Drive", row['Maps'])
                with col2:
                    if st.button("Complete", key=f"btn_{sid}"):
                        st.session_state.installed_sites[sid] = True
                        st.rerun()
    else:
        # If it still fails, show the raw text so we can see what the file actually looks like
        st.error("No valid site data detected.")
        with st.expander("Debug: See Raw File Content"):
            st.text(content[:1000])
