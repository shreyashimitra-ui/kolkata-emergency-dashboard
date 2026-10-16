
import math
import io
import html
import requests
import pandas as pd
import streamlit as st
import folium

from folium.plugins import AntPath, MarkerCluster
from streamlit_folium import st_folium

# =====================================================
# CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="Greater Kolkata Emergency Command Centre",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Greater Kolkata demonstration coverage:
# south, west, north, east
# Rectangular study extent, NOT an administrative boundary.
BBOX = (22.35, 88.15, 22.85, 88.65)

CENTER = [22.5726, 88.3639]

ORS_URL = (
    "https://api.heigit.org/openrouteservice/"
    "v2/directions/driving-car/geojson"
)

OVERPASS_SERVERS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

SCENARIOS = {
    "Flood": {
        "icon": "🌊",
        "color": "#38bdf8",
        "facility": "Shelter",
        "message": "FLOOD SCENARIO — Assess shelter accessibility."
    },
    "Fire": {
        "icon": "🔥",
        "color": "#fb923c",
        "facility": "Fire Station",
        "message": "FIRE SCENARIO — Locate nearby fire stations."
    },
    "Medical Emergency": {
        "icon": "🚑",
        "color": "#4ade80",
        "facility": "Hospital",
        "message": "MEDICAL SCENARIO — Locate nearby hospitals."
    }
}

SYMBOLS = {
    "Hospital": "🏥",
    "Fire Station": "🚒",
    "Shelter": "🏠"
}

