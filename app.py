
import requests
import pandas as pd
import streamlit as st
import folium

from folium.plugins import AntPath
from streamlit_folium import st_folium

# =====================================================
# PAGE CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="Kolkata Emergency Command Centre",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# DARK COMMAND CENTRE DESIGN
# =====================================================

st.markdown("""
<style>

.stApp {
    background: #081321;
    color: #e8f2ff;
}

[data-testid="stSidebar"] {
    background: #101f32;
    border-right: 1px solid #263c58;
}

.block-container {
    padding-top: 1.2rem;
    max-width: 1500px;
}

h1, h2, h3 {
    color: #f1f7ff !important;
}

.command-header {
    padding: 22px 25px;
    background: linear-gradient(
        110deg, #122943, #0a1829
    );
    border: 1px solid #2a5275;
    border-radius: 14px;
    margin-bottom: 16px;
}

.command-title {
    font-size: clamp(1.4rem, 3vw, 2.1rem);
    font-weight: 800;
    letter-spacing: 1px;
    color: #f5fbff;
}

.command-sub {
    color: #9ebad1;
    font-size: 0.9rem;
}

.status {
    border-left: 5px solid var(--accent);
    background: #162a3e;
    padding: 14px 16px;
    border-radius: 8px;
    margin: 12px 0;
    animation: pulse 2.8s ease-in-out infinite;
}

@keyframes pulse {
    0%, 100% {
        box-shadow: 0 0 0 transparent;
    }
    50% {
        box-shadow: 0 0 16px rgba(56,189,248,0.18);
    }
}

[data-testid="stMetric"] {
    background: #13263b;
    border: 1px solid #284763;
    border-radius: 12px;
    padding: 14px;
}

[data-testid="stMetricLabel"] {
    color: #a8c1d5;
}

[data-testid="stMetricValue"] {
    color: #f3faff;
}

</style>
""", unsafe_allow_html=True)

# =====================================================
# DISASTER SCENARIOS
# =====================================================

SCENARIOS = {
    "Flood": {
        "icon": "🌊",
        "color": "#39b9ff",
        "facility": "Shelter",
        "message": (
            "FLOOD SIMULATION — "
            "Check nearby shelters and road accessibility."
        )
    },
    "Fire": {
        "icon": "🔥",
        "color": "#ff9854",
        "facility": "Fire Station",
        "message": (
            "FIRE SIMULATION — "
            "Locate reachable fire response facilities."
        )
    },
    "Medical Emergency": {
        "icon": "🚑",
        "color": "#55dc9a",
        "facility": "Hospital",
        "message": (
            "MEDICAL SIMULATION — "
            "Find the nearest reachable hospital."
        )
    }
}

# =====================================================
# DEMONSTRATION FACILITIES
# These are fictional locations.
# =====================================================

FACILITIES = [
    {
        "name": "Demo Hospital A",
        "type": "Hospital",
        "lat": 22.585,
        "lon": 88.410
    },
    {
        "name": "Demo Hospital B",
        "type": "Hospital",
        "lat": 22.570,
        "lon": 88.440
    },
    {
        "name": "Demo Shelter A",
        "type": "Shelter",
        "lat": 22.575,
        "lon": 88.430
    },
    {
        "name": "Demo Shelter B",
        "type": "Shelter",
        "lat": 22.600,
        "lon": 88.420
    },
    {
        "name": "Demo Fire Station A",
        "type": "Fire Station",
        "lat": 22.565,
        "lon": 88.400
    },
    {
        "name": "Demo Fire Station B",
        "type": "Fire Station",
        "lat": 22.590,
        "lon": 88.450
    }
]

# =====================================================
# DASHBOARD HEADER
# =====================================================

st.markdown("""
<div class="command-header">
    <div class="command-title">
        🚨 KOLKATA | EMERGENCY COMMAND CENTRE
    </div>
    <div class="command-sub">
        Interactive Geospatial Decision Support System
        | Educational Disaster Simulation
    </div>
</div>
""", unsafe_allow_html=True)

# =====================================================
# SIDEBAR CONTROLS
# =====================================================

