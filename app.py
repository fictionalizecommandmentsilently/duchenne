# app.py
import pandas as pd
import streamlit as st
import pydeck as pdk
from pathlib import Path

st.set_page_config(page_title="Duchenne Access Coverage", layout="wide")
DATA_DIR = Path("duchenne_toolkit/data_final")

# ---- helpers ---------------------------------------------------------------

def _coerce_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def _normalize_columns(df):
    # Unify common variants
    rename_map = {
        "county": "county_name",
        "County": "county_name",
        "STATEFP": "state_fips",
        "COUNTYFP": "county_fips",
        "statefp": "state_fips",
        "countyfp": "county_fips",
        "lat": "centroid_lat",   # only if these were county cols in some versions
        "lon": "centroid_lon",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    return df

def _ensure_modeled(df_cov):
    # Add modeled value if missing
    if "modeled_dmd_5_24_mid" not in df_cov.columns:
        # Try to pull from the model CSV
        model_path = DATA_DIR / "county_dmd_model.csv"
        if model_path.exists():
            model = pd.read_csv(model_path, dtype={"state_fips": str, "county_fips": str})
            keep = ["state_fips", "county_fips", "modeled_dmd_5_24_mid"]
            keep = [c for c in keep if c in model.columns]
            df_cov = df_cov.merge(model[keep], on=["state_fips", "county_fips"], how="left")
    # Duplicates from merges like modeled_dmd_5_24_mid_x/y
    if "modeled_dmd_5_24_mid" not in df_cov.columns:
        alts = [c for c in df_cov.columns if c.startswith("modeled_dmd_5_24_mid")]
        if alts:
            df_cov["modeled_dmd_5_24_mid"] = df_cov[alts[0]]
    if "modeled_dmd_5_24_mid" not in df_cov.columns:
        df_cov["modeled_dmd_5_24_mid"] = 0.0
    return df_cov

def _find_centroid_cols(df_cov):
    # Accept several possibilities
    lat_candidates = ["centroid_lat", "county_lat", "latitude", "lat"]
    lon_candidates = ["centroid_lon", "county_lon", "longitude", "lon", "lng"]
    lat = next((c for c in lat_candidates if c in df_cov.columns), None)
    lon = next((c for c in lon_candidates if c in df_cov.columns), None)
    return lat, lon

COLOR_BY_BAND = {
    "<=150": [0, 160, 0],
    "150_300": [240, 160, 0],
    ">300": [200, 0, 0],
}
DEFAULT_COLOR = [120, 120, 120]

# ---- data ------------------------------------------------------------------

@st.cache_data
def load_data():
    centers = pd.read_csv(DATA_DIR / "centers_cdcc_us.csv", dtype={"state": str}, low_memory=False)
    cov     = pd.read_csv(DATA_DIR / "county_coverage.csv",
                          dtype={"state_fips": str, "county_fips": str},
                          low_memory=False)
    cov = _normalize_columns(cov)
    cov = _ensure_modeled(cov)
    cov = _coerce_numeric(cov, ["modeled_dmd_5_24_mid", "great_circle_mi"])
    # Identify centroid columns
    lat_col, lon_col = _find_centroid_cols(cov)
    cov["_lat_col"] = lat_col or ""
    cov["_lon_col"] = lon_col or ""
    # Centers numeric
    centers = _coerce_numeric(centers, ["lat","lon"])
    return centers, cov

centers, cov = load_data()

# Validate centroid columns early
lat_col = cov["_lat_col"].iloc[0] if len(cov) else None
lon_col = cov["_lon_col"].iloc[0] if len(cov) else None
has_centroids = bool(lat_col and lon_col)

# ---- UI --------------------------------------------------------------------

st.title("Duchenne Access Coverage")

with st.expander("What you’re looking at", expanded=True):
    st.write(
        "This app shows where certified Duchenne care centers are and how far each county’s modeled DMD population "
        "is from the nearest center. Colors reflect straight-line distance bands: "
        "≤150 miles (green), 150–300 miles (orange), and >300 miles (red). "
        "Counts use mid estimates for males ages 5–24."
    )

# Sidebar filters
states = sorted(cov["state_fips"].dropna().unique()) if "state_fips" in cov.columns else []
state_pick = st.sidebar.multiselect("Filter by state FIPS", options=states, default=states or None)
band_pick  = st.sidebar.multiselect("Distance band (miles)",
                                    options=["<=150","150_300",">300"],
                                    default=[">300","150_300","<=150"])
min_cases  = st.sidebar.number_input("Min modeled DMD cases (mid)",
                                     min_value=0.0, value=0.0, step=0.5)

tabs = st.tabs(["Overview", "Map", "Tables", "About"])

# ---- filter ----------------------------------------------------------------
f = cov.copy()
if states and state_pick:
    f = f[f["state_fips"].isin(state_pick)]
if "band_miles" in f.columns:
    f = f[f["band_miles"].isin(band_pick)]
if "modeled_dmd_5_24_mid" in f.columns:
    f = f[f["modeled_dmd_5_24_mid"] >= min_cases]

# ---- Overview --------------------------------------------------------------
with tabs[0]:
    total = cov["modeled_dmd_5_24_mid"].sum() if "modeled_dmd_5_24_mid" in cov.columns else 0
    sel_total = f["modeled_dmd_5_24_mid"].sum() if "modeled_dmd_5_24_mid" in f.columns else 0
    pct = (sel_total / total * 100) if total else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total modeled DMD (mid)", f"{total:,.0f}")
    c2.metric("Selected modeled DMD (mid)", f"{sel_total:,.0f}")
    c3.metric("Selected share", f"{pct:0.1f}%")
    c4.metric("Counties selected", f"{len(f):,}")

    # Band breakdown
    if "band_miles" in cov.columns and "modeled_dmd_5_24_mid" in cov.columns:
        band_sum = f.groupby("band_miles")["modeled_dmd_5_24_mid"].sum().reindex(["<=150","150_300",">300"]).fillna(0)
        st.write("Modeled DMD by distance band (selected):")
        st.dataframe(
            band_sum.reset_index().rename(columns={"band_miles":"Band","modeled_dmd_5_24_mid":"DMD mid"}),
            use_container_width=True
        )

# ---- Map -------------------------------------------------------------------
with tabs[1]:
    if not has_centroids:
        st.error("No coordinate columns found. Expected columns like 'centroid_lat' and 'centroid_lon'. "
                 "Open the Tables tab to inspect your coverage columns.")
    else:
        # Build plotting frame
        map_df = f.copy()
        map_df = _coerce_numeric(map_df, [lat_col, lon_col])
        before = len(map_df)
        map_df = map_df.dropna(subset=[lat_col, lon_col])
        dropped = before - len(map_df)

        if dropped > 0:
            st.info(f"Dropped {dropped} rows without coordinates from map layer.")

        def color_for_band(b):
            return COLOR_BY_BAND.get(b, DEFAULT_COLOR)

        map_df["color"] = map_df["band_miles"].map(color_for_band)
        map_df["radius"] = map_df["modeled_dmd_5_24_mid"].clip(lower=0) * 1500 + 5000

        county_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=[lon_col, lat_col],
            get_radius="radius",
            get_fill_color="color",
            pickable=True,
        )

        centers_vis = centers.dropna(subset=["lat","lon"]) if {"lat","lon"}.issubset(centers.columns) else pd.DataFrame()
        center_layer = pdk.Layer(
            "ScatterplotLayer",
            data=centers_vis,
            get_position=["lon","lat"] if {"lat","lon"}.issubset(centers.columns) else None,
            get_radius=8000,
            get_fill_color=[0,0,0],
            pickable=True,
        ) if not centers_vis.empty else None

        layers = [county_layer] + ([center_layer] if center_layer else [])

        tooltip_lines = []
        if "county_name" in map_df.columns: tooltip_lines.append("County: {county_name}")
        if "band_miles" in map_df.columns:  tooltip_lines.append("Band: {band_miles}")
        if "modeled_dmd_5_24_mid" in map_df.columns: tooltip_lines.append("DMD mid: {modeled_dmd_5_24_mid}")
        if "nearest_center_name" in map_df.columns: tooltip_lines.append("Nearest: {nearest_center_name}")
        if "great_circle_mi" in map_df.columns: tooltip_lines.append("Distance (mi): {great_circle_mi}")
        tooltip_txt = "\\n".join(tooltip_lines) if tooltip_lines else "{ }"

        view = pdk.ViewState(latitude=39.5, longitude=-98.35, zoom=3.4)
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=view,
            map_style=None,  # no token required
            tooltip={"text": tooltip_txt},
        ))

        # Legend
        st.markdown(
            """
            **Legend**  
            <span style="display:inline-block;width:12px;height:12px;background:rgb(0,160,0);margin-right:6px"></span> ≤150 miles  
            <span style="display:inline-block;width:12px;height:12px;background:rgb(240,160,0);margin-right:6px"></span> 150–300 miles  
            <span style="display:inline-block;width:12px;height:12px;background:rgb(200,0,0);margin-right:6px"></span> >300 miles  
            """,
            unsafe_allow_html=True
        )

