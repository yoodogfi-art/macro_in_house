"""KOSIS import. Give it a KOSIS 'generated URL' and it pulls the data.

The key from .env (KOSIS_API_KEY) is always used; whatever apiKey is in the URL
is ignored, so a pasted URL's key is inert. Convention: put the literal text
KOSIS_API_KEY in the URL's apiKey slot as a readable placeholder — same name as
in .env. Also fixes KOSIS's generator quirks:
  - method=getList -> getData (getList only lists the catalog, not data)
  - strips stray whitespace in code fields (the URL '+' -> space bug)

Returns a clean DataFrame: [date, series_id, value].
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd
import requests

from . import config

URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


def _parse_prd(s) -> pd.Timestamp:
    s = str(s).strip()
    for fmt in ("%Y%m%d", "%Y%m", "%Y"):
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(s, errors="coerce")


def strip_key(url: str) -> str:
    """Return the URL with apiKey blanked — safe to save. Optional; the key in
    a URL is ignored at fetch time regardless."""
    p = urlparse(url)
    q = parse_qs(p.query, keep_blank_values=True)
    q["apiKey"] = [""]
    return urlunparse(p._replace(query=urlencode({k: v[0] for k, v in q.items()})))


def fetch(
    series_id: str,
    url: str,
    date_field: str = "PRD_DE",
    value_field: str = "DT",
    **overrides,
) -> pd.DataFrame:
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query,
                                      keep_blank_values=True).items()}
    # We control these regardless of what's in the URL.
    q.pop("apiKey", None)
    q["method"] = "getData"
    q["format"] = "json"
    q["jsonVD"] = "Y"
    q["apiKey"] = config.key("KOSIS_API_KEY")
    # Clean stray whitespace, drop empty params, apply any overrides.
    for k in list(q):
        if isinstance(q[k], str):
            q[k] = q[k].strip()
    q = {k: v for k, v in q.items() if v != "" or k in
         ("startPrdDe", "endPrdDe")}
    q.update(overrides)

    r = requests.get(URL, params=q, timeout=30)
    r.raise_for_status()
    try:
        rows = r.json()
    except ValueError:
        raise RuntimeError(
            f"KOSIS non-JSON for '{series_id}': {r.text[:200]}"
        )
    if isinstance(rows, dict):  # KOSIS errors come back as an object
        raise RuntimeError(f"KOSIS error for '{series_id}': {rows}")

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "series_id", "value"])

    missing = {date_field, value_field} - set(df.columns)
    if missing:
        raise RuntimeError(
            f"KOSIS '{series_id}': fields {missing} not in response "
            f"{list(df.columns)}. Set date_field/value_field to match."
        )

    out = pd.DataFrame(
        {
            "date": df[date_field].map(_parse_prd),
            "series_id": series_id,
            "value": pd.to_numeric(df[value_field], errors="coerce"),
        }
    )
    return out.sort_values("date").reset_index(drop=True)


# Candidate name fields KOSIS uses, in priority order. Whichever of these
# actually VARY within the response become the column-name components.
_NAME_FIELDS = ["ITM_NM", "C1_NM", "C2_NM", "C3_NM", "C4_NM"]


def _clean_col(s: str) -> str:
    """Make a category label safe/tidy for a column header."""
    return "_".join(str(s).strip().split())


def fetch_wide(
    series_id: str,
    url: str,
    date_field: str = "PRD_DE",
    value_field: str = "DT",
    **overrides,
):
    """Fetch a multi-category KOSIS table as a WIDE frame: date first, then one
    column per distinct variable (category combination).

    Auto-detects which of KOSIS's name fields (ITM_NM, C1_NM, ...) actually vary
    in the response and builds column names from exactly those, so a table split
    by item gets item-named columns, and a table split by item x sector gets
    'item__sector' columns. Returns (wide_df, info) where info records which
    fields were used and the resulting column names.
    """
    long = _fetch_raw(series_id, url, date_field, value_field, **overrides)
    df = long["df"]
    if df.empty:
        return pd.DataFrame(columns=["date"]), {"varying": [], "columns": []}

    df = df.copy()
    df["date"] = df[date_field].map(_parse_prd)
    df["value"] = pd.to_numeric(df[value_field], errors="coerce")

    # Which name fields are present AND take more than one distinct value?
    present = [f for f in _NAME_FIELDS if f in df.columns]
    varying = [f for f in present if df[f].nunique(dropna=True) > 1]

    # If nothing varies, it's really a single series — one column under the name.
    if not varying:
        wide = (
            df[["date", "value"]]
            .drop_duplicates("date", keep="last")
            .set_index("date")
            .rename(columns={"value": series_id})
            .sort_index()
        )
        return wide.reset_index(), {"varying": [], "columns": [series_id]}

    # Build a column label per row from the varying fields.
    df["_col"] = df[varying].apply(
        lambda r: "__".join(_clean_col(r[f]) for f in varying), axis=1
    )

    wide = (
        df.pivot_table(
            index="date", columns="_col", values="value", aggfunc="last"
        )
        .sort_index()
    )
    wide.columns.name = None
    info = {"varying": varying, "columns": list(wide.columns)}
    return wide.reset_index(), info


def _fetch_raw(series_id, url, date_field, value_field, **overrides) -> dict:
    """Shared request + parse, returning the raw KOSIS rows as a DataFrame.
    Used by fetch_wide; keeps all category fields intact."""
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query,
                                      keep_blank_values=True).items()}
    q.pop("apiKey", None)
    q["method"] = "getData"
    q["format"] = "json"
    q["jsonVD"] = "Y"
    q["apiKey"] = config.key("KOSIS_API_KEY")
    for k in list(q):
        if isinstance(q[k], str):
            q[k] = q[k].strip()
    q = {k: v for k, v in q.items() if v != "" or k in
         ("startPrdDe", "endPrdDe")}
    q.update(overrides)

    r = requests.get(URL, params=q, timeout=30)
    r.raise_for_status()
    try:
        rows = r.json()
    except ValueError:
        raise RuntimeError(f"KOSIS non-JSON for '{series_id}': {r.text[:200]}")
    if isinstance(rows, dict):
        raise RuntimeError(f"KOSIS error for '{series_id}': {rows}")

    df = pd.DataFrame(rows)
    if not df.empty:
        missing = {date_field, value_field} - set(df.columns)
        if missing:
            raise RuntimeError(
                f"KOSIS '{series_id}': fields {missing} not in response "
                f"{list(df.columns)}. Set date_field/value_field to match."
            )
    return {"df": df}