with st.sidebar:

    st.header("⚙️ Command Controls")

    scenario = st.selectbox(
        "Incident Scenario",
        list(SCENARIOS.keys())
    )

    cfg = SCENARIOS[scenario]

    facility_options = [
        "Shelter",
        "Hospital",
        "Fire Station"
    ]

    facility_type = st.selectbox(
        "Response Facility",
        facility_options,
        index=facility_options.index(
            cfg["facility"]
        ),
        key=f"facility_{scenario}"
    )

    st.caption(
        "Select a disaster scenario and click "
        "anywhere on the map to move the incident."
    )

    if st.button(
        "↩ Reset Incident to Salt Lake",
        use_container_width=True
    ):
        st.session_state.incident = [
            22.580,
            88.420
        ]
        st.rerun()

    st.divider()

    st.info(
        "All facility names are fictional. "
        "This dashboard is for training only."
    )

# =====================================================
# INCIDENT LOCATION
# =====================================================

if "incident" not in st.session_state:
    st.session_state.incident = [
        22.580,
        88.420
    ]

lat, lon = st.session_state.incident

# =====================================================
# ANIMATED STATUS MESSAGE
# =====================================================

st.markdown(
    f"""
    <div class="status"
         style="--accent:{cfg['color']}">

        <strong>
            {cfg['icon']} {cfg['message']}
        </strong>

        <div style="
            color:#b8cbdf;
            font-size:0.85rem;
            margin-top:6px;
        ">
            Click on the map to update the incident
            location and recalculate the road route.
        </div>

    </div>
    """,
    unsafe_allow_html=True
)

# =====================================================
# OPENROUTESERVICE API KEY
# =====================================================

try:
    api_key = st.secrets["ORS_API_KEY"]

except (KeyError, FileNotFoundError):

    st.error(
        "Routing API key not found. "
        "Add ORS_API_KEY to Streamlit Secrets."
    )

    st.stop()

# =====================================================
# ROAD NETWORK ROUTING
# =====================================================

@st.cache_data(
    ttl=1800,
    show_spinner=False
)
def get_route(
    key,
    origin_lat,
    origin_lon,
    dest_lat,
    dest_lon
):

    url = (
        "https://api.heigit.org/"
        "openrouteservice/v2/"
        "directions/driving-car/geojson"
    )

    payload = {
        "coordinates": [
            [origin_lon, origin_lat],
            [dest_lon, dest_lat]
        ]
    }

    headers = {
        "Authorization": key,
        "Content-Type": "application/json"
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=25
    )

    response.raise_for_status()

    data = response.json()

    feature = data["features"][0]

    summary = feature[
        "properties"
    ]["summary"]

    coordinates = feature[
        "geometry"
    ]["coordinates"]

    route_path = [
        [point[1], point[0]]
        for point in coordinates
    ]

    return (
        float(summary["distance"]),
        float(summary["duration"]),
        route_path
    )

# =====================================================
# FIND NEAREST REACHABLE FACILITY
# =====================================================

results = []
errors = []

with st.spinner(
    "🛰️ Analysing road-network accessibility..."
):

    for facility in FACILITIES:

        if facility["type"] != facility_type:
            continue

        try:

            distance, duration, path = get_route(
                api_key,
                round(lat, 5),
                round(lon, 5),
                facility["lat"],
                facility["lon"]
            )

            results.append({
                "facility": facility,
                "distance": distance,
                "duration": duration,
                "path": path
            })

        except (
            requests.RequestException,
            KeyError,
            ValueError,
            IndexError
        ) as exc:

            errors.append(str(exc))

results.sort(
    key=lambda x: x["distance"]
)

nearest = (
    results[0]
    if results
    else None
)

# =====================================================
# DASHBOARD METRICS
# =====================================================

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Incident",
    f"{cfg['icon']} {scenario}"
)

c2.metric(
    "Nearest Demo Facility",
    nearest["facility"]["name"]
    if nearest else "Unavailable"
)

c3.metric(
    "Road Distance",
    f"{nearest['distance']/1000:.2f} km"
    if nearest else "N/A"
)

c4.metric(
    "Estimated Driving Time",
    f"{nearest['duration']/60:.1f} min"
    if nearest else "N/A"
)

