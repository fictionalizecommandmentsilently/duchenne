"""Compute coverage metrics for counties relative to Duchenne care centers.

This script combines modeled DMD counts with geocoded care centers and
county centroids to determine the nearest center for each county.  It
calculates straight‐line distances and approximate drive times, assigns
each county to distance and time bands, and flags gaps where counties
are beyond the longest band.  Summary statistics and gap lists are
exported to CSV and markdown files.
"""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
import requests
import pandas as pd
import requests

from .config import (
    CENTERS_OUTPUT,
    DMD_MODEL_OUTPUT,
    COVERAGE_OUTPUT,
    GAP_OUTPUT,
    BAND_MILES,
    BAND_DRIVE,
    COUNTY_CENTERS_URL,
)
from .utils_io import read_csv, write_csv, haversine_distance, classify_band

# Hard-coded geographic center coordinates for each US state and DC.
# These approximate central points are used as a fallback when county
# centroid data cannot be downloaded.  Coordinates are sourced from
# publicly available state centroid approximations (degrees N, degrees W).
STATE_CENTROIDS = {
    "01": (32.806671, -86.791130),  # Alabama
    "02": (61.370716, -152.404419),  # Alaska
    "04": (33.729759, -111.431221),  # Arizona
    "05": (34.969704, -92.373123),  # Arkansas
    "06": (36.116203, -119.681564),  # California
    "08": (39.059811, -105.311104),  # Colorado
    "09": (41.597782, -72.755371),  # Connecticut
    "10": (39.318523, -75.507141),  # Delaware
    "11": (38.897438, -77.026817),  # District of Columbia
    "12": (27.766279, -81.686783),  # Florida
    "13": (33.040619, -83.643074),  # Georgia
    "15": (21.094318, -157.498337),  # Hawaii
    "16": (44.240459, -114.478828),  # Idaho
    "17": (40.349457, -88.986137),  # Illinois
    "18": (39.849426, -86.258278),  # Indiana
    "19": (42.011539, -93.210526),  # Iowa
    "20": (38.526600, -96.726486),  # Kansas
    "21": (37.668140, -84.670067),  # Kentucky
    "22": (31.169546, -91.867805),  # Louisiana
    "23": (44.693947, -69.381927),  # Maine
    "24": (39.063946, -76.802101),  # Maryland
    "25": (42.230171, -71.530106),  # Massachusetts
    "26": (43.326618, -84.536095),  # Michigan
    "27": (45.694454, -93.900192),  # Minnesota
    "28": (32.741646, -89.678696),  # Mississippi
    "29": (38.456085, -92.288368),  # Missouri
    "30": (46.921925, -110.454353),  # Montana
    "31": (41.125370, -98.268082),  # Nebraska
    "32": (38.313515, -117.055374),  # Nevada
    "33": (43.452492, -71.563896),  # New Hampshire
    "34": (40.298904, -74.521011),  # New Jersey
    "35": (34.840515, -106.248482),  # New Mexico
    "36": (42.165726, -74.948051),  # New York
    "37": (35.630066, -79.806419),  # North Carolina
    "38": (47.528912, -99.784012),  # North Dakota
    "39": (40.388783, -82.764915),  # Ohio
    "40": (35.565342, -96.928917),  # Oklahoma
    "41": (44.572021, -122.070938),  # Oregon
    "42": (40.590752, -77.209755),  # Pennsylvania
    "44": (41.680893, -71.511780),  # Rhode Island
    "45": (33.856892, -80.945007),  # South Carolina
    "46": (44.299782, -99.438828),  # South Dakota
    "47": (35.747845, -86.692345),  # Tennessee
    "48": (31.054487, -97.563461),  # Texas
    "49": (40.150032, -111.862434),  # Utah
    "50": (44.045876, -72.710686),  # Vermont
    "51": (37.769337, -78.169968),  # Virginia
    "53": (47.400902, -121.490494),  # Washington
    "54": (38.491226, -80.954453),  # West Virginia
    "55": (44.268543, -89.616508),  # Wisconsin
    "56": (42.756771, -107.302490),  # Wyoming
}


def build_state_centroid_df(df_model: pd.DataFrame) -> pd.DataFrame:
    """Build a fallback centroid DataFrame using state geographic centers.

    This function assigns the same latitude and longitude to every
    county within a state using approximate geographic center
    coordinates defined in STATE_CENTROIDS.

    Args:
        df_model: County-level model dataframe from which to derive
            unique state and county codes.

    Returns:
        DataFrame with columns state_fips, county_fips, centroid_lat,
        centroid_lon.
    """
    records = []
    for _, row in df_model.iterrows():
        state_fips = str(row["state_fips"]).zfill(2)
        county_fips = str(row["county_fips"]).zfill(3)
        coords = STATE_CENTROIDS.get(state_fips)
        if coords:
            lat, lon = coords
        else:
            # Default to continental US center if unknown
            lat, lon = 39.8283, -98.5795
        records.append({
            "state_fips": state_fips,
            "county_fips": county_fips,
            "centroid_lat": lat,
            "centroid_lon": lon,
        })
    return pd.DataFrame(records)


