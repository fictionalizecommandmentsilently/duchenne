# app.py
import pandas as pd
import streamlit as st
import pydeck as pdk

import logging
import json
from typing import Optional
from duchenne_toolkit.src.utils_io import geocode_address
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
        # lat/lon variants will be unified later to standard 'lat'/'lon'
        "lat": "centroid_lat",   # only if these were county cols in some versions
        "lon": "centroid_lon",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    # Standardize to 'lat' and 'lon' if possible.
    lat_candidates = ["centroid_lat", "county_lat", "latitude", "lat"]
    lon_candidates = ["centroid_lon", "county_lon", "longitude", "lon", "lng"]
    lat_found = next((c for c in lat_candidates if c in df.columns), None)
    lon_found = next((c for c in lon_candidates if c in df.columns), None)
    # Only rename if 'lat'/'lon' are not already present.
    if lat_found and "lat" not in df.columns:
        df = df.rename(columns={lat_found: "lat"})
    if lon_found and "lon" not in df.columns:
        df = df.rename(columns={lon_found: "lon"})
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

# Load data with spinner and error boundary
with st.spinner("Loading data…"):
    try:
        centers, cov = load_data()
    except Exception as exc:
        # If data files are missing or unreadable, show error and fallback to empty frames
        st.error(f"Failed to load data: {exc}")
        centers, cov = pd.DataFrame(), pd.DataFrame()

# Validate centroid columns early
# Prefer standardised 'lat'/'lon' if present, otherwise fall back to stored candidates
lat_col = "lat" if "lat" in cov.columns else (
    cov["_lat_col"].iloc[0] if (len(cov) and "_lat_col" in cov.columns) else None
)
lon_col = "lon" if "lon" in cov.columns else (
    cov["_lon_col"].iloc[0] if (len(cov) and "_lon_col" in cov.columns) else None
)
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

# Sidebar filters with persistence via session_state
states = sorted(cov["state_fips"].dropna().unique()) if "state_fips" in cov.columns else []
if "state_pick" not in st.session_state:
    st.session_state["state_pick"] = states or []
if "band_pick" not in st.session_state:
    st.session_state["band_pick"] = [">300", "150_300", "<=150"]
if "min_cases" not in st.session_state:
    st.session_state["min_cases"] = 0.0
state_pick = st.sidebar.multiselect(
    "Filter by state FIPS",
    options=states,
    default=st.session_state["state_pick"],
    key="state_pick",
)
band_pick = st.sidebar.multiselect(
    "Distance band (miles)",
    options=["<=150", "150_300", ">300"],
    default=st.session_state["band_pick"],
    key="band_pick",
)
min_cases = st.sidebar.number_input(
    "Min modeled DMD cases (mid)",
    min_value=0.0,
    value=st.session_state["min_cases"],
    step=0.5,
    key="min_cases",
)

tabs = st.tabs(["Overview", "Map", "Tables", "About", "Edit Data"])

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
    st.caption(
        "The metrics above summarise the modeled Duchenne muscular dystrophy (DMD) mid estimates for all counties "
        "and for your current filter selection. "
        "The **Selected share** tells you what proportion of the national burden is represented by the counties you’ve chosen."
    )

    # Band breakdown
    if "band_miles" in cov.columns and "modeled_dmd_5_24_mid" in cov.columns:
        band_sum = f.groupby("band_miles")["modeled_dmd_5_24_mid"].sum().reindex(["<=150","150_300",">300"]).fillna(0)
        st.write("Modeled DMD by distance band (selected):")
        st.dataframe(
            band_sum.reset_index().rename(columns={"band_miles": "Band", "modeled_dmd_5_24_mid": "DMD mid"}),
            use_container_width=True,
        )
        st.caption(
            "This breakdown shows how the modeled DMD burden is distributed across straight-line distance bands from the nearest care centre. "
            "Use it to identify whether most cases are within close reach (≤150 mi) or far away (>300 mi)."
        )

