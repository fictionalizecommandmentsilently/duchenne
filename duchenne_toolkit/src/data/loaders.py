from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

# Paths relative to the package root: duchenne_toolkit/
BASE_DIR: Path = Path(__file__).resolve().parents[2]
DATA_FINAL_DIR: Path = BASE_DIR / "data_final"
LOOKUP_DIR: Path = BASE_DIR / "data" / "lookups"
DERIVED_DIR: Path = BASE_DIR / "data" / "derived"


def _ensure_lat_lon(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int | None]]:
    report: Dict[str, int | None] = {}
    df = df.copy()

    rmap = {}
    for cand in ["latitude", "lat_dd", "INTPTLAT", "y", "Lat", "LAT"]:
        if cand in df.columns:
            rmap[cand] = "lat"
            break
    for cand in ["longitude", "lon_dd", "lng", "INTPTLONG", "x", "Lon", "LON"]:
        if cand in df.columns:
            rmap[cand] = "lon"
            break
    if rmap:
        df = df.rename(columns=rmap)

    for c in ["lat", "lon"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if {"lat", "lon"}.issubset(df.columns):
        before = len(df)
        df = df.dropna(subset=["lat", "lon"])
        report["dropped_missing_coords"] = before - len(df)
    else:
        report["dropped_missing_coords"] = None

    return df, report


def load_coverage() -> Tuple[pd.DataFrame, Dict[str, int | str | None]]:
    """
    Load duchenne_toolkit/data_final/county_coverage.csv and enrich with county centroids.
    Persists a derived CSV with coords to duchenne_toolkit/data/derived/coverage_with_coords.csv
    and returns (df, debug_report).
    """
    debug: Dict[str, int | str | None] = {}
    path = DATA_FINAL_DIR / "county_coverage.csv"
    df = pd.read_csv(path, dtype=str)

    if "state_fips" in df.columns:
        df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)
    if "county_fips" in df.columns:
        df["county_fips"] = df["county_fips"].astype(str).str.zfill(3)
    if {"state_fips", "county_fips"}.issubset(df.columns):
        df["geoid"] = df["state_fips"] + df["county_fips"]
    else:
        df["geoid"] = pd.NA

    df, rep0 = _ensure_lat_lon(df)
    debug.update(rep0)

    need_coords = (
        ({"lat", "lon"}.issubset(df.columns) and (df["lat"].isna() | df["lon"].isna()).any())
        or not {"lat", "lon"}.issubset(df.columns)
    )

    if need_coords:
        lookup_file = LOOKUP_DIR / "county_centroids.csv"
        if lookup_file.exists():
            lookup = pd.read_csv(lookup_file, dtype={"GEOID": str})
            lookup = lookup.rename(
                columns={"GEOID": "geoid", "INTPTLAT": "centroid_lat", "INTPTLONG": "centroid_lon"}
            )
            lookup["centroid_lat"] = pd.to_numeric(lookup["centroid_lat"], errors="coerce")
            lookup["centroid_lon"] = pd.to_numeric(lookup["centroid_lon"], errors="coerce")

            df = df.merge(lookup[["geoid", "centroid_lat", "centroid_lon"]], on="geoid", how="left")
            if "lat" not in df.columns:
                df["lat"] = df["centroid_lat"]
            else:
                df["lat"] = df["lat"].fillna(df["centroid_lat"])
            if "lon" not in df.columns:
                df["lon"] = df["centroid_lon"]
            else:
                df["lon"] = df["lon"].fillna(df["centroid_lon"])
            df = df.drop(columns=[c for c in ["centroid_lat", "centroid_lon"] if c in df.columns])
        # else: leave missing; app will warn

    if {"lat", "lon"}.issubset(df.columns):
        debug["missing_after_merge"] = int((df["lat"].isna() | df["lon"].isna()).sum())
    else:
        debug["missing_after_merge"] = None

    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    derived_path = DERIVED_DIR / "coverage_with_coords.csv"
    df.to_csv(derived_path, index=False)
    debug["derived_path"] = str(derived_path)

    return df, debug
