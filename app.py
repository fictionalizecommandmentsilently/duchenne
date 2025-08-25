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
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from duchenne_toolkit.src.utils.github import (
    create_branch,
    commit_file,
    open_pr,
)
from duchenne_toolkit.src.utils.validate import (
    validate_fips,
    coerce_distance_band,
    show_validation_report,
)
from duchenne_toolkit.src.data.loaders import load_coverage

# Configure the page
st.set_page_config(page_title="DMD Access Coverage", layout="wide")

# Directory for final data
DATA_DIR = Path("duchenne_toolkit/data_final")

# ---- Secrets (GitHub integration) --------------------------------------------

secrets = st.secrets if hasattr(st, "secrets") else {}
repo_full_name = None
base_branch = None
token = secrets.get("github_token")

if "github_repo" in secrets:
    repo_full_name = secrets.get("github_repo")
    base_branch = secrets.get("github_default_branch") or secrets.get("github_branch")
else:
    owner = secrets.get("github_repo_owner")
    name = secrets.get("github_repo_name")
    if owner and name:
        repo_full_name = f"{owner}/{name}"
    base_branch = secrets.get("github_branch") or secrets.get("github_default_branch")

required = {"repo": bool(repo_full_name), "token": bool(token), "branch": bool(base_branch)}
missing_secrets = []
if not required["repo"]:
    missing_secrets.append("github_repo (or github_repo_owner + github_repo_name)")
if not required["token"]:
    missing_secrets.append("github_token")
if not required["branch"]:
    missing_secrets.append("github_default_branch (or github_branch)")

# ---- Data loading ------------------------------------------------------------

with st.spinner("Loading data…"):
    try:
        centers = pd.read_csv(DATA_DIR / "centers_cdcc_us.csv", dtype={"state": str}, low_memory=False)
        cov, load_debug = load_coverage()
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
        centers, cov = pd.DataFrame(), pd.DataFrame()
        load_debug: Dict[str, Any] = {}

has_lat_lon: bool = {"lat", "lon"}.issubset(cov.columns)

# Sidebar filters
states = sorted(cov["state_fips"].dropna().unique()) if "state_fips" in cov.columns else []
if "state_pick" not in st.session_state:
    st.session_state["state_pick"] = states or []
if "band_pick" not in st.session_state:
    st.session_state["band_pick"] = ["<=150", "150_300", ">300"]
if "min_cases" not in st.session_state:
    st.session_state["min_cases"] = 0.0

with st.sidebar:
    st.header("Filters")
    st.session_state["state_pick"] = st.multiselect(
        "States (FIPS)", options=states, default=st.session_state["state_pick"]
    ) if states else []
    st.session_state["band_pick"] = st.multiselect(
        "Distance band",
        options=["<=150", "150_300", ">300"],
        default=st.session_state["band_pick"],
    )
    st.session_state["min_cases"] = st.number_input(
        "Min modeled cases (5–24)", min_value=0.0, value=float(st.session_state["min_cases"])
    )

if not cov.empty:
    mask = pd.Series(True, index=cov.index)
    if st.session_state["state_pick"]:
        mask &= cov["state_fips"].isin(st.session_state["state_pick"])
    if st.session_state["band_pick"]:
        mask &= cov["band_miles"].isin(st.session_state["band_pick"])
    if "modeled_dmd_5_24_mid" in cov.columns:
        mask &= pd.to_numeric(cov["modeled_dmd_5_24_mid"], errors="coerce").fillna(0) >= st.session_state["min_cases"]
    cov_f = cov.loc[mask].copy()
else:
    cov_f = cov

# ---- Layout ------------------------------------------------------------------

st.title("DMD Access Coverage")

overview_tab, map_tab, tables_tab, about_tab, edit_tab = st.tabs(
    ["Overview", "Map", "Tables", "About", "Edit Data"]
)

# Overview
with overview_tab:
    st.subheader("Quick stats")
    if not cov.empty:
        total_counties = len(cov)
        with_coords = int((cov[["lat", "lon"]].notna().all(axis=1)).sum()) if {"lat", "lon"}.issubset(cov.columns) else 0
        st.metric("Counties in model", total_counties)
        st.metric("Counties with coordinates", with_coords)
        st.caption(f"Derived at: {load_debug.get('derived_path', 'n/a')}")
    else:
        st.info("No coverage data loaded.")