def load_county_centroids() -> pd.DataFrame:
    """Load county centroid coordinates from the external CSV dataset.

    The dataset includes population-weighted and geographic center coordinates
    for 2000 and 2010.  We use the 2010 population-weighted center
    (pclat10, pclon10) when available; otherwise fall back to the
    geographic center (clat10, clon10).
    """
    print("Downloading county centers dataset...")
    resp = requests.get(COUNTY_CENTERS_URL)
    resp.raise_for_status()
    from io import StringIO
    df_centers = pd.read_csv(StringIO(resp.text))
    # FIPS codes may have leading spaces; strip and pad
    df_centers["fips"] = df_centers["fips"].astype(str).str.strip().str.zfill(5)
    # Use population-weighted coordinates if available, else spatial
    df_centers["centroid_lat"] = df_centers["pclat10"].fillna(df_centers["clat10"])
    df_centers["centroid_lon"] = df_centers["pclon10"].fillna(df_centers["clon10"])
    df_centers["state_fips"] = df_centers["fips"].str[:2]
    df_centers["county_fips"] = df_centers["fips"].str[2:]
    return df_centers[["state_fips", "county_fips", "centroid_lat", "centroid_lon"]]


def compute_nearest_center(county_lat: float, county_lon: float, centers_df: pd.DataFrame) -> tuple:
    """Return the nearest center's id, name and distance in miles."""
    min_dist = float("inf")
    nearest_id = None
    nearest_name = None
    for _, row in centers_df.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            continue
        dist = haversine_distance(county_lat, county_lon, row["lat"], row["lon"])
        if dist < min_dist:
            min_dist = dist
            nearest_id = row["center_id"]
            nearest_name = row["center_name"]
    return nearest_id, nearest_name, min_dist


def main():
    # Load data
    df_centers = read_csv(CENTERS_OUTPUT)
    df_model = read_csv(DMD_MODEL_OUTPUT)
    # If center coordinates are missing, assign state centroid coordinates
    # Build mapping of state abbreviations to FIPS codes
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
    # Assign FIPS and centroid coordinates for each center if lat/lon missing
    def assign_center_coords(row):
        if pd.notnull(row.get("lat")) and pd.notnull(row.get("lon")):
            return row["lat"], row["lon"]
        state_abbr = row.get("state")
        fips = STATE_ABBR_TO_FIPS.get(state_abbr)
        coords = STATE_CENTROIDS.get(fips)
        if coords:
            return coords
        # Default to continental US center
        return (39.8283, -98.5795)
    lats = []
    lons = []
    for _, r in df_centers.iterrows():
        lat, lon = assign_center_coords(r)
        lats.append(lat)
        lons.append(lon)
    df_centers["lat"] = lats
    df_centers["lon"] = lons
    # Load county centroids
    try:
        gdf_centroids = load_county_centroids()
    except Exception as exc:
        print(f"Warning: failed to download county centroids ({exc}). Falling back to state centroids.")
        # Fallback: approximate county centroids by state geographic centers
        gdf_centroids = build_state_centroid_df(df_model)
    # Ensure FIPS columns are strings for merging
    df_model["state_fips"] = df_model["state_fips"].astype(str).str.zfill(2)
    df_model["county_fips"] = df_model["county_fips"].astype(str).str.zfill(3)
    gdf_centroids["state_fips"] = gdf_centroids["state_fips"].astype(str).str.zfill(2)
    gdf_centroids["county_fips"] = gdf_centroids["county_fips"].astype(str).str.zfill(3)
    # Merge model with centroids on FIPS codes only
    df = df_model.merge(gdf_centroids, on=["state_fips", "county_fips"], how="left")
    # Compute nearest center for each county
    nearest_ids: list[str | None] = []
    nearest_names: list[str | None] = []
    distances: list[float | None] = []
    drive_times: list[float | None] = []
    for _, row in df.iterrows():
        county_lat = row["centroid_lat"]
        county_lon = row["centroid_lon"]
        # If centroid is missing, skip distance calculation
        if pd.isna(county_lat) or pd.isna(county_lon):
            nearest_ids.append(None)
            nearest_names.append(None)
            distances.append(None)
            drive_times.append(None)
            continue
        center_id, center_name, dist = compute_nearest_center(county_lat, county_lon, df_centers)
        nearest_ids.append(center_id)
        nearest_names.append(center_name)
        distances.append(dist)
        # Approximate drive time: assume 50 mph average speed
        if dist is not None:
            drive_times.append(dist / 50 * 60)  # miles / mph * 60 = minutes
        else:
            drive_times.append(None)
    df["nearest_center_id"] = nearest_ids
    df["nearest_center_name"] = nearest_names
    df["great_circle_mi"] = distances
    df["drive_time_minutes"] = drive_times
    # Classify bands
    df["band_miles"] = df["great_circle_mi"].apply(lambda x: classify_band(x, BAND_MILES) if pd.notnull(x) else "Unknown")
    df["band_drive_time"] = df["drive_time_minutes"].apply(lambda x: classify_band(x, BAND_DRIVE) if pd.notnull(x) else "Unknown")
    # Flags for gaps: counties beyond 300 miles or 360 minutes
    df["flags"] = df.apply(
        lambda r: "distance_gt_300" if r["band_miles"] == ">300" else (
            "drive_gt_360" if r["band_drive_time"] == ">360" else ""
        ),
        axis=1,
    )
    # Keep necessary columns
    df_cov = df[[
        "state_fips", "county_fips", "county_name",
        "nearest_center_id", "nearest_center_name",
        "great_circle_mi", "drive_time_minutes",
        "band_miles", "band_drive_time",
        "modeled_dmd_5_24_mid",
        "flags",
    ]].copy()
    write_csv(COVERAGE_OUTPUT, df_cov)
    print(f"Wrote coverage file to {COVERAGE_OUTPUT}")
    # Gap counties
    df_gap = df_cov[(df_cov["band_miles"] == ">300") | (df_cov["band_drive_time"] == ">360")].copy()
    df_gap = df_gap.sort_values(by="modeled_dmd_5_24_mid", ascending=False)
    write_csv(GAP_OUTPUT, df_gap)
    print(f"Wrote gap file to {GAP_OUTPUT} with {len(df_gap)} counties")


if __name__ == "__main__":
    main()