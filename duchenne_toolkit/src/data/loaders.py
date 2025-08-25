"""
# Standardise any existing coordinate columns and drop rows lacking both lat and lon.
df, rep0 = ensure_lat_lon(df)
debug.update(rep0)
# Determine which rows still need coordinates. If either coordinate
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
else:
# Fallback: fetch county centroid lookup from the public URL
try:
lookup = pd.read_csv(COUNTY_CENTERS_URL, dtype=str)
# Try to normalise columns to geoid + centroid_lat/lon
cols = {c.lower(): c for c in lookup.columns}
if "geoid" in cols:
lookup = lookup.rename(columns={cols["geoid"]: "geoid"})
elif "fips" in cols:
lookup = lookup.rename(columns={cols["fips"]: "geoid"})
# Identify latitude/longitude columns
lat_col = cols.get("lat") or cols.get("latitude") or cols.get("intptlat") or cols.get("lat_dd")
lon_col = cols.get("lon") or cols.get("longitude") or cols.get("intptlong") or cols.get("lng") or cols.get("lon_dd")
if not lat_col or not lon_col:
raise ValueError("Could not infer centroid latitude/longitude columns from lookup dataset")
lookup = lookup.rename(columns={lat_col: "centroid_lat", lon_col: "centroid_lon"})
# Coerce numeric
lookup["centroid_lat"] = pd.to_numeric(lookup["centroid_lat"], errors="coerce")
lookup["centroid_lon"] = pd.to_numeric(lookup["centroid_lon"], errors="coerce")
# Ensure geoid is zero-padded to 5 digits (some sources use 5-digit county FIPS)
lookup["geoid"] = lookup["geoid"].astype(str).str.zfill(5)
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
except Exception as e:
# Leave coordinates missing; the app will surface a validation message
pass
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
