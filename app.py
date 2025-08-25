"""
Streamlit application for visualising Duchenne access coverage.

This app reads county coverage data and centre information from CSVs,
merges in geographic centroid coordinates using a cached lookup, and
presents interactive views including summary statistics, a map, data
tables and an editing interface.  Edits can optionally be pushed to
GitHub via a pull request when secrets are provided.

The layout uses a tabbed interface with five pages: Overview, Map,
Tables, About and Edit Data.  A sidebar offers filters for state,
distance band and minimum case threshold.  The Map page only renders
once latitude and longitude columns are present; if coordinates are
missing, the user is prompted to inspect the underlying CSV in the
Tables page.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from duchenne_toolkit.src.data.loaders import load_coverage
from duchenne_toolkit.src.utils.validate import (
    validate_fips,
    coerce_distance_band,
    numeric_or_nan,
    show_validation_report,
)
from duchenne_toolkit.src.utils.github import (
    create_branch,
    commit_file,
    open_pr,
)

# Configure the page
st.set_page_config(page_title="DMD Access Coverage", layout="wide")

# Directory for final data
DATA_DIR = Path("duchenne_toolkit/data_final")

# Read secrets for GitHub integration if present.  The presence of
# github_repo, github_token and github_default_branch determine
# whether pull requests can be created.  If any are missing the
# editing interface will still allow saving locally but will not
# attempt to open a PR.
secrets = st.secrets if hasattr(st, "secrets") else {}
required_secrets = ["github_repo", "github_token", "github_default_branch"]
missing_secrets = [k for k in required_secrets if k not in secrets]

# ---- Data loading -----------------------------------------------------------

# Load centres and coverage with proper coordinates.  Use a spinner and
# catch errors to avoid crashing the whole app when data files are
# missing or corrupt.
with st.spinner("Loading data…"):
    try:
        centers = pd.read_csv(DATA_DIR / "centers_cdcc_us.csv", dtype={"state": str}, low_memory=False)
        cov, load_debug = load_coverage()
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
        centers, cov = pd.DataFrame(), pd.DataFrame()
        load_debug: Dict[str, Any] = {}

# Determine whether coordinate columns are available
has_lat_lon: bool = {"lat", "lon"}.issubset(cov.columns)

# Sidebar filters with persistence via session_state
states = sorted(cov["state_fips"].dropna().unique()) if "state_fips" in cov.columns else []
if "state_pick" not in st.session_state:
    st.session_state["state_pick"] = states or []
if "band_pick" not in st.session_state:
    st.session_state["band_pick"] = ["<=150", "150_300", ">300"]
if "min_cases" not in st.session_state:
    st.session_state["min_cases"] = 0.0

state_pick = st.sidebar.multiselect(
    "Filter by state FIPS", options=states, default=st.session_state["state_pick"], key="state_pick"
)
band_pick = st.sidebar.multiselect(
    "Distance band (miles)", options=["<=150", "150_300", ">300"], default=st.session_state["band_pick"], key="band_pick"
)
min_cases = st.sidebar.number_input(
    "Min modelled DMD cases (mid)", min_value=0.0, value=st.session_state["min_cases"], step=0.5, key="min_cases"
)

# Apply filters to a copy of the coverage DataFrame
f = cov.copy()
if states and state_pick:
    f = f[f["state_fips"].isin(state_pick)]
if "band_miles" in f.columns and band_pick:
    f = f[f["band_miles"].isin(band_pick)]
if "modeled_dmd_5_24_mid" in f.columns:
    f = f[f["modeled_dmd_5_24_mid"] >= min_cases]

# ---- UI ---------------------------------------------------------------------

st.title("Duchenne Access Coverage")

with st.expander("What you’re looking at", expanded=True):
    st.write(
        "Each county is plotted at its population‑weighted centroid. "
        "Colours reflect straight‑line distance to the nearest certified Duchenne care centre: "
        "≤150 mi (green), 150–300 mi (orange) and >300 mi (red). "
        "Marker size scales with the modelled number of DMD cases (mid estimate)."
    )
    st.write(
        "**Why it matters:** Identifying counties far from care centres helps advocates prioritise outreach, travel support "
        "and new centre locations."
    )
    st.write("**What to do next:**")
    st.markdown("- Use the sidebar to filter by state, distance band and minimum case count.")
    st.markdown("- Switch to the **Tables** tab to explore the raw data and download CSVs.")
    st.markdown("- Make edits under **Edit Data** and commit them back to GitHub via a pull request.")

tabs = st.tabs(["Overview", "Map", "Tables", "About", "Edit Data"])

# ---- Overview ---------------------------------------------------------------
with tabs[0]:
    # Summary metrics
    total = cov["modeled_dmd_5_24_mid"].sum() if "modeled_dmd_5_24_mid" in cov.columns else 0
    sel_total = f["modeled_dmd_5_24_mid"].sum() if "modeled_dmd_5_24_mid" in f.columns else 0
    pct = (sel_total / total * 100) if total else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total modelled DMD (mid)", f"{total:,.0f}")
    c2.metric("Selected modelled DMD (mid)", f"{sel_total:,.0f}")
    c3.metric("Selected share", f"{pct:0.1f}%")
    c4.metric("Counties selected", f"{len(f):,}")
    st.caption(
        "The metrics above summarise the modelled Duchenne muscular dystrophy (DMD) mid estimates for all counties "
        "and for your current filter selection. "
        "The **Selected share** indicates what proportion of the national burden your selection represents."
    )
    # Band breakdown
    if "band_miles" in f.columns and "modeled_dmd_5_24_mid" in f.columns:
        band_sum = (
            f.groupby("band_miles")["modeled_dmd_5_24_mid"]
            .sum()
            .reindex(["<=150", "150_300", ">300"])  # ensure order
            .fillna(0)
        )
        st.write("Modelled DMD by distance band (selected):")
        st.dataframe(
            band_sum.reset_index().rename(columns={"band_miles": "Band", "modeled_dmd_5_24_mid": "DMD mid"}),
            use_container_width=True,
        )
        st.caption(
            "This breakdown shows how the modelled DMD burden is distributed across straight‑line distance bands. "
            "Use it to identify whether most cases are within close reach (≤150 mi) or far away (>300 mi)."
        )

# ---- Map --------------------------------------------------------------------
with tabs[1]:
    if not has_lat_lon:
        # Show a red callout when coordinate columns are missing entirely
        st.error(
            "No coordinate columns found. Expected columns named `lat` and `lon` or their variants. "
            "Open the **Tables** tab to inspect your coverage CSV and add centroid columns via the data loader."
        )
    else:
        # If no rows remain after filtering, inform the user
        if f.empty:
            st.info("No rows match your current filters.")
        else:
            # Build plotting frame
            map_df = f.copy()
            # Ensure numeric coordinates
            map_df["lat"], _ = numeric_or_nan(map_df["lat"])
            map_df["lon"], _ = numeric_or_nan(map_df["lon"])
            # Drop any rows where coordinates still missing
            before = len(map_df)
            map_df = map_df.dropna(subset=["lat", "lon"])
            dropped = before - len(map_df)
            if dropped > 0:
                st.info(f"Dropped {dropped} rows without coordinates from map layer.")
            # Colour mapping
            COLOR_BY_BAND = {
                "<=150": [0, 160, 0],
                "150_300": [240, 160, 0],
                ">300": [200, 0, 0],
            }
            DEFAULT_COLOR = [120, 120, 120]
            map_df["color"] = map_df.get("band_miles", pd.Series()).map(lambda b: COLOR_BY_BAND.get(b, DEFAULT_COLOR))
            # Radius scales with modelled cases; use fallback constant when missing
            if "modeled_dmd_5_24_mid" in map_df.columns:
                map_df["radius"] = map_df["modeled_dmd_5_24_mid"].clip(lower=0) * 1500 + 5000
            else:
                map_df["radius"] = 5000
            # County layer
            county_layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position=["lon", "lat"],
                get_radius="radius",
                get_fill_color="color",
                pickable=True,
            )
            # Centre layer
            centers_vis = centers.dropna(subset=["lat", "lon"]) if {"lat", "lon"}.issubset(centers.columns) else pd.DataFrame()
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
            layers = [county_layer] + ([center_layer] if center_layer is not None else [])
            # Tooltip template including county/state, band, DMD mid, nearest centre name and miles
            tooltip_lines = []
            if "state_fips" in map_df.columns:
                tooltip_lines.append("State FIPS: {state_fips}")
            if "county_fips" in map_df.columns:
                tooltip_lines.append("County FIPS: {county_fips}")
            if "band_miles" in map_df.columns:
                tooltip_lines.append("Band: {band_miles}")
            if "modeled_dmd_5_24_mid" in map_df.columns:
                tooltip_lines.append("DMD mid: {modeled_dmd_5_24_mid}")
            if "nearest_center_name" in map_df.columns:
                tooltip_lines.append("Nearest: {nearest_center_name}")
            if "great_circle_mi" in map_df.columns:
                tooltip_lines.append("Distance (mi): {great_circle_mi}")
            tooltip_txt = "\n".join(tooltip_lines) if tooltip_lines else "{ }"
            # Zoom control
            col_zoom, _ = st.columns([1, 8])
            if col_zoom.button("Zoom to data") and not map_df.empty:
                lat_min, lat_max = map_df["lat"].min(), map_df["lat"].max()
                lon_min, lon_max = map_df["lon"].min(), map_df["lon"].max()
                mid_lat = (lat_min + lat_max) / 2.0
                mid_lon = (lon_min + lon_max) / 2.0
                span = max(lat_max - lat_min, lon_max - lon_min)
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
                st.session_state["map_view_state"] = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=zoom_level)
            # Determine view state
            view_state = st.session_state.get(
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
                 • ≤150 miles (green)  
                 • 150–300 miles (orange)  
                 • >300 miles (red)
                """,
                unsafe_allow_html=True,
            )