# =====================================================
# ROUTE STATUS NOTIFICATION
# =====================================================

if nearest:

    st.success(
        f"✅ Route calculated to "
        f"{nearest['facility']['name']}. "
        f"Modelled road distance: "
        f"{nearest['distance']/1000:.2f} km."
    )

else:

    st.error(
        "⚠️ No road route returned. "
        "Check API quota, connectivity, "
        "or incident location."
    )

    if errors:

        with st.expander(
            "Technical Error Details"
        ):
            st.code(errors[0][:700])

# =====================================================
# MAP AND FACILITY COMPARISON
# =====================================================

left, right = st.columns(
    [3, 1],
    gap="large"
)

with left:

    st.subheader(
        "🗺️ Interactive Response Map"
    )

    # Corrected basemap:
    # No additional CARTO API key required.

    m = folium.Map(
        location=[lat, lon],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True
    )

    # Incident marker

    folium.Marker(
        [lat, lon],
        tooltip=(
            f"{cfg['icon']} "
            f"Incident: {scenario}"
        ),
        popup="Simulated Incident",
        icon=folium.DivIcon(
            html=(
                '<div style="font-size:32px;'
                f'filter:drop-shadow(0 0 6px {cfg["color"]})">'
                f'{cfg["icon"]}</div>'
            )
        )
    ).add_to(m)

    # Facility symbols

    icons = {
        "Hospital": "🏥",
        "Shelter": "🏠",
        "Fire Station": "🚒"
    }

    for facility in FACILITIES:

        folium.Marker(
            [
                facility["lat"],
                facility["lon"]
            ],
            tooltip=facility["name"],
            popup=(
                f"{facility['name']} — "
                "fictional demonstration facility"
            ),
            icon=folium.DivIcon(
                html=(
                    '<div style="font-size:24px">'
                    f'{icons[facility["type"]]}'
                    '</div>'
                )
            )
        ).add_to(m)

    # Animated road route

    if nearest:

        AntPath(
            nearest["path"],
            color=cfg["color"],
            pulse_color="#ffffff",
            weight=6,
            delay=900,
            dash_array=[12, 20],
            tooltip="Modelled Driving Route"
        ).add_to(m)

    # Map interaction

    clicked = st_folium(
        m,
        height=530,
        width=None,
        key="command_map",
        returned_objects=[
            "last_clicked"
        ]
    )

    if clicked and clicked.get(
        "last_clicked"
    ):

        point = clicked[
            "last_clicked"
        ]

        new_point = [
            round(point["lat"], 5),
            round(point["lng"], 5)
        ]

        if (
            new_point
            != st.session_state.incident
        ):

            st.session_state.incident = (
                new_point
            )

            st.rerun()

# =====================================================
# FACILITY COMPARISON CHART
# =====================================================

with right:

    st.subheader(
        "📊 Facility Comparison"
    )

    if results:

        chart_data = pd.DataFrame([
            {
                "Facility": r[
                    "facility"
                ]["name"],
                "Road Distance (km)": round(
                    r["distance"] / 1000,
                    2
                )
            }
            for r in results
        ])

        st.bar_chart(
            chart_data.set_index(
                "Facility"
            )
        )

        table_data = pd.DataFrame([
            {
                "Facility": r[
                    "facility"
                ]["name"],
                "Distance (km)": round(
                    r["distance"] / 1000,
                    2
                ),
                "Time (min)": round(
                    r["duration"] / 60,
                    1
                )
            }
            for r in results
        ])

        st.dataframe(
            table_data,
            hide_index=True,
            use_container_width=True
        )

    else:

        st.caption(
            "No reachable demonstration "
            "facilities to compare."
        )

    st.caption(
        "Driving times are model estimates, "
        "not live traffic or emergency "
        "response times."
    )

# =====================================================
# FOOTER
# =====================================================

st.divider()

st.caption(
    "⚠️ EDUCATIONAL SIMULATION ONLY | "
    "Fictional Facilities | "
    "No Live Incident Feeds | "
    "No Flood Depth or Road Closure Validation | "
    "Not for Actual Emergency Decisions"
)
