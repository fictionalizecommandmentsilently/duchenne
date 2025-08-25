"""Fetch county demographic data for Duchenne modeling.

This script reads a locally cached population dataset containing
county‐level counts of total male population by single age bands.  The
dataset, ``countypopmonthasrh.csv``, is included in the project and
derives from the National Center for Health Statistics bridged race
population estimates.  It contains annual population estimates for
multiple reference years (``yearref``).  To approximate a 5‑year
estimate, we compute the mean of the ``tot_male`` counts across all
``yearref`` values for each county and age group.

Age group codes in the dataset correspond to five‑year bands:

* ``3`` → ages 5–9
* ``4`` → ages 10–14
* ``5`` → ages 15–19
* ``6`` → ages 20–24

The script aggregates the mean male counts for these groups and
produces a tidy CSV with FIPS codes, county name and the male
population in each band.  The output file is written to
``data_final/county_demographics_acs.csv`` (although it is not
strictly ACS data) for compatibility with downstream scripts.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from .config import DATA_FINAL, ACS_OUTPUT, RUN_DATE
from .utils_io import write_csv


def main() -> None:
    # Path to the bridged race population dataset shipped with the repo
    source_path = Path("countypopmonthasrh.csv")
    # Read only required columns to limit memory usage
    cols = [
        "state",
        "county",
        "stname",
        "ctyname",
        "agegrp",
        "yearref",
        "tot_male",
    ]
    df = pd.read_csv(source_path, usecols=cols)
    # Filter for age groups of interest (5–9, 10–14, 15–19, 20–24)
    age_map = {
        3: "male_5_9",
        4: "male_10_14",
        5: "male_15_19",
        6: "male_20_24",
    }
    df = df[df["agegrp"].isin(age_map.keys())].copy()
    # Compute mean male count across all yearref values for each county and agegrp
    grouped = (
        df.groupby(["state", "county", "stname", "ctyname", "agegrp"])["tot_male"]
        .mean()
        .reset_index()
    )
    # Pivot age groups to columns
    pivot = grouped.pivot_table(
        index=["state", "county", "stname", "ctyname"],
        columns="agegrp",
        values="tot_male",
    ).reset_index()
    # Rename columns based on mapping
    pivot = pivot.rename(columns=age_map)
    # Ensure FIPS codes are zero‑padded strings
    pivot["state_fips"] = pivot["state"].astype(str).str.zfill(2)
    pivot["county_fips"] = pivot["county"].astype(str).str.zfill(3)
    pivot["county_name"] = pivot["ctyname"].astype(str)
    # Select and order output columns
    out_cols = [
        "state_fips",
        "county_fips",
        "county_name",
        "male_5_9",
        "male_10_14",
        "male_15_19",
        "male_20_24",
    ]
    df_out = pivot[out_cols].copy()
    # Round male counts to nearest integer
    for col in ["male_5_9", "male_10_14", "male_15_19", "male_20_24"]:
        df_out[col] = df_out[col].round().astype(int)
    df_out["source_retrieved_date"] = RUN_DATE
    write_csv(ACS_OUTPUT, df_out)
    print(f"Wrote demographics file to {ACS_OUTPUT}")


if __name__ == "__main__":
    main()