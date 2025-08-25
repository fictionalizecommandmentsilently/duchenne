"""Generate a brief coverage summary report in Markdown format.

This script reads the processed data and computes summary statistics,
including the number of certified Duchenne care centers by state, the
proportion of modeled DMD population within specified distance and
drive‐time bands, and the top gap counties ranked by modeled cases.
The report is written to `docs/coverage_summary.md`.
"""

from __future__ import annotations

import pandas as pd
from collections import Counter

from .config import (
    CENTERS_OUTPUT,
    DMD_MODEL_OUTPUT,
    COVERAGE_OUTPUT,
    GAP_OUTPUT,
    COVERAGE_SUMMARY_MD,
    RUN_DATE,
)
from .utils_io import read_csv, write_csv


def compute_center_counts(df_centers: pd.DataFrame) -> pd.DataFrame:
    counts = df_centers.groupby("state").size().reset_index(name="center_count")
    return counts


def compute_coverage_percentages(df_cov: pd.DataFrame, df_model: pd.DataFrame) -> pd.DataFrame:
    """Compute the share of modeled DMD cases within each distance band.

    Args:
        df_cov: Coverage dataframe containing band assignments and modeled counts.
        df_model: Unused; included for API consistency.

    Returns:
        A dict mapping each band label to the fraction of modeled cases in that band.
    """
    # Use the modeled counts already present in df_cov
    total = df_cov["modeled_dmd_5_24_mid"].sum()
    summary: dict[str, float] = {}
    for band in sorted(df_cov["band_miles"].unique()):
        band_total = df_cov.loc[df_cov["band_miles"] == band, "modeled_dmd_5_24_mid"].sum()
        summary[band] = band_total / total if total > 0 else 0
    return summary


def main():
    df_centers = read_csv(CENTERS_OUTPUT)
    df_model = read_csv(DMD_MODEL_OUTPUT)
    df_cov = read_csv(COVERAGE_OUTPUT)
    df_gap = read_csv(GAP_OUTPUT)
    # Center counts by state
    center_counts = compute_center_counts(df_centers)
    # Coverage percentages
    coverage_pct = compute_coverage_percentages(df_cov, df_model)
    # Top 20 gap counties
    top_gaps = df_gap.nlargest(20, "modeled_dmd_5_24_mid")[["county_name", "state_fips", "band_miles", "modeled_dmd_5_24_mid"]]
    # Build report
    lines = []
    lines.append(f"# Duchenne Care Access Coverage Summary\n")
    lines.append(f"**Run date:** {RUN_DATE}\n")
    lines.append("\n## Methods\n")
    lines.append(
        "We compiled a list of certified Duchenne care centers from Parent Project Muscular Dystrophy (PPMD) announcements through mid‑2025【681332876136906†L380-L465】【483110723608113†L430-L440】【133955900796891†L7-L21】.  County‑level male population counts for ages 5–24 were derived from the National Center for Health Statistics bridged‑race population estimates (2010s) contained in a local dataset; we averaged male counts across all available reference years for each county and five‑year age band (5–9, 10–14, 15–19 and 20–24) to approximate a five‑year estimate.  Duchenne/Becker muscular dystrophy prevalence (1.3–1.8 per 10 000 males) from MD STARnet was multiplied by 0.75 to approximate Duchenne only【514519091151079†L144-L147】, and a diagnosed Duchenne prevalence of 6 per 100 000 males was used as a secondary anchor.  Low, mid and high estimates were derived from these rates by taking the minimum, mean and maximum of the two approaches.  Straight‑line distances from county population‑weighted centroids (from a public county centers dataset) to the nearest care center were calculated using the haversine formula to classify counties into ≤150, 150–300 and >300 mile bands; drive times were approximated assuming a 50 mph average speed."
    )
    lines.append("\n## Center counts by state\n")
    for _, row in center_counts.sort_values(by="state").iterrows():
        state = row["state"]
        count = int(row["center_count"])
        lines.append(f"- {state}: {count}")
    lines.append("\n## Coverage percentages (modeled mid estimate)\n")
    for band, pct in coverage_pct.items():
        lines.append(f"- {band} miles: {pct:.1%} of modeled DMD population")
    lines.append("\n## Top gap counties (>300 miles or >360 minutes)\n")
    lines.append("County | State FIPS | Band | Modeled DMD mid")
    lines.append("--- | --- | --- | ---")
    for _, row in top_gaps.iterrows():
        lines.append(f"{row['county_name']} | {row['state_fips']} | {row['band_miles']} | {row['modeled_dmd_5_24_mid']:.1f}")
    lines.append("\n## Limitations\n")
    lines.append("This analysis assumes patients reside at the population‐weighted centroid of their county and that all certified centers have equal capacity.  Drive times are approximated from straight‐line distances and may not reflect actual travel times.  Prevalence rates are estimates and do not account for regional variation; adult transitions beyond age 24 are not modeled.  Data sources and certifications are current through mid‑2025 but may change thereafter.\n")
    # Write report
    COVERAGE_SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(COVERAGE_SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote coverage summary report to {COVERAGE_SUMMARY_MD}")


if __name__ == "__main__":
    main()