# ---- Tables ----------------------------------------------------------------
with tabs[2]:
    st.subheader("Top gap counties (>300 miles)")
    if "band_miles" in cov.columns:
        gaps = f[f["band_miles"].eq(">300")] if "band_miles" in f.columns else pd.DataFrame()
        if "modeled_dmd_5_24_mid" in f.columns and not gaps.empty:
            gaps = gaps.sort_values("modeled_dmd_5_24_mid", ascending=False)
        cols = [c for c in ["state_fips","county_fips","county_name","modeled_dmd_5_24_mid",
                             "nearest_center_name","great_circle_mi"] if c in gaps.columns]
        st.dataframe(gaps[cols].head(200), use_container_width=True)
    else:
        st.info("No 'band_miles' column found in coverage CSV.")

    st.subheader("Centers")
    if not centers.empty:
        ccols = [c for c in ["center_name","health_system","city","state",
                             "certification_year","website","phone","lat","lon"] if c in centers.columns]
        st.dataframe(centers[ccols], use_container_width=True)
    else:
        st.info("Centers CSV is empty or missing expected columns.")

    st.download_button("Download coverage CSV", data=cov.to_csv(index=False), file_name="county_coverage.csv")
    st.download_button("Download centers CSV", data=centers.to_csv(index=False), file_name="centers_cdcc_us.csv")

# ---- About -----------------------------------------------------------------
with tabs[3]:
    st.markdown(
        """
        **What’s shown**  
        - Certified Duchenne care centers (black dots).  
        - County markers sized by modeled DMD mid estimate (males 5–24).  
        - Color = straight-line distance from county centroid to nearest center.  

        **Notes**  
        - Drive times aren’t computed in this app. Distances are great-circle miles.  
        - If you see no map points: check your coverage CSV has coordinate columns like `centroid_lat` and `centroid_lon`.  
        - Replace CSVs in `duchenne_toolkit/data_final/` and redeploy to refresh.
        """
    )

with st.expander("Debug: coverage columns"):
    st.write(list(cov.columns))
    st.write(cov.head())
