"""Utility functions for IO, geocoding, and geographic calculations."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import requests
import numpy as np
from math import radians, sin, cos, sqrt, atan2

from .config import GEOCODER_USER_AGENT


def write_csv(path: Path, df: pd.DataFrame) -> None:
    """Write a pandas DataFrame to a CSV file with UTF‑8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV file into a pandas DataFrame."""
    return pd.read_csv(path)


def save_json(path: Path, data: dict) -> None:
    """Write a dictionary to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def geocode_address(address: str, geolocator: Optional[object] = None) -> Optional[Tuple[float, float, dict]]:
    """Geocode an address or place name using the Nominatim HTTP API.

    Returns a tuple of (latitude, longitude, raw_json) or None if not found.
    This function makes an HTTP request to the public Nominatim service and
    should be used sparingly to respect usage limits.  No API key is required.
    """
    try:
        params = {
            "q": address,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": GEOCODER_USER_AGENT}
        resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not results:
            return None
        item = results[0]
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
        return lat, lon, item
    except Exception:
        return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great circle distance between two points in miles using the haversine formula."""
    # Radius of Earth in miles
    R = 3958.8
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def classify_band(value: float, bands: Dict[str, Tuple[float, float]]) -> str:
    """Classify a numeric value into a band defined by ranges.

    Returns the band key whose range (min, max) contains the value.
    """
    for band, (lower, upper) in bands.items():
        if lower <= value < upper:
            return band
    return "Unknown"