# ---- Tables -----------------------------------------------------------------
with tabs[2]:
    st.subheader("Top gap counties (>300 miles)")
    st.caption(
        "Counties listed here are more than 300 miles from the nearest certified Duchenne centre. "
        "They are sorted by modelled DMD mid estimate to highlight areas with the largest estimated patient populations. "
        "Advocacy efforts may prioritise these regions."
    )
    if "band_miles" in f.columns:
        gaps = f[f["band_miles"].eq(">300")] if "band_miles" in f.columns else pd.DataFrame()
        if "modeled_dmd_5_24_mid" in f.columns and not gaps.empty:
            gaps = gaps.sort_values("modeled_dmd_5_24_mid", ascending=False)
        cols = [
            c
            for c in [
                "state_fips",
                "county_fips",
                "county_name",
                "modeled_dmd_5_24_mid",
                "nearest_center_name",
                "great_circle_mi",
            ]
            if c in gaps.columns
        ]
        st.dataframe(gaps[cols].head(200), use_container_width=True)
    else:
        st.info("No 'band_miles' column found in coverage CSV.")
    st.subheader("Centres")
    st.caption(
        "This table lists certified Duchenne care centres and key details. "
        "Use the **Edit Data** tab to update addresses, certification years or coordinates."
    )
    if not centers.empty:
        ccols = [
            c
            for c in [
                "center_name",
                "health_system",
                "city",
                "state",
                "certification_year",
                "website",
                "phone",
                "lat",
                "lon",
            ]
            if c in centers.columns
        ]
        st.dataframe(centers[ccols], use_container_width=True)
    else:
        st.info("Centres CSV is empty or missing expected columns.")
    # Download buttons
    st.download_button("Download coverage CSV", data=cov.to_csv(index=False), file_name="county_coverage.csv")
    st.download_button("Download centres CSV", data=centers.to_csv(index=False), file_name="centers_cdcc_us.csv")

