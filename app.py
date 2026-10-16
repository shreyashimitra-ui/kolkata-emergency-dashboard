
import streamlit as st
import folium
from streamlit_folium import st_folium
import requests

st.set_page_config(
    page_title="Kolkata Emergency Dashboard",
    layout="wide"
)

st.title("Kolkata Emergency Response GIS Dashboard")
st.warning(
    "Educational simulation only. "
    "Do not use for actual emergency navigation."
)

facilities = [
    {"name": "Demo Hospital A", "type": "Hospital",
     "lat": 22.585, "lon": 88.410},
    {"name": "Demo Hospital B", "type": "Hospital",
     "lat": 22.570, "lon": 88.440},
    {"name": "Demo Shelter A", "type": "Shelter",
     "lat": 22.575, "lon": 88.430},
    {"name": "Demo Shelter B", "type": "Shelter",
     "lat": 22.600, "lon": 88.420},
    {"name": "Demo Fire Station A", "type": "Fire Station",
     "lat": 22.565, "lon": 88.400},
    {"name": "Demo Fire Station B", "type": "Fire Station",
     "lat": 22.590, "lon": 88.450}
]

try:
    api_key = st.secrets["ORS_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("ORS_API_KEY is missing from Streamlit Secrets.")
    st.stop()

st.sidebar.header("Emergency controls")

disaster = st.sidebar.selectbox(
    "Incident type",
    ["Flood", "Fire", "Medical Emergency"]
)

facility_type = st.sidebar.selectbox(
    "Facility type",
    ["Hospital", "Shelter", "Fire Station"]
)

st.sidebar.caption(
    "Facilities are fictional demonstration points."
)

if "incident" not in st.session_state:
    st.session_state.incident = [22.580, 88.420]

lat, lon = st.session_state.incident


@st.cache_data(ttl=1800, show_spinner=False)
def get_route(key, origin_lat, origin_lon, dest_lat, dest_lon):
    url = (
        "https://api.heigit.org/openrouteservice/v2/"
        "directions/driving-car/geojson"
    )

    body = {
        "coordinates": [
            [origin_lon, origin_lat],
            [dest_lon, dest_lat]
        ]
    }

    response = requests.post(
        url,
        json=body,
        headers={
            "Authorization": key,
            "Content-Type": "application/json"
        },
        timeout=25
    )

    response.raise_for_status()
    data = response.json()

    feature = data["features"][0]
    summary = feature["properties"]["summary"]
    coordinates = feature["geometry"]["coordinates"]

    route = [[p[1], p[0]] for p in coordinates]

    return summary["distance"], summary["duration"], route


candidates = [
    f for f in facilities
    if f["type"] == facility_type
]

results = []

with st.spinner("Finding reachable facilities using roads..."):
    for f in candidates:
        try:
            distance, duration, route = get_route(
                api_key,
                round(lat, 5),
                round(lon, 5),
                f["lat"],
                f["lon"]
            )

            results.append(
                (distance, duration, route, f)
            )

        except (
            requests.RequestException,
            KeyError,
            IndexError,
            ValueError
        ):
            continue

nearest = (
    min(results, key=lambda item: item[0])
    if results else None
)

c1, c2, c3 = st.columns(3)

c1.metric("Incident", disaster)

c2.metric(
    "Nearest reachable demo facility",
    nearest[3]["name"] if nearest else "Unavailable"
)

c3.metric(
    "Road distance",
    f"{nearest[0] / 1000:.2f} km" if nearest else "N/A"
)

if nearest:
    st.write(
        f"Estimated driving time: "
        f"**{nearest[1] / 60:.1f} minutes** "
        "(routing model, not live traffic)."
    )
else:
    st.error(
        "No road route was returned. Check the API key, "
        "quota, connectivity, or incident location."
    )

m = folium.Map(
    location=[lat, lon],
    zoom_start=13
)

folium.Marker(
    [lat, lon],
    tooltip="Incident",
    icon=folium.Icon(color="red")
).add_to(m)

for f in facilities:
    folium.Marker(
        [f["lat"], f["lon"]],
        tooltip=f["name"],
        popup=f["name"],
        icon=folium.Icon(color="blue")
    ).add_to(m)

if nearest:
    folium.PolyLine(
        nearest[2],
        color="green",
        weight=6,
        tooltip="Road route to nearest reachable demo facility"
    ).add_to(m)

st.write("Click the map to move the incident point.")

map_data = st_folium(
    m,
    height=520,
    width=None,
    key="route_map"
)

if map_data and map_data.get("last_clicked"):
    p = map_data["last_clicked"]

    new = [
        round(p["lat"], 5),
        round(p["lng"], 5)
    ]

    if new != st.session_state.incident:
        st.session_state.incident = new
        st.rerun()

st.caption(
    "Nearest facility is selected by calculated road "
    "distance among demonstration candidates. "
    "Flooded roads, closures, traffic, and actual "
    "facility capacity are not considered."
)
