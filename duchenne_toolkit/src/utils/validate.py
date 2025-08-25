from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def validate_fips(val: Any) -> bool:
    """
    True if val looks like a valid 2-, 3-, or 5-digit FIPS/geoid piece.
    """
    if val is None:
        return False
    s = str(val).strip()
    if not s.isdigit():
        return False
    return len(s) in (2, 3, 5)


def coerce_distance_band(x: Any) -> Optional[str]:
    """
    Normalizes to one of: '<=150', '150_300', '>300'. Returns None if unknown.
    """
    if x is None:
        return None
    s = (
        str(x)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "_")
    )

    mapping = {
        "<=150": {"<=150", "<=150mi", "le150", "0_150", "0to150", "0_150mi", "under150"},
        "150_300": {"150_300", "150to300", "150_300mi", "150-300"},
        ">300": {">300", ">300mi", "over300", "gt300"},
    }
    for norm, alts in mapping.items():
        if s == norm or s in alts:
            return norm

    try:
        v = float(s.replace("mi", ""))
        if v <= 150:
            return "<=150"
        if v <= 300:
            return "150_300"
        return ">300"
    except Exception:
        return None


def show_validation_report(report: Dict[str, Any], st=None) -> None:
    """
    Print a compact summary in Streamlit if provided, else stdout.
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
