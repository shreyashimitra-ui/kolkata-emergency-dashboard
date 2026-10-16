import math
import requests
import streamlit as st
import folium
from folium.plugins import AntPath
from streamlit_folium import st_folium

st.set_page_config(page_title='Kolkata | Emergency Command Centre', page_icon='🚨', layout='wide', initial_sidebar_state='expanded')

st.markdown('''<style>
.stApp {background: #081321; color: #e8f2ff;}
[data-testid="stSidebar"] {background: #101f32; border-right: 1px solid #263c58;}
.block-container {padding-top: 1.2rem; max-width: 1500px;}
h1,h2,h3 {color: #f1f7ff !important;}
.command-header {padding: 20px 24px; background: linear-gradient(110deg,#122943,#0a1829); border: 1px solid #2a5275; border-radius: 14px; margin-bottom: 16px;}
.command-title {font-size: clamp(1.4rem,3vw,2.1rem); font-weight: 800; letter-spacing: 1px; color: #f5fbff;}
.command-sub {color: #9ebad1; font-size: .9rem;}
.status {border-left: 5px solid var(--accent); background: #162a3e; padding: 13px 16px; border-radius: 8px; margin: 12px 0; animation: pulse 2.8s ease-in-out infinite;}
@keyframes pulse {0%,100%{box-shadow:0 0 0 rgba(255,255,255,0)}50%{box-shadow:0 0 14px color-mix(in srgb,var(--accent) 22%, transparent)}}
[data-testid="stMetric"] {background: #13263b; border: 1px solid #284763; border-radius: 12px; padding: 14px;}
[data-testid="stMetricLabel"] {color: #a8c1d5;}
[data-testid="stMetricValue"] {color: #f3faff;}
</style>''', unsafe_allow_html=True)

SCENARIOS = {
    'Flood': {'icon': '🌊', 'color': '#39b9ff', 'facility': 'Shelter', 'message': 'FLOOD SIMULATION — Check accessibility; routes are NOT flood-validated.'},
    'Fire': {'icon': '🔥', 'color': '#ff9854', 'facility': 'Fire Station', 'message': 'FIRE SIMULATION — Locate reachable fire response facilities.'},
    'Medical Emergency': {'icon': '🚑', 'color': '#55dc9a', 'facility': 'Hospital', 'message': 'MEDICAL SIMULATION — Find a reachable demonstration hospital.'},
}
# Fictional demonstration facilities; coordinates are not verified operational locations.
FACILITIES = [
    {'name': 'Demo Hospital A', 'type': 'Hospital', 'lat': 22.585, 'lon': 88.410},
    {'name': 'Demo Hospital B', 'type': 'Hospital', 'lat': 22.570, 'lon': 88.440},
    {'name': 'Demo Shelter A', 'type': 'Shelter', 'lat': 22.575, 'lon': 88.430},
    {'name': 'Demo Shelter B', 'type': 'Shelter', 'lat': 22.600, 'lon': 88.420},
    {'name': 'Demo Fire Station A', 'type': 'Fire Station', 'lat': 22.565, 'lon': 88.400},
    {'name': 'Demo Fire Station B', 'type': 'Fire Station', 'lat': 22.590, 'lon': 88.450},
]

st.markdown('''<div class="command-header"><div class="command-title">🚨 KOLKATA | EMERGENCY COMMAND CENTRE</div><div class="command-sub">Interactive geospatial decision-support demonstration · Educational simulation only</div></div>''', unsafe_allow_html=True)

with st.sidebar:
    st.header('⚙️ Command controls')
    scenario = st.selectbox('Incident scenario', list(SCENARIOS))
    facility_type = st.selectbox('Response facility', ['Shelter', 'Hospital', 'Fire Station'], index=['Shelter','Hospital','Fire Station'].index(SCENARIOS[scenario]['facility']))
    st.caption('Select a scenario, then click the map to move the incident marker.')
    if st.button('↩ Reset incident to Salt Lake', use_container_width=True):
        st.session_state.incident = [22.580, 88.420]
        st.rerun()
    st.divider()
    st.info('All facility names are fictional. This is NOT a live emergency service.')

if 'incident' not in st.session_state:
    st.session_state.incident = [22.580, 88.420]
lat, lon = st.session_state.incident
cfg = SCENARIOS[scenario]
st.markdown(f'''<div class="status" style="--accent:{cfg['color']}"><strong>{cfg['icon']} {cfg['message']}</strong><div style="color:#b8cbdf;font-size:.85rem">Click on the map to update the incident location and recalculate the route.</div></div>''', unsafe_allow_html=True)