# ---- About ------------------------------------------------------------------
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
        - Visit the **Edit Data** tab to update centre addresses, certification years or county coverage values directly in the app and submit your changes as a pull request.  

        **Notes**  
        - Distances are great‑circle miles; drive times are not computed in this app.  
        - If you see no map points: check that your coverage CSV has coordinate columns (`lat`/`lon`).  
        - Replacing CSVs in ``duchenne_toolkit/data_final/`` and redeploying will refresh the data.
        """
    )

# Debug panel to inspect columns and show loader debug info
with st.expander("Debug information"):
    st.write("Coverage columns:", list(cov.columns))
    st.write(cov.head())
    if load_debug:
        st.write("Loader report:")
        st.json(load_debug)

# ---- Edit Data --------------------------------------------------------------
with tabs[4]:
    st.header("Edit Data")
    st.markdown(
        "Use the editor below to update values in the coverage or centres datasets. "
        "After making changes, you can validate your edits and optionally create a pull request on GitHub to merge them back into the repository."
    )
    dataset_choice = st.radio(
        "Which dataset would you like to edit?",
        options=["Coverage", "Centres"],
        horizontal=True,
    )
    # Select dataframe and filename
    if dataset_choice == "Coverage":
        orig_df = cov.copy()
        session_key = "edit_cov"
        file_name = "county_coverage.csv"
        file_path = DATA_DIR / file_name
    else:
        orig_df = centers.copy()
        session_key = "edit_centres"
        file_name = "centers_cdcc_us.csv"
        file_path = DATA_DIR / file_name
    # Initialise editable copy in session
    if session_key not in st.session_state:
        st.session_state[session_key] = orig_df.copy()
    edited_df = st.data_editor(
        st.session_state[session_key],
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{dataset_choice}",
    )
    st.session_state[session_key] = edited_df
    # Show diff preview
    try:
        diff_df = edited_df.compare(orig_df, align_axis=0)
    except Exception:
        diff_df = pd.DataFrame()
    with st.expander("Preview changes (diff vs original)"):
        if not diff_df.empty:
            st.dataframe(diff_df, use_container_width=True)
        else:
            st.caption("No changes detected.")
    col_revert, col_save, col_pr = st.columns(3)
    # Revert button resets to original
    if col_revert.button(f"Revert {dataset_choice} changes"):
        st.session_state[session_key] = orig_df.copy()
        st.experimental_rerun()
    # Save button writes locally (always)
    if col_save.button(f"Save {dataset_choice} CSV"):
        try:
            # Coerce numeric lat/lon if present
            if "lat" in edited_df.columns:
                edited_df["lat"], _ = numeric_or_nan(edited_df["lat"])
            if "lon" in edited_df.columns:
                edited_df["lon"], _ = numeric_or_nan(edited_df["lon"])
            edited_df.to_csv(file_path, index=False)
            st.success(f"Saved {file_name} locally.")
        except Exception as exc:
            st.error(f"Error saving {file_name}: {exc}")
    # Validate & Create PR button
    if col_pr.button("Validate & Create PR"):
        # Collect validation issues
        report: Dict[str, Any] = {}
        # Validate FIPS for coverage
        if dataset_choice == "Coverage":
            if {"state_fips", "county_fips"}.issubset(edited_df.columns):
                bad_fips = []
                # Build 5-digit fips to validate
                for s, c in zip(edited_df["state_fips"].astype(str), edited_df["county_fips"].astype(str)):
                    geoid = s.zfill(2) + c.zfill(3)
                    if not validate_fips(geoid):
                        bad_fips.append(geoid)
                if bad_fips:
                    report["invalid_fips"] = bad_fips[:5]
            # Validate distance band
            if "band_miles" in edited_df.columns:
                unmapped = []
                canonical_values = []
                for v in edited_df["band_miles"]:
                    canon = coerce_distance_band(v)
                    if canon is None:
                        unmapped.append(v)
                    canonical_values.append(canon)
                if unmapped:
                    report["invalid_band_miles"] = list(set(unmapped))
                edited_df["band_miles"] = canonical_values
            # Validate lat/lon numeric
            for col in ["lat", "lon"]:
                if col in edited_df.columns:
                    _, n_nans = numeric_or_nan(edited_df[col])
                    if n_nans > 0:
                        report[f"non_numeric_{col}"] = n_nans
        # Show validation report in debug
        show_validation_report(report, st)
        if report:
            st.error("Validation failed; please fix the issues above and try again.")
        else:
            # Proceed to create PR if secrets available
            if missing_secrets:
                st.warning(
                    "Cannot create pull request because required secrets are missing: "
                    f"{', '.join(missing_secrets)}"
                )
            else:
                try:
                    repo_full_name: str = secrets["github_repo"]
                    token: str = secrets["github_token"]
                    base_branch: str = secrets["github_default_branch"]
                    # Create a new branch name
                    branch_name = f"data-edit-{dataset_choice.lower()}-{pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S')}"
                    # Create branch
                    create_branch(repo_full_name, base_branch, branch_name, token)
                    # Prepare file content
                    csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
                    # Commit file to new branch
                    commit_file(
                        repo_full_name,
                        branch_name,
                        str(file_path),
                        csv_bytes,
                        f"feat(data): update {file_name} via app",
                        token,
                    )
                    # Build changelog as JSON summary
                    changelog = {
                        "rows_added": int(len(edited_df) - len(orig_df)),
                        "rows_deleted": int(len(orig_df) - len(edited_df)),
                        "rows_modified": int(len(diff_df)) if not diff_df.empty else 0,
                    }
                    body = "Automated data update from Streamlit app.\n\n" + json.dumps(changelog, indent=2)
                    pr_url = open_pr(
                        repo_full_name,
                        branch_name,
                        base_branch,
                        f"feat(data): update {file_name} via app",
                        body,
                        token,
                    )
                    st.success(f"Pull request created: {pr_url}")
                except Exception as exc:
                    st.error(f"Failed to create pull request: {exc}")