# ---- Map -------------------------------------------------------------------
with tabs[1]:
    if not has_centroids:
        st.error(
            "No coordinate columns found. Expected columns like `lat` and `lon` (or variants like `centroid_lat`). "
            "Open the Tables tab to inspect your coverage columns."
        )
    else:
        # Description and controls
        st.markdown(
            "**Map of counties and centers**: marker size scales with modeled DMD mid estimates and color encodes distance bands. "
            "Use the **Zoom to data** button to focus on the filtered counties and optionally geocode missing locations.",
            help="Red markers are counties >300 miles from a certified center; green ≤150 miles."
        )
        # Build plotting frame
        map_df = f.copy()
        # Ensure lat/lon numeric
        map_df = _coerce_numeric(map_df, [lat_col, lon_col])
        # Optionally geocode missing coordinates
        missing_mask = map_df[[lat_col, lon_col]].isna().any(axis=1) if lat_col and lon_col else None
        if missing_mask is not None and missing_mask.any():
            with st.expander(f"{missing_mask.sum()} counties missing coordinates"):
                st.write(
                    "Some counties lack latitude/longitude. "
                    "Check your input CSV or tick the box below to attempt geocoding via Nominatim. "
                    "Geocoding results are cached to avoid repeated lookups."
                )
                do_geocode = st.checkbox("Attempt geocoding for missing counties")
                if do_geocode:
                    with st.spinner("Geocoding missing counties…"):
                        for idx, row in map_df[missing_mask].iterrows():
                            # Build a query from county name and state FIPS if available
                            query_parts = []
                            if isinstance(row.get("county_name"), str):
                                query_parts.append(row["county_name"])
                            if isinstance(row.get("state_fips"), str):
                                query_parts.append(row["state_fips"])
                            query = ", ".join(query_parts) + ", USA"
                            try:
                                cached = st.cache_data(ttl=60 * 60 * 24)(geocode_address)
                                res = cached(query)  # type: ignore
                                if res:
                                    lat, lon, _ = res
                                    map_df.at[idx, lat_col] = lat
                                    map_df.at[idx, lon_col] = lon
                            except Exception as exc:
                                logging.warning(f"Failed to geocode {query}: {exc}")
                    # recalc mask after geocoding
                    missing_mask = map_df[[lat_col, lon_col]].isna().any(axis=1)

        before = len(map_df)
        map_df = map_df.dropna(subset=[lat_col, lon_col])
        dropped = before - len(map_df)
        if dropped > 0:
            st.info(f"Dropped {dropped} rows without coordinates from map layer.")

        def color_for_band(b):
            return COLOR_BY_BAND.get(b, DEFAULT_COLOR)
        map_df["color"] = map_df["band_miles"].map(color_for_band)
        map_df["radius"] = map_df["modeled_dmd_5_24_mid"].clip(lower=0) * 1500 + 5000

        # Create pydeck layers
        county_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=[lon_col, lat_col],
            get_radius="radius",
            get_fill_color="color",
            pickable=True,
        )
        centers_vis = (
            centers.dropna(subset=["lat", "lon"])
            if {"lat", "lon"}.issubset(centers.columns)
            else pd.DataFrame()
        )
        center_layer = (
            pdk.Layer(
                "ScatterplotLayer",
                data=centers_vis,
                get_position=["lon", "lat"],
                get_radius=8000,
                get_fill_color=[0, 0, 0],
                pickable=True,
            )
            if not centers_vis.empty
            else None
        )
        layers = [county_layer] + ([center_layer] if center_layer else [])

        # Build tooltip text
        tooltip_lines = []
        if "county_name" in map_df.columns:
            tooltip_lines.append("County: {county_name}")
        if "band_miles" in map_df.columns:
            tooltip_lines.append("Band: {band_miles}")
        if "modeled_dmd_5_24_mid" in map_df.columns:
            tooltip_lines.append("DMD mid: {modeled_dmd_5_24_mid}")
        if "nearest_center_name" in map_df.columns:
            tooltip_lines.append("Nearest: {nearest_center_name}")
        if "great_circle_mi" in map_df.columns:
            tooltip_lines.append("Distance (mi): {great_circle_mi}")
        tooltip_txt = "\\n".join(tooltip_lines) if tooltip_lines else "{ }"

        # Zoom control
        col_zoom, col_spacer = st.columns([1, 8])
        if col_zoom.button("Zoom to data"):
            # Compute bounding box
            lat_min, lat_max = map_df[lat_col].min(), map_df[lat_col].max()
            lon_min, lon_max = map_df[lon_col].min(), map_df[lon_col].max()
            mid_lat = (lat_min + lat_max) / 2.0
            mid_lon = (lon_min + lon_max) / 2.0
            span = max(lat_max - lat_min, lon_max - lon_min)
            # Heuristic zoom level: smaller spans => larger zoom
            if span > 20:
                zoom_level = 3
            elif span > 10:
                zoom_level = 4
            elif span > 5:
                zoom_level = 5
            elif span > 2:
                zoom_level = 6
            else:
                zoom_level = 7
            st.session_state["map_view_state"] = pdk.ViewState(
                latitude=mid_lat, longitude=mid_lon, zoom=zoom_level
            )
        # Determine view state from session state or default
        view_state: pdk.ViewState = st.session_state.get(
            "map_view_state", pdk.ViewState(latitude=39.5, longitude=-98.35, zoom=3.4)
        )
        st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=view_state,
                map_style=None,
                tooltip={"text": tooltip_txt},
            )
        )
        # Legend
        st.markdown(
            """
            **Legend**  
            <span style="display:inline-block;width:12px;height:12px;background:rgb(0,160,0);margin-right:6px"></span> ≤150 miles  
            <span style="display:inline-block;width:12px;height:12px;background:rgb(240,160,0);margin-right:6px"></span> 150–300 miles  
            <span style="display:inline-block;width:12px;height:12px;background:rgb(200,0,0);margin-right:6px"></span> >300 miles  
            """,
            unsafe_allow_html=True,
        )