try:
    api_key = st.secrets['ORS_API_KEY']
except (KeyError, FileNotFoundError):
    st.error('Routing key not found. Add ORS_API_KEY to Streamlit Community Cloud → App settings → Secrets.')
    st.stop()

@st.cache_data(ttl=1800, show_spinner=False)
def get_route(key, origin_lat, origin_lon, dest_lat, dest_lon):
    url = 'https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson'
    payload = {'coordinates': [[origin_lon, origin_lat], [dest_lon, dest_lat]]}
    response = requests.post(url, json=payload, headers={'Authorization': key, 'Content-Type': 'application/json'}, timeout=25)
    response.raise_for_status()
    feature = response.json()['features'][0]
    summary = feature['properties']['summary']
    path = [[p[1], p[0]] for p in feature['geometry']['coordinates']]
    return float(summary['distance']), float(summary['duration']), path

results = []
errors = []
with st.spinner('🛰️ Analysing road-network accessibility...'):
    for facility in FACILITIES:
        if facility['type'] != facility_type:
            continue
        try:
            distance, duration, path = get_route(api_key, round(lat, 5), round(lon, 5), facility['lat'], facility['lon'])
            results.append({'facility': facility, 'distance': distance, 'duration': duration, 'path': path})
        except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
            errors.append(str(exc))
results.sort(key=lambda x: x['distance'])
nearest = results[0] if results else None

c1, c2, c3, c4 = st.columns(4)
c1.metric('Incident', f"{cfg['icon']} {scenario}")
c2.metric('Nearest demo facility', nearest['facility']['name'] if nearest else 'Unavailable')
c3.metric('Road distance', f"{nearest['distance']/1000:.2f} km" if nearest else 'N/A')
c4.metric('Estimated driving time', f"{nearest['duration']/60:.1f} min" if nearest else 'N/A')

if nearest:
    st.success(f"✅ Route calculated to {nearest['facility']['name']}. Modelled road distance: {nearest['distance']/1000:.2f} km.")
else:
    st.error('⚠️ No road route returned. Check the API key, usage quota, connectivity, or incident location.')
    if errors:
        with st.expander('Technical error details'):
            st.code(errors[0][:700])

left, right = st.columns([3, 1], gap='large')
with left:
    st.subheader('🗺️ Interactive response map')
    m = folium.Map(location=[lat, lon], zoom_start=13, tiles='CartoDB dark_matter', control_scale=True)
    folium.Marker([lat, lon], tooltip=f'{cfg["icon"]} Incident: {scenario}', popup='Simulated incident', icon=folium.DivIcon(html=f'<div style="font-size:32px;filter:drop-shadow(0 0 6px {cfg["color"]})">{cfg["icon"]}</div>')).add_to(m)
    icons = {'Hospital': '🏥', 'Shelter': '🏠', 'Fire Station': '🚒'}
    for f in FACILITIES:
        folium.Marker([f['lat'], f['lon']], tooltip=f['name'], popup=f"{f['name']} — fictional demonstration facility", icon=folium.DivIcon(html=f'<div style="font-size:24px">{icons[f["type"]]}</div>')).add_to(m)
    if nearest:
        AntPath(nearest['path'], color=cfg['color'], pulse_color='#ffffff', weight=6, delay=900, dash_array=[12, 20], tooltip='Modelled driving route').add_to(m)
    clicked = st_folium(m, height=530, width=None, key='command_map', returned_objects=['last_clicked'])
    if clicked and clicked.get('last_clicked'):
        p = clicked['last_clicked']
        new_point = [round(p['lat'], 5), round(p['lng'], 5)]
        if new_point != st.session_state.incident:
            st.session_state.incident = new_point
            st.rerun()
with right:
    st.subheader('📊 Facility comparison')
    if results:
        import pandas as pd
        chart_data = pd.DataFrame([{'Facility': r['facility']['name'], 'Road distance (km)': round(r['distance']/1000, 2)} for r in results]).set_index('Facility')
        st.bar_chart(chart_data)
        st.dataframe(pd.DataFrame([{'Facility': r['facility']['name'], 'Distance (km)': round(r['distance']/1000, 2), 'Time (min)': round(r['duration']/60, 1)} for r in results]), hide_index=True, use_container_width=True)
    else:
        st.caption('No reachable demonstration facilities to compare.')
    st.caption('Driving times are model estimates, not live traffic or emergency response times.')

st.divider()
st.caption('⚠️ TRAINING ONLY · Fictional facilities · No live incident feeds · No flood depth, fire spread, road closure, traffic or shelter-capacity validation · Not for emergency decisions.')