# =====================================================
# DARK THEME
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
    padding-top: 1rem;
    max-width: 1600px;
}
h1, h2, h3 {
    color: #f1f7ff !important;
}
.command-header {
    padding: 22px;
    background: linear-gradient(110deg,#142d49,#091725);
    border: 1px solid #305574;
    border-radius: 14px;
    margin-bottom: 15px;
}
.command-title {
    font-size: clamp(1.4rem,3vw,2rem);
    font-weight: 800;
    color: #f5fbff;
}
.command-sub {
    color: #a8c3da;
    font-size: .9rem;
}
.alert-panel {
    padding: 15px;
    background: #172b40;
    border-left: 5px solid var(--accent);
    border-radius: 9px;
    margin: 12px 0;
    animation: glow 3s infinite;
}
@keyframes glow {
    0%,100% {box-shadow:0 0 0 transparent;}
    50% {box-shadow:0 0 15px rgba(56,189,248,.2);}
}
[data-testid="stMetric"] {
    background: #14263b;
    border: 1px solid #30506c;
    border-radius: 12px;
    padding: 12px;
}
[data-testid="stMetricValue"] {
    color: #f5fbff;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# GEOGRAPHIC FUNCTIONS
# =====================================================

def inside_area(lat, lon):
    s, w, n, e = BBOX
    return s <= lat <= n and w <= lon <= e


def haversine(lat1, lon1, lat2, lon2):
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    return 2 * radius * math.asin(
        min(1.0, math.sqrt(a))
    )


# =====================================================
# OPENSTREETMAP DATA
# =====================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_osm_facilities():

    s, w, n, e = BBOX
    bbox = f"{s},{w},{n},{e}"

    query = f"""
    [out:json][timeout:90];
    (
      nwr["amenity"="hospital"]({bbox});
      nwr["amenity"="fire_station"]({bbox});
    );
    out center;
    """

    last_error = "No response"

    for server in OVERPASS_SERVERS:
        try:
            response = requests.post(
                server,
                data={"data": query},
                timeout=110,
                headers={
                    "User-Agent":
                    "KolkataGIS-EducationalDashboard/1.0"
                }
            )
            response.raise_for_status()
            data = response.json()

            facilities = []
            seen = set()

            for item in data.get("elements", []):
                tags = item.get("tags", {})

                amenity = tags.get("amenity")

                if amenity == "hospital":
                    facility_type = "Hospital"
                elif amenity == "fire_station":
                    facility_type = "Fire Station"
                else:
                    continue

                center = item.get("center", item)

                lat = center.get("lat")
                lon = center.get("lon")

                if lat is None or lon is None:
                    continue

                lat = float(lat)
                lon = float(lon)

                if not inside_area(lat, lon):
                    continue

                osm_id = (
                    f"{item.get('type')}/"
                    f"{item.get('id')}"
                )

                if osm_id in seen:
                    continue

                seen.add(osm_id)

                facilities.append({
                    "id": osm_id,
                    "name": (
                        tags.get("name")
                        or f"Unnamed {facility_type}"
                    ),
                    "type": facility_type,
                    "lat": lat,
                    "lon": lon,
                    "source": "OpenStreetMap",
                    "verified": False
                })

            return facilities, None

        except (
            requests.RequestException,
            ValueError
        ) as exc:
            last_error = str(exc)

    return [], last_error


# =====================================================
# VERIFIED SHELTER DATA
# =====================================================

def load_verified_shelters(uploaded_file):

    if uploaded_file is None:
        return [], None

    try:
        df = pd.read_csv(uploaded_file)

        required = {
            "name",
            "latitude",
            "longitude",
            "verified",
            "source"
        }

        if not required.issubset(df.columns):
            return [], (
                "Shelter CSV must contain: "
                "name, latitude, longitude, verified, source"
            )

        shelters = []

        for index, row in df.iterrows():

            verified = str(
                row["verified"]
            ).strip().lower()

            if verified not in [
                "yes", "true", "1"
            ]:
                continue

            name = str(row["name"]).strip()
            source = str(row["source"]).strip()

            if (
                not name
                or name.lower() == "nan"
                or not source
                or source.lower() == "nan"
            ):
                continue

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (TypeError, ValueError):
                continue

            if not inside_area(lat, lon):
                continue

            shelters.append({
                "id": f"shelter-{index}",
                "name": name,
                "type": "Shelter",
                "lat": lat,
                "lon": lon,
                "source": source,
                "verified": True
            })

        return shelters, None

    except Exception as exc:
        return [], str(exc)


# =====================================================
# OPENROUTESERVICE ROUTING
# =====================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_route(
    key,
    start_lat,
    start_lon,
    end_lat,
    end_lon
):

    payload = {
        "coordinates": [
            [start_lon, start_lat],
            [end_lon, end_lat]
        ]
    }

    response = requests.post(
        ORS_URL,
        json=payload,
        headers={
            "Authorization": key,
            "Content-Type": "application/json"
        },
        timeout=30
    )

    response.raise_for_status()

    feature = response.json()["features"][0]

    summary = feature["properties"]["summary"]

    geometry = feature["geometry"]["coordinates"]

    path = [
        [point[1], point[0]]
        for point in geometry
    ]

    return {
        "distance": float(summary["distance"]),
        "duration": float(summary["duration"]),
        "path": path
    }


# =====================================================
# HEADER
# =====================================================

st.markdown("""
<div class="command-header">
  <div class="command-title">
    🚨 GREATER KOLKATA | EMERGENCY COMMAND CENTRE
  </div>
  <div class="command-sub">
    Kolkata · Howrah · Salt Lake · New Town ·
    Adjoining Urban Areas
    <br>
    Geospatial Decision Support | Educational Simulation
  </div>
</div>
""", unsafe_allow_html=True)

# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    st.header("⚙️ Command Controls")

    scenario = st.selectbox(
        "Incident scenario",
        list(SCENARIOS.keys())
    )

    cfg = SCENARIOS[scenario]

    options = [
        "Hospital",
        "Fire Station",
        "Shelter"
    ]

    facility_type = st.selectbox(
        "Response facility",
        options,
        index=options.index(cfg["facility"]),
        key=f"facility_{scenario}"
    )

    st.divider()

    st.subheader("🗺️ Map layers")

    show_hospitals = st.checkbox(
        "Show hospitals", True
    )

    show_fire = st.checkbox(
        "Show fire stations", True
    )

    show_shelters = st.checkbox(
        "Show verified shelters", True
    )

    st.divider()

    st.subheader("📍 Routing controls")

    candidate_count = st.slider(
        "Nearby facilities to evaluate",
        min_value=2,
        max_value=10,
        value=5
    )

    calculate = st.button(
        "🚀 Calculate nearest road route",
        use_container_width=True,
        type="primary"
    )

    if st.button(
        "↩ Reset incident",
        use_container_width=True
    ):
        st.session_state.incident = CENTER.copy()
        st.session_state.map_version = (
            st.session_state.get("map_version", 0) + 1
        )
        st.rerun()

    st.divider()

    st.subheader("🏠 Verified shelter data")

    uploaded_shelters = st.file_uploader(
        "Upload approved shelter CSV",
        type=["csv"]
    )

    st.caption(
        "Only rows marked verified=yes are used. "
        "The uploader does not independently "
        "authenticate the source."
    )

    st.divider()

    st.caption(
        "Training system only. "
        "No live emergency validation."
    )

# =====================================================
# SESSION STATE
# =====================================================

if "incident" not in st.session_state:
    st.session_state.incident = CENTER.copy()

if "map_version" not in st.session_state:
    st.session_state.map_version = 0

if "route_result" not in st.session_state:
    st.session_state.route_result = None

if "route_signature" not in st.session_state:
    st.session_state.route_signature = None

lat, lon = st.session_state.incident

# =====================================================
# LOAD FACILITIES
# =====================================================

with st.spinner(
    "🛰️ Loading mapped facilities across Greater Kolkata..."
):
    osm_facilities, osm_error = load_osm_facilities()

shelters, shelter_error = load_verified_shelters(
    uploaded_shelters
)

facilities = osm_facilities + shelters

if osm_error:
    st.error(
        "OpenStreetMap facility retrieval failed: "
        + osm_error[:250]
    )

if shelter_error:
    st.warning(shelter_error)

hospital_count = sum(
    f["type"] == "Hospital" for f in facilities
)

fire_count = sum(
    f["type"] == "Fire Station" for f in facilities
)

shelter_count = len(shelters)

# =====================================================
# SCENARIO MESSAGE
# =====================================================

st.markdown(
    f"""
    <div class="alert-panel"
         style="--accent:{cfg['color']}">
      <strong>
        {cfg['icon']} {cfg['message']}
      </strong>
      <div style="color:#b9d0e2;margin-top:6px">
        Click anywhere inside the study area to
        position an incident, then calculate a route.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# =====================================================
# FACILITY COUNTERS
# =====================================================

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "🏥 Mapped hospitals",
    hospital_count
)

c2.metric(
    "🚒 Mapped fire stations",
    fire_count
)

c3.metric(
    "🏠 Verified shelters loaded",
    shelter_count
)

c4.metric(
    "📍 Total mapped facilities",
    len(facilities)
)

if shelter_count == 0:
    st.info(
        "No verified shelters loaded. "
        "Upload an approved shelter CSV to enable "
        "shelter routing. Hospitals and fire stations "
        "can still be explored."
    )

# =====================================================
# FIND GEOGRAPHICALLY NEARBY CANDIDATES
# =====================================================

matching = [
    f for f in facilities
    if f["type"] == facility_type
]

for f in matching:
    f["straight_distance"] = haversine(
        lat, lon, f["lat"], f["lon"]
    )

matching.sort(
    key=lambda f: f["straight_distance"]
)

candidates = matching[:candidate_count]

# =====================================================
# CALCULATE ROAD ROUTES ON BUTTON CLICK
# =====================================================

signature = (
    round(lat, 5),
    round(lon, 5),
    facility_type,
    candidate_count,
    tuple(f["id"] for f in candidates)
)

if st.session_state.route_signature != signature:
    st.session_state.route_result = None
    st.session_state.route_signature = signature

if calculate:

    try:
        api_key = st.secrets["ORS_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "ORS_API_KEY is missing from Streamlit Secrets."
        )
        st.stop()

    route_results = []
    route_errors = []

    if not candidates:
        st.warning(
            "No facilities of this type are available."
        )

    else:
        progress = st.progress(0)

        with st.spinner(
            "🚦 Calculating road-network routes..."
        ):
            for i, facility in enumerate(candidates):

                try:
                    route = get_route(
                        api_key,
                        round(lat, 5),
                        round(lon, 5),
                        round(facility["lat"], 5),
                        round(facility["lon"], 5)
                    )

                    route_results.append({
                        "facility": facility,
                        **route
                    })

                except (
                    requests.RequestException,
                    ValueError,
                    KeyError,
                    IndexError
                ) as exc:
                    route_errors.append(str(exc))

                progress.progress(
                    (i + 1) / len(candidates)
                )

        progress.empty()

        route_results.sort(
            key=lambda x: x["distance"]
        )

        st.session_state.route_result = {
            "results": route_results,
            "errors": route_errors
        }

# =====================================================
# ROUTE RESULTS
# =====================================================

saved = st.session_state.route_result

results = saved["results"] if saved else []

nearest = results[0] if results else None

m1, m2, m3 = st.columns(3)

m1.metric(
    "Nearest evaluated facility",
    nearest["facility"]["name"]
    if nearest else "Not calculated"
)

m2.metric(
    "Road distance",
    f"{nearest['distance']/1000:.2f} km"
    if nearest else "—"
)

m3.metric(
    "Estimated driving time",
    f"{nearest['duration']/60:.1f} min"
    if nearest else "—"
)

if nearest:
    st.success(
        "✅ Route calculated to "
        + nearest["facility"]["name"]
        + ". The route follows the modelled road network."
    )

elif saved and saved["errors"]:
    st.error(
        "No road route was returned for the "
        "evaluated candidates."
    )
    with st.expander("Routing error details"):
        st.code(saved["errors"][0][:500])

else:
    st.info(
        "Select an incident location and press "
        "'Calculate nearest road route'."
    )

# =====================================================
# MAP
# =====================================================

left, right = st.columns(
    [3, 1],
    gap="large"
)

with left:

    st.subheader("🗺️ Greater Kolkata Response Map")

    m = folium.Map(
        location=[lat, lon],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True
    )

    # Study area boundary
    folium.Rectangle(
        bounds=[
            [BBOX[0], BBOX[1]],
            [BBOX[2], BBOX[3]]
        ],
        color="#38bdf8",
        weight=2,
        fill=False,
        dash_array="7,7",
        tooltip="Study coverage (not administrative boundary)"
    ).add_to(m)

    # Cluster markers
    cluster = MarkerCluster(
        name="Emergency facilities"
    ).add_to(m)

    visible_types = set()

    if show_hospitals:
        visible_types.add("Hospital")

    if show_fire:
        visible_types.add("Fire Station")

    if show_shelters:
        visible_types.add("Shelter")

    for f in facilities:

        if f["type"] not in visible_types:
            continue

        symbol = SYMBOLS[f["type"]]

        safe_name = html.escape(f["name"])
        safe_source = html.escape(f["source"])

        popup_html = (
            f"<b>{safe_name}</b><br>"
            f"Type: {f['type']}<br>"
            f"Source: {safe_source}<br>"
            "Status: Not independently operationally verified"
        )

        folium.Marker(
            location=[f["lat"], f["lon"]],
            tooltip=f["name"],
            popup=folium.Popup(
                popup_html,
                max_width=300
            ),
            icon=folium.DivIcon(
                html=(
                    '<div style="font-size:23px;'
                    'filter:drop-shadow(0 0 3px black)">'
                    f'{symbol}</div>'
                )
            )
        ).add_to(cluster)

    # Incident marker
    folium.Marker(
        [lat, lon],
        tooltip="Selected incident",
        popup="Simulated emergency incident",
        icon=folium.DivIcon(
            html=(
                '<div style="font-size:34px;'
                'animation:pulse 2s infinite">'
                f'{cfg["icon"]}</div>'
            )
        )
    ).add_to(m)

    # Animated route
    if nearest:
        AntPath(
            locations=nearest["path"],
            color=cfg["color"],
            pulse_color="#ffffff",
            weight=6,
            delay=900,
            dash_array=[12, 20],
            tooltip="Modelled road route"
        ).add_to(m)

        folium.CircleMarker(
            location=[
                nearest["facility"]["lat"],
                nearest["facility"]["lon"]
            ],
            radius=15,
            color="#facc15",
            weight=3,
            fill=False,
            tooltip="Selected destination"
        ).add_to(m)

    clicked = st_folium(
        m,
        height=600,
        width=None,
        key=f"city_map_{st.session_state.map_version}",
        returned_objects=["last_clicked"]
    )

    if clicked and clicked.get("last_clicked"):

        point = clicked["last_clicked"]

        new_lat = round(point["lat"], 5)
        new_lon = round(point["lng"], 5)

        if inside_area(new_lat, new_lon):

            new_point = [new_lat, new_lon]

            if new_point != st.session_state.incident:

                st.session_state.incident = new_point
                st.session_state.map_version += 1
                st.session_state.route_result = None

                st.rerun()

        else:
            st.warning(
                "Please select a location inside "
                "the Greater Kolkata study boundary."
            )

# =====================================================
# FACILITY COMPARISON
# =====================================================

with right:

    st.subheader("📊 Facility Analysis")

    st.caption(
        f"{len(matching)} mapped {facility_type.lower()} "
        "records within the study area."
    )

    if results:

        table = pd.DataFrame([
            {
                "Facility": r["facility"]["name"],
                "Road km": round(
                    r["distance"] / 1000, 2
                ),
                "Time min": round(
                    r["duration"] / 60, 1
                )
            }
            for r in results
        ])

        st.bar_chart(
            table.set_index("Facility")[["Road km"]]
        )

        st.dataframe(
            table,
            hide_index=True,
            use_container_width=True
        )

        st.download_button(
            "⬇ Download route comparison CSV",
            data=table.to_csv(index=False),
            file_name="kolkata_route_comparison.csv",
            mime="text/csv",
            use_container_width=True
        )

    else:

        st.caption(
            "Calculate a route to display "
            "the road-distance comparison."
        )

    st.divider()

    st.subheader("📍 Nearby Candidates")

    candidate_table = pd.DataFrame([
        {
            "Facility": f["name"],
            "Straight km": round(
                f["straight_distance"], 2
            )
        }
        for f in candidates
    ])

    if not candidate_table.empty:

        st.dataframe(
            candidate_table,
            hide_index=True,
            use_container_width=True
        )

    st.caption(
        "Candidates are preselected using straight-line "
        "distance. Road routing then compares those "
        "candidates, not every facility in the city."
    )

# =====================================================
# DATA DOWNLOAD
# =====================================================

st.divider()

st.subheader("📁 Facility Database")

if facilities:

    facility_df = pd.DataFrame(facilities)

    export_columns = [
        "name",
        "type",
        "lat",
        "lon",
        "source",
        "verified"
    ]

    st.download_button(
        "⬇ Download mapped facility database",
        data=facility_df[
            export_columns
        ].to_csv(index=False),
        file_name="greater_kolkata_facilities.csv",
        mime="text/csv"
    )

st.caption(
    "DATA: © OpenStreetMap contributors | "
    "Routing: openrouteservice / HeiGIT | "
    "Study area: illustrative rectangular extent."
)

st.warning(
    "EDUCATIONAL SIMULATION ONLY. "
    "OSM facility records are not independently verified. "
    "Routing does not account for live traffic, road closures, "
    "flood depth, fire spread, hospital availability, "
    "shelter capacity or emergency access permissions. "
    "Do not use this dashboard for actual emergency decisions."
)
