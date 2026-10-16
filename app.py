
import streamlit as st
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

st.set_page_config(
    page_title="Kolkata Emergency GIS Dashboard",
    layout="wide"
)

st.title("Kolkata Emergency Response Dashboard")
st.write("Interactive GIS Disaster Management Simulation")
st.warning("Educational demonstration only. Not for real emergency navigation.")

facilities = [
    {"name": "Demo Hospital A", "type": "Hospital",
     "lat": 22.585, "lon": 88.410},
    {"name": "Demo Shelter B", "type": "Shelter",
     "lat": 22.575, "lon": 88.430},
    {"name": "Demo Fire Station C", "type": "Fire Station",
     "lat": 22.565, "lon": 88.400}
]

def distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

st.sidebar.header("Emergency Controls")

disaster = st.sidebar.selectbox(
    "Select Disaster",
    ["Flood", "Fire", "Medical Emergency"]
)

facility_type = st.sidebar.selectbox(
    "Select Emergency Facility",
    ["Hospital", "Shelter", "Fire Station"]
)

if "incident" not in st.session_state:
    st.session_state.incident = [22.580, 88.420]

lat, lon = st.session_state.incident

matching = [
    f for f in facilities
    if f["type"] == facility_type
]

nearest = min(
    matching,
    key=lambda f: distance_km(
        lat, lon, f["lat"], f["lon"]
    )
)

distance = distance_km(
    lat, lon, nearest["lat"], nearest["lon"]
)

col1, col2, col3 = st.columns(3)

col1.metric("Disaster", disaster)
col2.metric("Nearest Demo Facility", nearest["name"])
col3.metric("Straight-Line Distance", f"{distance:.2f} km")

st.subheader("Interactive Emergency Map")
st.write("Click anywhere on the map to select an incident location.")

m = folium.Map(
    location=[lat, lon],
    zoom_start=13
)

folium.Marker(
    [lat, lon],
    tooltip="Selected Incident",
    icon=folium.Icon(color="red", icon="warning-sign")
).add_to(m)

for f in facilities:
    folium.Marker(
        [f["lat"], f["lon"]],
        tooltip=f["name"],
        popup=f["name"],
        icon=folium.Icon(color="blue")
    ).add_to(m)

folium.PolyLine(
    [
        [lat, lon],
        [nearest["lat"], nearest["lon"]]
    ],
    color="green",
    weight=5,
    tooltip="Straight-line connection (not a road route)"
).add_to(m)

result = st_folium(
    m,
    height=500,
    width=None,
    key="emergency_map"
)

if result and result.get("last_clicked"):
    clicked = result["last_clicked"]
    new_location = [clicked["lat"], clicked["lng"]]

    if new_location != st.session_state.incident:
        st.session_state.incident = new_location
        st.rerun()

st.subheader("Emergency Facility Information")

st.write("Selected facility:", nearest["name"])
st.write("Facility type:", nearest["type"])
st.write("Straight-line distance:", round(distance, 2), "km")

st.info(
    "This first version uses fictional facilities and "
    "straight-line distances. Actual road routing and "
    "verified facilities will be added in the next stage."
)
