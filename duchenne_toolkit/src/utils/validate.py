"""
Validation helpers used by the Streamlit app.
Keeps all Streamlit UI calls optional so these utilities are import-safe everywhere.
"""

from __future__ import annotations
from typing import Dict, Any, Optional

import pandas as pd

def validate_fips(val: Any) -> bool:
    """
    Returns True if `val` looks like a valid 2- or 3- or 5-digit FIPS piece.
    We accept strings and numbers; pads to 5 only when both pieces are combined elsewhere.
    """
    if val is None:
        return False
    s = str(val).strip()
    if not s.isdigit():
        return False
    # accept 2 (state), 3 (county), or 5 (combined geoid)
    return len(s) in (2, 3, 5)

def coerce_distance_band(x: Any) -> Optional[str]:
    """
    Normalizes the distance-band column to one of: '<=150', '150_300', '>300'.
    Returns None if it cannot be interpreted.
    """
    if x is None:
        return None
    s = str(x).strip().lower().replace(" ", "").replace("-", "_")
    candidates = {
        "<=150": {"<=150", "<=150mi", "le150", "0_150", "0to150", "0_150mi", "under150"},
        "150_300": {"150_300", "150to300", "150_300mi", "150-300"},
        ">300": {">300", ">300mi", "over300", "gt300"},
    }
    for norm, alts in candidates.items():
        if s == norm or s in alts:
            return norm
    # handle numeric buckets
    try:
        v = float(s.replace("mi", ""))
        if v <= 150:
            return "<=150"
        if 150 < v <= 300:
            return "150_300"
        if v > 300:
            return ">300"
    except Exception:
        pass
    return None

def show_validation_report(report: Dict[str, Any], st=None) -> None:
    """
    If a report dict has entries, print a compact summary in Streamlit if available.
    Keeps Streamlit import out of the module to avoid hard dependency.
    """
    if not report:
        return
    lines = []
    for k, v in report.items():
        if v:
            lines.append(f"- {k.replace('_', ' ')}: {v}")
    msg = "Validation issues detected:\n" + ("\n".join(lines) if lines else "(none)")
    if st is not None:
        st.warning(msg)
    else:
        print(msg)
