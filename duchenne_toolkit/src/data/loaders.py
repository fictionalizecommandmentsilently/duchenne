"""
Data loading utilities for the Duchenne access toolkit.

This module centralises the logic for reading the county coverage CSV,
enriching it with geographic centroids and standardising latitude and
longitude columns.  Separating these concerns into a dedicated loader
keeps the Streamlit app lean and makes it easier to test data
processing independently of the user interface.

Functions in this module return both the processed DataFrame and a
dictionary of debug metadata (counts of dropped rows, number of rows
still missing coordinates, and the path to the persisted derived file).
The derived CSV is written to ``data/derived/coverage_with_coords.csv``
on each run so that the map page can read a ready‑to‑plot dataset
without repeatedly performing the join.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Tuple, Dict

# Base directory of the duchenne_toolkit package.  ``__file__``
# points to ``duchenne_toolkit/src/data/loaders.py`` so two parents up
# gets us ``duchenne_toolkit``.  From there we can construct paths
# relative to ``data_final`` (raw outputs), ``data/lookups`` (static
# lookup tables) and ``data/derived`` (intermediate products).
BASE_DIR: Path = Path(__file__).resolve().parents[2]
DATA_FINAL_DIR: Path = BASE_DIR / "data_final"
LOOKUP_DIR: Path = BASE_DIR / "data" / "lookups"
DERIVED_DIR: Path = BASE_DIR / "data" / "derived"

def ensure_lat_lon(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int | None]]:
    """Normalise latitude/longitude column names and drop missing rows.

    This helper inspects a DataFrame for any of several common names for
    latitude and longitude columns and renames them to the standard
    ``lat`` and ``lon``.  It then attempts to coerce those columns to
    floats and removes rows where either coordinate is missing.  A
    small report is returned alongside the cleaned DataFrame.

    Parameters
    ----------
    df:
        The DataFrame to clean.  It is not modified in place.

    Returns
    -------
    (DataFrame, dict):
        A tuple containing the cleaned DataFrame and a report
        dictionary with one key, ``dropped_missing_coords``, giving the
        number of rows removed due to missing coordinates (or ``None``
        if coordinate columns were absent entirely).
    """
    rename_map = {
        "centroid_lat": "lat",
        "county_lat": "lat",
        "latitude": "lat",
        "lat": "lat",
        "centroid_lon": "lon",
        "county_lon": "lon",
        "longitude": "lon",
        "lon": "lon",
        "lng": "lon",
    }
    df = df.copy()
    # Rename any variants found; later keys overwrite earlier ones
    for old_name, new_name in rename_map.items():
        if old_name in df.columns:
            df = df.rename(columns={old_name: new_name})
    # Coerce numeric
    for col in ["lat", "lon"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Drop rows lacking both coordinates
    report: Dict[str, int | None] = {}
    if {"lat", "lon"}.issubset(df.columns):
        before = len(df)
        df = df.dropna(subset=["lat", "lon"])
        report["dropped_missing_coords"] = before - len(df)
    else:
        report["dropped_missing_coords"] = None
    return df, report


def load_coverage() -> Tuple[pd.DataFrame, Dict[str, int | str | None]]:
    """Load the county coverage CSV and attach centroid coordinates.

    This function reads ``county_coverage.csv`` from the ``data_final``
    directory, ensures state and county FIPS codes are zero‑padded
    strings, constructs a five‑digit ``geoid`` key, and merges on
    geographic centroids from the lookup table ``county_centroids.csv``
    when coordinates are missing.  After merging, the function calls
    :func:`ensure_lat_lon` to standardise coordinate names, casts to
    floats and drops any residual missing rows.

    A copy of the merged DataFrame is persisted to
    ``data/derived/coverage_with_coords.csv`` on each run for use by
    interactive components.  A dictionary of debug metadata is also
    returned.

    Returns
    -------
    (DataFrame, dict):
        The enriched coverage DataFrame and a report detailing the
        number of rows dropped due to missing coordinates, how many
        remain missing after the centroid merge, and the path to the
        written derived CSV.
    """
    debug: Dict[str, int | str | None] = {}
    cov_path = DATA_FINAL_DIR / "county_coverage.csv"
    df = pd.read_csv(cov_path, dtype={"state_fips": str, "county_fips": str})
    # Ensure zero‑padded FIPS strings
    if "state_fips" in df.columns:
        # Always pad state FIPS to two digits
        df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    if "county_fips" in df.columns:
        # For county FIPS values that may include the state prefix (e.g. 1001 for 001),
        # take the last three digits after zero padding.  This ensures 1→001, 1001→001.
        cf = df["county_fips"].astype(str).str.zfill(3)
        df["county_fips"] = cf.str[-3:]
    # Build GEOID (5‑digit) used in the county lookup
    if {"state_fips", "county_fips"}.issubset(df.columns):
        df["geoid"] = df["state_fips"] + df["county_fips"]
    else:
        df["geoid"] = pd.NA
    # Standardise any existing coordinate columns and drop rows lacking both lat and lon.
    df, rep0 = ensure_lat_lon(df)
    debug.update(rep0)
    # Determine which rows still need coordinates.  If either coordinate
    # column is absent we consider all rows missing.
    if {"lat", "lon"}.issubset(df.columns):
        missing_mask = df["lat"].isna() | df["lon"].isna()
    else:
        missing_mask = pd.Series(True, index=df.index)
    # Only attempt a centroid merge if there are rows without coords
    if missing_mask.any():
        lookup_file = LOOKUP_DIR / "county_centroids.csv"
        if lookup_file.exists():
            lookup = pd.read_csv(lookup_file, dtype={"GEOID": str})
            lookup = lookup.rename(
                columns={"GEOID": "geoid", "INTPTLAT": "centroid_lat", "INTPTLONG": "centroid_lon"}
            )
            # Coerce centroid columns to numeric
            lookup["centroid_lat"] = pd.to_numeric(lookup["centroid_lat"], errors="coerce")
            lookup["centroid_lon"] = pd.to_numeric(lookup["centroid_lon"], errors="coerce")
            # Merge centroid coordinates onto the coverage DataFrame
            df = df.merge(lookup[["geoid", "centroid_lat", "centroid_lon"]], on="geoid", how="left")
            # Create lat/lon columns if they do not yet exist, then fill missing values
            if "lat" not in df.columns:
                df["lat"] = df["centroid_lat"]
            else:
                df["lat"] = df["lat"].fillna(df["centroid_lat"])
            if "lon" not in df.columns:
                df["lon"] = df["centroid_lon"]
            else:
                df["lon"] = df["lon"].fillna(df["centroid_lon"])
            # Drop temporary centroid columns
            df = df.drop(columns=[c for c in ["centroid_lat", "centroid_lon"] if c in df.columns])
        # Recompute missing coordinate count after merge
        if {"lat", "lon"}.issubset(df.columns):
            debug["missing_after_merge"] = int((df["lat"].isna() | df["lon"].isna()).sum())
        else:
            debug["missing_after_merge"] = None
    # Persist the enriched dataset to the derived directory for reuse
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    derived_path = DERIVED_DIR / "coverage_with_coords.csv"
    df.to_csv(derived_path, index=False)
    debug["derived_path"] = str(derived_path)
    return df, debug