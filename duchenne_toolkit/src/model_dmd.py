"""Model county-level Duchenne muscular dystrophy counts.

This script reads the ACS county demographics and applies prevalence rates
defined in `config.py` to estimate the number of Duchenne/Becker (DBMD)
and Duchenne muscular dystrophy (DMD) cases among males aged 5–24.  It
produces low, mid and high estimates and writes a CSV to
`data_final/county_dmd_model.csv`.
"""

from __future__ import annotations

import pandas as pd

from .config import (
    DATA_FINAL,
    ACS_OUTPUT,
    DMD_MODEL_OUTPUT,
    DBMD_PREVALENCE_MID,
    DBMD_PREVALENCE_LOW,
    DBMD_PREVALENCE_HIGH,
    DMD_FRACTION_OF_DBMD,
    DMD_DIAGNOSED_PREVALENCE,
    RUN_DATE,
)
from .utils_io import read_csv, write_csv


def main():
    df_pop = read_csv(ACS_OUTPUT)
    # Compute total male population 5–24
    df_pop["male_5_24_total"] = df_pop[["male_5_9", "male_10_14", "male_15_19", "male_20_24"]].sum(axis=1)
    # DBMD counts using prevalence (cases per person) times population
    df_pop["dbmd_low"] = df_pop["male_5_24_total"] * DBMD_PREVALENCE_LOW
    df_pop["dbmd_mid"] = df_pop["male_5_24_total"] * DBMD_PREVALENCE_MID
    df_pop["dbmd_high"] = df_pop["male_5_24_total"] * DBMD_PREVALENCE_HIGH
    # Convert DBMD to DMD by applying fraction
    df_pop["dmd_from_dbmd_low"] = df_pop["dbmd_low"] * DMD_FRACTION_OF_DBMD
    df_pop["dmd_from_dbmd_mid"] = df_pop["dbmd_mid"] * DMD_FRACTION_OF_DBMD
    df_pop["dmd_from_dbmd_high"] = df_pop["dbmd_high"] * DMD_FRACTION_OF_DBMD
    # Diagnosed DMD counts using diagnosed prevalence (per 1 person) times population
    df_pop["dmd_diagnosed"] = df_pop["male_5_24_total"] * DMD_DIAGNOSED_PREVALENCE
    # Low estimate: minimum of dmd_from_dbmd_low and diagnosed
    df_pop["modeled_dmd_5_24_low"] = df_pop[["dmd_from_dbmd_low", "dmd_diagnosed"]].min(axis=1)
    # High estimate: maximum of dmd_from_dbmd_high and diagnosed
    df_pop["modeled_dmd_5_24_high"] = df_pop[["dmd_from_dbmd_high", "dmd_diagnosed"]].max(axis=1)
    # Mid estimate: mean of DBMD-derived mid and diagnosed DMD
    df_pop["modeled_dmd_5_24_mid"] = (df_pop["dmd_from_dbmd_mid"] + df_pop["dmd_diagnosed"]) / 2
    # Round to one decimal
    for col in ["modeled_dmd_5_24_low", "modeled_dmd_5_24_mid", "modeled_dmd_5_24_high"]:
        df_pop[col] = df_pop[col].round(1)
    # Add modeling notes
    df_pop["modeling_notes"] = (
        "DBMD prevalence 1.3–1.8 per 10k males 5–24 multiplied by 0.75 to approximate DMD; "
        "diagnosed DMD prevalence assumed 6 per 100k males 5–24; mid estimate is average"
    )
    df_pop["source_retrieved_date"] = RUN_DATE
    # Build final DataFrame
    df_final = df_pop[[
        "state_fips", "county_fips", "county_name",
        "male_5_9", "male_10_14", "male_15_19", "male_20_24",
        "modeled_dmd_5_24_low", "modeled_dmd_5_24_mid", "modeled_dmd_5_24_high",
        "modeling_notes", "source_retrieved_date",
    ]].copy()
    write_csv(DMD_MODEL_OUTPUT, df_final)
    print(f"Wrote DMD model to {DMD_MODEL_OUTPUT}")


if __name__ == "__main__":
    main()