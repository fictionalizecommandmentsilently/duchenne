"""Configuration constants for the Duchenne Access Coverage Toolkit.

This module centralizes file paths, prevalence rates and other constants
used throughout the pipeline.  Changing values here propagates to all
scripts.
"""

from pathlib import Path
import datetime

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = BASE_DIR / "data_raw"
DATA_INTERMEDIATE = BASE_DIR / "data_intermediate"
DATA_FINAL = BASE_DIR / "data_final"
DOCS = BASE_DIR / "docs"
MAPS = BASE_DIR / "maps"

# Current run date
RUN_DATE = datetime.datetime.now().date().isoformat()

# Prevalence rates (cases per population)
# MD STARnet DBMD prevalence (per 10,000 males 5–24).  Use mid estimate 1.47,
# low 1.3 and high 1.8 as reported【514519091151079†L144-L147】.
DBMD_PREVALENCE_MID = 1.47 / 10_000
DBMD_PREVALENCE_LOW = 1.3 / 10_000
DBMD_PREVALENCE_HIGH = 1.8 / 10_000

# Fraction of DBMD assumed to be DMD (approximate, 75%)
DMD_FRACTION_OF_DBMD = 0.75

# Diagnosed DMD prevalence (per 100,000 males 5–24) – placeholder value
# Many registry‐based estimates report around 6 per 100,000.  This value
# should be replaced with a properly cited value when available.
DMD_DIAGNOSED_PREVALENCE = 6 / 100_000

# Distance bands (miles)
BAND_MILES = {
    "<=150": (0, 150),
    "150_300": (150, 300),
    ">300": (300, float("inf")),
}

# Drive time bands (minutes)
BAND_DRIVE = {
    "<=120": (0, 120),
    "120_360": (120, 360),
    ">360": (360, float("inf")),
}

# ACS year to query (5‑year estimate)
ACS_YEAR = 2022

# Output file names
CENTERS_OUTPUT = DATA_FINAL / "centers_cdcc_us.csv"
ACS_OUTPUT = DATA_FINAL / "county_demographics_acs.csv"
DMD_MODEL_OUTPUT = DATA_FINAL / "county_dmd_model.csv"
COVERAGE_OUTPUT = DATA_FINAL / "county_coverage.csv"
GAP_OUTPUT = DATA_FINAL / "gap_counties.csv"
COVERAGE_SUMMARY_MD = DOCS / "coverage_summary.md"
SOURCES_JSON = DOCS / "sources.json"

# Geocoding settings
GEOCODER_USER_AGENT = "duchenne_toolkit_geocoder"

# OpenRouteService API key (optional) – set this environment variable if available.
import os
ORS_API_KEY = os.getenv("ORS_API_KEY")

# County centers dataset (population-weighted centroid) CSV
# Source: Benjamin T. Skinner – county_centers.csv (population and geographic centers)
COUNTY_CENTERS_URL = "https://raw.githubusercontent.com/btskinner/spatial/master/data/county_centers.csv"

# US counties GeoJSON for folium choropleth
COUNTIES_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"