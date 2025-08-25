"""
Validation utilities for the Duchenne access toolkit.

These helper functions encapsulate common data quality checks used by the
Streamlit editing interface.  Centralising validation logic in this
module makes it easier to maintain consistent rules across different
components of the app.

Functions
---------
validate_fips(fips: str) -> bool
    Return ``True`` if the supplied string is a 5‑digit FIPS code.

coerce_distance_band(val: str) -> str | None
    Normalise a free‑form distance band string to one of the three
    canonical values ``{"<=150", "150_300", ">300"}``, or return
    ``None`` if it cannot be matched.

numeric_or_nan(series: pandas.Series) -> Tuple[pandas.Series, int]
    Coerce a pandas Series to numeric, returning the coerced series and
    the count of values that were converted to NaN.

show_validation_report(report: dict, st) -> None
    Render a validation report into the Streamlit app using the passed
    ``st`` module.  Each key/value pair in ``report`` is displayed as
    a separate line in an expander.
"""

from __future__ import annotations

import pandas as pd
from typing import Tuple, Any, Optional

def validate_fips(fips: Any) -> bool:
    """Check that a FIPS code is exactly five digits.

    Parameters
    ----------
    fips: Any
        The value to validate.  It will be converted to a string if
        possible.

    Returns
    -------
    bool
        ``True`` if ``fips`` is a five‑character string of digits,
        otherwise ``False``.
    """
    try:
        s = str(fips)
    except Exception:
        return False
    return len(s) == 5 and s.isdigit()

def coerce_distance_band(val: Any) -> Optional[str]:
    """Normalise distance band values to canonical categories.

    Accept a variety of user inputs (e.g. ``"<=150"``, ``"≤150"``,
    ``"150-300"``, ``">=300"``, etc.) and map them onto one of
    ``{"<=150", "150_300", ">300"}``.  Returns ``None`` if the
    value cannot be interpreted.
    """
    if val is None:
        return None
    s = str(val).strip().replace("–", "-")  # normalise en dash
    # Remove any comparison operators and whitespace
    s = s.replace("<=", "<=").replace(">=", ">=").replace("≥", ">=")
    lookup = {
        "<=150": "<=150",
        "<= 150": "<=150",
        "150-300": "150_300",
        "150 - 300": "150_300",
        "150_300": "150_300",
        ">300": ">300",
        "> 300": ">300",
        "300+": ">300",
    }
    # Exact match first
    if s in lookup:
        return lookup[s]
    # Handle cases like "<=150 miles"
    for key, canonical in lookup.items():
        if s.startswith(key):
            return canonical
    return None

def numeric_or_nan(series: pd.Series) -> Tuple[pd.Series, int]:
    """Coerce a Series to float, returning NaN for non‑parsable values.

    Parameters
    ----------
    series: pandas.Series
        A series to convert to numeric.  Missing or invalid entries
        become ``NaN``.

    Returns
    -------
    (Series, int):
        The converted Series and the number of NaN entries that
        resulted from coercion.
    """
    coerced = pd.to_numeric(series, errors="coerce")
    return coerced, int(coerced.isna().sum())

def show_validation_report(report: dict, st: Any) -> None:
    """Render a validation report dictionary in Streamlit.

    Displays each key/value pair in ``report`` inside an expander for
    easy inspection.  If ``report`` is empty, a friendly message is
    displayed instead.

    Parameters
    ----------
    report: dict
        The report to display.  Keys and values should be strings or
        values convertible to strings.
    st: module
        The Streamlit module passed from the calling code.  Using an
        explicit argument avoids a hard dependency on Streamlit in this
        module, making the functions easier to test.
    """
    if not report:
        st.info("No validation issues found.")
        return
    with st.expander("Validation Report"):
        for key, value in report.items():
            st.write(f"{key}: {value}")