"""Merge a fresh pull into an existing series CSV (same series over time).

Rules:
  - new dates            -> appended
  - date in both, value changed (a revision) -> new value overwrites old,
                            and the change is logged
  - date in both, value identical            -> left alone

Every revision is recorded in data/_changes/<series>.csv as an audit trail:
    date, old_value, new_value, pulled_at

Comparison treats NaN==NaN as equal (a still-missing value is not a change) and
rounds to a tolerance so floating-point noise isn't logged as a revision.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

CHANGES_DIR = config.DATA_DIR / "_changes"
TOL = 1e-9  # values within this are considered equal


def _values_differ(old: float, new: float) -> bool:
    old_na, new_na = pd.isna(old), pd.isna(new)
    if old_na and new_na:
        return False
    if old_na or new_na:
        return True
    return abs(float(old) - float(new)) > TOL


def merge(name: str, fresh: pd.DataFrame, existing_path: Path) -> dict:
    """Merge `fresh` into the CSV at existing_path. Returns a summary dict.

    Both frames use the canonical schema [date, series_id, value].
    """
    existing = pd.read_csv(existing_path, parse_dates=["date"])

    # Collapse any duplicate dates (keep the last occurrence) so each date maps
    # to a single value. Duplicates arise from a manual merge, or from a KOSIS
    # table that returns multiple classification rows under one date — the
    # latter should really be split into one series per category, not merged
    # into a single file. `dup_*` is reported so you can spot that case.
    dup_existing = int(existing["date"].duplicated().sum())
    dup_fresh = int(fresh["date"].duplicated().sum())
    existing = existing.drop_duplicates(subset="date", keep="last")
    fresh = fresh.drop_duplicates(subset="date", keep="last")

    old = existing.set_index("date")["value"]
    new = fresh.set_index("date")["value"]

    added_dates = new.index.difference(old.index)
    common_dates = new.index.intersection(old.index)

    # find revisions among the common dates
    revisions = []
    for d in common_dates:
        ov, nv = old.loc[d], new.loc[d]
        if _values_differ(ov, nv):
            revisions.append(
                {"date": d, "old_value": ov, "new_value": nv}
            )

    # build merged series: start from old, overwrite with all new values
    merged = old.copy()
    for d in new.index:
        merged.loc[d] = new.loc[d]
    merged = merged.sort_index()

    out = (
        merged.reset_index()
        .assign(series_id=name)[["date", "series_id", "value"]]
    )
    out.to_csv(existing_path, index=False, encoding="utf-8-sig")

    # log revisions
    if revisions:
        CHANGES_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        log = pd.DataFrame(revisions)
        log["pulled_at"] = stamp
        log_path = CHANGES_DIR / f"{name}.csv"
        header = not log_path.exists()
        log.to_csv(
            log_path, mode="a", header=header, index=False,
            encoding="utf-8-sig",
        )

    return {
        "added": len(added_dates),
        "added_dates": sorted(added_dates),
        "revised": len(revisions),
        "total": len(out),
        "revisions": revisions,
        "dup_existing": dup_existing,
        "dup_fresh": dup_fresh,
    }