# Map
with map_tab:
    if not has_lat_lon:
        st.warning(
            "Coverage lacks coordinates. Check `county_coverage.csv` or the derived file in `duchenne_toolkit/data/derived`."
        )
    else:
        map_df = cov_f.dropna(subset=["lat", "lon"]).copy()
        color_map = {"<=150": [34, 197, 94], "150_300": [245, 158, 11], ">300": [239, 68, 68]}
        if "band_miles" in map_df.columns:
            map_df["color"] = map_df["band_miles"].map(color_map).fillna([120, 144, 156])
        else:
            map_df["color"] = [120, 144, 156]
        if "modeled_dmd_5_24_mid" in map_df.columns:
            map_df["radius"] = pd.to_numeric(map_df["modeled_dmd_5_24_mid"], errors="coerce").fillna(0).clip(lower=0) * 1500 + 5000
        else:
            map_df["radius"] = 5000

        county_layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["lon", "lat"],
            get_radius="radius",
            get_fill_color="color",
            pickable=True,
        )
        centers_vis = centers.dropna(subset=["lat", "lon"]) if {"lat", "lon"}.issubset(centers.columns) else pd.DataFrame()
        center_layer = (
            pdk.Layer(
                "ScatterplotLayer",
                data=centers_vis,
                get_position=["lon", "lat"],
                get_radius=6000,
                get_fill_color=[30, 64, 175],
                pickable=True,
            )
            if not centers_vis.empty
            else None
        )
        layers = [county_layer] + ([center_layer] if center_layer is not None else [])
        tooltip_txt = (
            "County: {county_name}\\nBand: {band_miles}\\nCases (5–24 mid): {modeled_dmd_5_24_mid}\\nNearest center: {nearest_center_name}\\nDistance (mi): {great_circle_mi}"
            if "county_name" in map_df.columns
            else "DMD coverage"
        )
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
        st.markdown(
            """
            **Legend**  
            • ≤150 miles (green)  
            • 150–300 miles (orange)  
            • >300 miles (red)
            """
        )

# Tables
with tables_tab:
    st.subheader("Coverage table")
    if cov_f.empty:
        st.info("No rows to display.")
    else:
        st.dataframe(cov_f, use_container_width=True)
    st.subheader("Centers table")
    if centers.empty:
        st.info("No centers loaded.")
    else:
        st.dataframe(centers, use_container_width=True)

# About
with about_tab:
    st.markdown(
        """
        **DMD Access Coverage** — internal toolkit to compare where certified Duchenne centers are
        versus modeled patient counts at the US county level.  Use the **Edit Data** tab to update
        CSVs and optionally send a pull request if GitHub secrets are configured in Streamlit.
        """
    )

# Edit Data
with edit_tab:
    st.subheader("Edit CSVs")
    file_options = {
        "county_coverage.csv": DATA_DIR / "county_coverage.csv",
        "centers_cdcc_us.csv": DATA_DIR / "centers_cdcc_us.csv",
    }
    file_name = st.selectbox("Choose a file to edit", list(file_options))
    path = file_options[file_name]
    if not path.exists():
        st.error(f"Missing file: {path}")
    else:
        df = pd.read_csv(path)
        st.caption("Tip: double-click cells to edit; use the download below to save a copy.")
        edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")

        # Validation
        report: Dict[str, Any] = {}
        if "state_fips" in edited.columns:
            bad = edited["state_fips"].astype(str).apply(validate_fips)
            if (~bad).any():
                report["invalid_state_fips"] = int((~bad).sum())
        if "county_fips" in edited.columns:
            bad = edited["county_fips"].astype(str).apply(validate_fips)
            if (~bad).any():
                report["invalid_county_fips"] = int((~bad).sum())
        if "band_miles" in edited.columns:
            edited["band_miles_norm"] = edited["band_miles"].apply(coerce_distance_band)
            if edited["band_miles_norm"].isna().any():
                report["invalid_band_miles"] = int(edited["band_miles_norm"].isna().sum())
            else:
                edited["band_miles"] = edited["band_miles_norm"]
            edited = edited.drop(columns=["band_miles_norm"], errors="ignore")
        for col in ["modeled_dmd_5_24_mid", "lat", "lon", "great_circle_mi"]:
            if col in edited.columns:
                coerced = pd.to_numeric(edited[col], errors="coerce")
                n_nans = int(coerced.isna().sum()) - int(edited[col].isna().sum())
                edited[col] = coerced
                if n_nans > 0:
                    report[f"non_numeric_{col}"] = n_nans

        show_validation_report(report, st)

        if report:
            st.error("Validation failed; please fix the issues above and try again.")
        else:
            if missing_secrets:
                st.warning(
                    "Cannot create pull request because required secrets are missing: "
                    f"{', '.join(missing_secrets)}"
                )
            else:
                try:
                    repo_full_name_str: str = repo_full_name
                    branch_name = f"data-update/{file_name.replace('.csv','')}-{pd.Timestamp.utcnow().strftime('%Y%m%d-%H%M%S')}"
                    base = base_branch
                    create_branch(repo_full_name_str, base, branch_name, token)
                    csv_bytes = edited.to_csv(index=False).encode("utf-8")
                    commit_file(
                        repo_full_name_str,
                        branch_name,
                        f"duchenne_toolkit/data_final/{file_name}",
                        csv_bytes,
                        f"chore(data): update {file_name} via Streamlit",
                        token,
                    )
                    original = df.copy()
                    diff_df = edited.merge(original, how="outer", indicator=True)
                    st.expander("Preview: changed rows").dataframe(diff_df[diff_df["_merge"] != "both"], use_container_width=True)
                    changelog = {
                        "file": file_name,
                        "rows_before": int(len(original)),
                        "rows_after": int(len(edited)),
                        "rows_modified": int(len(diff_df)) if not diff_df.empty else 0,
                    }
                    body = "Automated data update from Streamlit app.\\n\\n" + json.dumps(changelog, indent=2)
                    pr_url = open_pr(
                        repo_full_name_str,
                        branch_name,
                        base,
                        f"feat(data): update {file_name} via app",
                        body,
                        token,
                    )
                    st.success(f"Pull request created: {pr_url}")
                except Exception as exc:
                    st.error(f"Failed to create pull request: {exc}")
