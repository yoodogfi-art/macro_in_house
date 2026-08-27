"""Merge a fresh WIDE pull (date + many category columns) into an existing wide
CSV. Same philosophy as merge.py but per-column:

  - new dates            -> appended (all columns)
  - existing date, a cell's value changed -> overwritten, and logged
  - new columns          -> added (older dates get NaN for them)

Revisions are logged to data/_changes/<name>.csv as:
    date, column, old_value, new_value, pulled_at
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from . import config

CHANGES_DIR = config.DATA_DIR / "_changes"
TOL = 1e-9


def _differ(old, new) -> bool:
    o_na, n_na = pd.isna(old), pd.isna(new)
    if o_na and n_na:
        return False
    if o_na or n_na:
        return True
    return abs(float(old) - float(new)) > TOL


def merge_wide(name: str, fresh: pd.DataFrame, existing_path: Path) -> dict:
    existing = pd.read_csv(existing_path, parse_dates=["date"])

    old = existing.set_index("date").sort_index()
    new = fresh.set_index("date").sort_index()

    added_dates = new.index.difference(old.index)
    new_cols = [c for c in new.columns if c not in old.columns]

    # Detect per-cell revisions on the overlap.
    revisions = []
    common_dates = new.index.intersection(old.index)
    common_cols = [c for c in new.columns if c in old.columns]
    for d in common_dates:
        for c in common_cols:
            ov, nv = old.at[d, c], new.at[d, c]
            if _differ(ov, nv):
                revisions.append(
                    {"date": d, "column": c, "old_value": ov, "new_value": nv}
                )

    # Combine: reindex both to the union of dates+cols, then overwrite old with
    # new wherever new has a (non-missing) value.
    all_cols = list(dict.fromkeys(list(old.columns) + list(new.columns)))
    all_dates = old.index.union(new.index)
    merged = old.reindex(index=all_dates, columns=all_cols)
    new_full = new.reindex(index=all_dates, columns=all_cols)
    merged = new_full.combine_first(merged)  # new wins where present
    merged = merged.sort_index()

    out = merged.reset_index().rename(columns={"index": "date"})
    out.to_csv(existing_path, index=False, encoding="utf-8-sig")

    if revisions:
        CHANGES_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        log = pd.DataFrame(revisions)
        log["pulled_at"] = stamp
        log_path = CHANGES_DIR / f"{name}.csv"
        log.to_csv(log_path, mode="a", header=not log_path.exists(),
                   index=False, encoding="utf-8-sig")

    return {
        "added": len(added_dates),
        "added_dates": sorted(added_dates),
        "new_cols": new_cols,
        "revised": len(revisions),
        "revisions": revisions,
        "total_rows": len(out),
        "total_cols": len(out.columns) - 1,  # minus date
    }