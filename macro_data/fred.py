"""FRED import. Pull any series by ID from fred/series/observations.

Returns a clean DataFrame: [date, series_id, value], dates typed, FRED's "."
missing marker coerced to NaN, sorted ascending.
"""
from __future__ import annotations

import pandas as pd
import requests

from . import config

URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch(
    series_id: str,
    start: str | None = None,
    end: str | None = None,
    frequency: str | None = None,
    units: str | None = None,
) -> pd.DataFrame:
    params = {
        "series_id": series_id,
        "api_key": config.key("FRED_API_KEY"),
        "file_type": "json",
    }
    if start:
        params["observation_start"] = start
    if end:
        params["observation_end"] = end
    if frequency:
        params["frequency"] = frequency
    if units:
        params["units"] = units

    r = requests.get(URL, params=params, timeout=30)
    if r.status_code != 200:
        try:
            msg = r.json().get("error_message", r.text)
        except ValueError:
            msg = r.text
        raise RuntimeError(f"FRED error for '{series_id}': {msg}")

    obs = r.json().get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        return pd.DataFrame(columns=["date", "series_id", "value"])

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "series_id": series_id,
            "value": pd.to_numeric(df["value"], errors="coerce"),
        }
    )
    return out.sort_values("date").reset_index(drop=True)