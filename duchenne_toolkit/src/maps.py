"""Generate interactive and static maps for Duchenne coverage analysis.

This script creates an interactive folium map showing county‐level modeled
DMD counts and certified care center locations, as well as a static
PNG map summarising coverage bands.  The maps are written to the
`maps/` directory.
"""

from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt
from .config import MAPS, COVERAGE_OUTPUT, CENTERS_OUTPUT

def make_interactive_map():
    """Create an interactive map if folium is available.

    If the `folium` package is not installed or external datasets cannot be
    downloaded, this function will quietly skip map creation.
    """
    try:
        import folium  # type: ignore
        from folium.features import GeoJsonTooltip
        import json  # imported here to avoid unused import when folium is missing
        import requests
        from .config import DMD_MODEL_OUTPUT, COUNTIES_GEOJSON_URL

        # Attempt to download county GeoJSON
        print("Attempting to create interactive map...")
        geojson_resp = requests.get(COUNTIES_GEOJSON_URL)
        geojson_resp.raise_for_status()
        counties_geojson = geojson_resp.json()
        # Load model and centers
        df_model = pd.read_csv(DMD_MODEL_OUTPUT, dtype={"state_fips": str, "county_fips": str})
        df_centers = pd.read_csv(CENTERS_OUTPUT)
        df_model["fips"] = df_model["state_fips"] + df_model["county_fips"]
        m = folium.Map(location=[39.8283, -98.5795], zoom_start=4, tiles="cartodbpositron")
        # Choropleth
        folium.Choropleth(
            geo_data=counties_geojson,
            name="Modeled DMD (mid)",
            data=df_model,
            columns=["fips", "modeled_dmd_5_24_mid"],
            key_on="feature.id",
            fill_color="YlOrRd",
            fill_opacity=0.7,
            line_opacity=0.1,
            nan_fill_color="white",
            legend_name="Modeled DMD cases (ages 5–24)"
        ).add_to(m)
        folium.GeoJson(
            counties_geojson,
            style_function=lambda x: {"fillColor": "transparent", "color": "transparent"},
            tooltip=GeoJsonTooltip(
                fields=["NAME"],
                aliases=["County"],
            ),
        ).add_to(m)
        for _, row in df_centers.iterrows():
            if pd.notnull(row.get("lat")) and pd.notnull(row.get("lon")):
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=4,
                    color="blue",
                    fill=True,
                    fill_opacity=0.8,
                    popup=f"{row['center_name']} ({row['state']})",
                ).add_to(m)
        m.save(MAPS / "duchenne_coverage_interactive.html")
        print(f"Saved interactive map to {MAPS / 'duchenne_coverage_interactive.html'}")
    except Exception as exc:
        print(f"Skipping interactive map creation due to missing dependencies or download error: {exc}")


def make_static_map():
    """Create a static PNG map of coverage bands.

    This implementation does not rely on external datasets; instead it
    approximates county centroids using state geographic centers.
    """
    df_cov = pd.read_csv(COVERAGE_OUTPUT, dtype={"state_fips": str, "county_fips": str})
    df_centers = pd.read_csv(CENTERS_OUTPUT)
    # Hard-coded state centroid mapping (duplicated from coverage.py for independence)
    STATE_CENTROIDS = {
        "01": (32.806671, -86.791130), "02": (61.370716, -152.404419), "04": (33.729759, -111.431221),
        "05": (34.969704, -92.373123), "06": (36.116203, -119.681564), "08": (39.059811, -105.311104),
        "09": (41.597782, -72.755371), "10": (39.318523, -75.507141), "11": (38.897438, -77.026817),
        "12": (27.766279, -81.686783), "13": (33.040619, -83.643074), "15": (21.094318, -157.498337),
        "16": (44.240459, -114.478828), "17": (40.349457, -88.986137), "18": (39.849426, -86.258278),
        "19": (42.011539, -93.210526), "20": (38.526600, -96.726486), "21": (37.668140, -84.670067),
        "22": (31.169546, -91.867805), "23": (44.693947, -69.381927), "24": (39.063946, -76.802101),
        "25": (42.230171, -71.530106), "26": (43.326618, -84.536095), "27": (45.694454, -93.900192),
        "28": (32.741646, -89.678696), "29": (38.456085, -92.288368), "30": (46.921925, -110.454353),
        "31": (41.125370, -98.268082), "32": (38.313515, -117.055374), "33": (43.452492, -71.563896),
        "34": (40.298904, -74.521011), "35": (34.840515, -106.248482), "36": (42.165726, -74.948051),
        "37": (35.630066, -79.806419), "38": (47.528912, -99.784012), "39": (40.388783, -82.764915),
        "40": (35.565342, -96.928917), "41": (44.572021, -122.070938), "42": (40.590752, -77.209755),
        "44": (41.680893, -71.511780), "45": (33.856892, -80.945007), "46": (44.299782, -99.438828),
        "47": (35.747845, -86.692345), "48": (31.054487, -97.563461), "49": (40.150032, -111.862434),
        "50": (44.045876, -72.710686), "51": (37.769337, -78.169968), "53": (47.400902, -121.490494),
        "54": (38.491226, -80.954453), "55": (44.268543, -89.616508), "56": (42.756771, -107.302490),
    }
    # Mapping of state abbreviations to FIPS codes (duplicate of coverage module)
    STATE_ABBR_TO_FIPS = {
        "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
        "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
        "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
        "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
        "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
        "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
        "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
        "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
        "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
        "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
        "WY": "56",
    }

    # Assign lat/lon to counties and centers
    lats = []
    lons = []
    for _, r in df_cov.iterrows():
        coords = STATE_CENTROIDS.get(r["state_fips"], (39.8283, -98.5795))
        lats.append(coords[0])
        lons.append(coords[1])
    df_cov["lat"] = lats
    df_cov["lon"] = lons
    center_lats = []
    center_lons = []
    for _, r in df_centers.iterrows():
        # use center lat/lon if present; otherwise state centroid
        if pd.notnull(r.get("lat")) and pd.notnull(r.get("lon")):
            center_lats.append(r["lat"])
            center_lons.append(r["lon"])
        else:
            coords = STATE_CENTROIDS.get(STATE_ABBR_TO_FIPS.get(r["state"], ""), (39.8283, -98.5795))
            center_lats.append(coords[0])
            center_lons.append(coords[1])
    df_centers["plot_lat"] = center_lats
    df_centers["plot_lon"] = center_lons
    # Plot scatter map
    fig, ax = plt.subplots(figsize=(12, 8))
    band_colors = {
        "<=150": "#2ca25f",
        "150_300": "#fec44f",
        ">300": "#de2d26",
        "Unknown": "#f0f0f0",
    }
    for band, color in band_colors.items():
        subset = df_cov[df_cov["band_miles"] == band]
        ax.scatter(subset["lon"], subset["lat"], s=8, color=color, label=band, alpha=0.6)
    ax.scatter(df_centers["plot_lon"], df_centers["plot_lat"], s=50, color="blue", marker="^", label="Care centers")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Approximate Duchenne care access distance bands (state centroids)")
    ax.legend(title="Distance band (mi)")
    plt.tight_layout()
    MAPS.mkdir(parents=True, exist_ok=True)
    fig.savefig(MAPS / "duchenne_coverage_national.png", dpi=300)
    plt.close(fig)
    print(f"Saved static map to {MAPS / 'duchenne_coverage_national.png'}")


def main():
    make_interactive_map()
    make_static_map()


if __name__ == "__main__":
    main()