# ---- Tables ----------------------------------------------------------------
with tabs[2]:
    st.subheader("Top gap counties (>300 miles)")
    st.caption(
        "Counties listed here are more than 300 miles from the nearest certified Duchenne centre. "
        "They are sorted by modeled DMD mid estimate to highlight areas with the largest estimated patient populations. "
        "Advocacy efforts may prioritise these regions."
    )
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
    st.caption(
        "This table lists certified Duchenne care centres and key details. "
        "Use the new **Edit Data** tab to update addresses, certification years or coordinates."
    )
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
        - Certified Duchenne care centres (black dots).  
        - County markers sized by modelled DMD mid estimate (males 5–24).  
        - Colour encodes straight‑line distance from county centroid to nearest centre (green ≤150 mi, orange 150–300 mi, red >300 mi).  

        **Why it matters**  
        The map highlights counties where patients may need to travel long distances to access specialised Duchenne care. Identifying high‑population counties in the >300 mile band can guide advocacy for new centres or outreach services.  

        **Next steps**  
        - Filter by state or case thresholds to focus on specific regions.  
        - Use the **Zoom to data** button to centre the map on your selection.  
        - Tick “Attempt geocoding” in the Map tab to fill in missing coordinates using open geocoders (results are cached).  
        - Visit the **Edit Data** tab to update centre addresses, certification years or county coverage values directly in the app.  
        - Provide a GitHub personal access token in the app secrets to commit your edits back to the repository on Streamlit Cloud.  

        **Notes**  
        - Drive times aren’t computed in this app; distances are great‑circle (straight‑line) miles.  
        - If you see no map points: check that your coverage CSV has coordinate columns (`centroid_lat`/`centroid_lon` or `lat`/`lon`).  
        - Replacing CSVs in `duchenne_toolkit/data_final/` and redeploying will refresh the data.
        """
    )

with st.expander("Debug: coverage columns"):
    st.write(list(cov.columns))
    st.write(cov.head())

# ---- Edit Data -------------------------------------------------------------
with tabs[4]:
    st.header("Edit Data")
    st.markdown(
        "Use the editor below to update values in the coverage or centers datasets. "
        "After making changes, review the diff preview and click **Save** to write the updated CSV. "
        "Click **Revert** to undo unsaved changes. In production on Streamlit Cloud, you can provide "
        "a GitHub personal access token (`github_token`) via `st.secrets` to commit changes back to the repository."
    )
    # Dataset selector
    dataset_choice = st.radio(
        "Which dataset would you like to edit?",
        options=["Coverage", "Centers"],
        horizontal=True,
    )
    # Pick data and session keys
    if dataset_choice == "Coverage":
        orig_df = cov.copy()
        session_key = "edit_cov"
        file_name = "county_coverage.csv"
        file_path = DATA_DIR / file_name
    else:
        orig_df = centers.copy()
        session_key = "edit_centers"
        file_name = "centers_cdcc_us.csv"
        file_path = DATA_DIR / file_name
    # Initialize session state with original if not present
    if session_key not in st.session_state:
        st.session_state[session_key] = orig_df.copy()
    # Editable dataframe
    edited_df = st.data_editor(
        st.session_state[session_key],
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{dataset_choice}",
    )
    # Update session state
    st.session_state[session_key] = edited_df
    # Diff preview
    try:
        diff_df = edited_df.compare(orig_df, align_axis=0)
    except Exception:
        diff_df = pd.DataFrame()
    with st.expander("Preview changes (diff vs original)"):
        if not diff_df.empty:
            st.dataframe(diff_df, use_container_width=True)
        else:
            st.caption("No changes detected.")
    col_revert, col_save = st.columns(2)
    # Revert changes button
    if col_revert.button(f"Revert {dataset_choice} changes"):
        st.session_state[session_key] = orig_df.copy()
        st.experimental_rerun()
    # Save changes button
    if col_save.button(f"Save {dataset_choice} CSV"):
        try:
            # Validate numeric columns (lat/lon) if present
            if "lat" in edited_df.columns:
                edited_df["lat"] = pd.to_numeric(edited_df["lat"], errors="coerce")
            if "lon" in edited_df.columns:
                edited_df["lon"] = pd.to_numeric(edited_df["lon"], errors="coerce")
            # Determine whether to commit via GitHub API or local write
            token: Optional[str] = st.secrets.get("github_token") if hasattr(st, "secrets") else None
            if token:
                import base64
                import requests
                # Build API endpoint
                repo_owner = st.secrets.get("github_repo_owner", "")
                repo_name = st.secrets.get("github_repo_name", "")
                branch = st.secrets.get("github_branch", "main")
                api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
                headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
                # Get current file SHA
                resp = requests.get(api_url, headers=headers)
                sha = resp.json().get("sha") if resp.ok else None
                # Prepare content
                csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
                encoded = base64.b64encode(csv_bytes).decode("utf-8")
                payload = {
                    "message": f"Update {file_name} via Streamlit editor",
                    "content": encoded,
                    "sha": sha,
                    "branch": branch,
                }
                put_resp = requests.put(api_url, headers=headers, json=payload)
                if put_resp.ok:
                    st.success(f"Committed changes to {file_name} on GitHub.")
                else:
                    st.error(f"Failed to commit to GitHub: {put_resp.status_code} {put_resp.text}")
            # Always write locally as a backup
            edited_df.to_csv(file_path, index=False)
            st.success(f"Saved {file_name} locally.")
            # Refresh dataframes in memory
            if dataset_choice == "Coverage":
                cov = edited_df.copy()
            else:
                centers = edited_df.copy()
        except Exception as exc:
            st.error(f"Error saving {file_name}: {exc}")
