#!/usr/bin/env python3
"""Pull every series in series.yaml and save one CSV per series.

    python pull.py                 # pull all series
    python pull.py us_unemployment # pull just one (or several) by name

Existing-file behaviour: the fresh pull is MERGED into the saved CSV — new
dates appended, revised values overwritten (and logged to
data/_changes/<name>.csv), unchanged values left alone.

A KOSIS series marked `wide: true` in series.yaml is saved WIDE: date first,
then one column per category (auto-detected from KOSIS's name fields).
"""
from __future__ import annotations

import sys

import yaml

from macro_data import config, fred, kosis, merge, merge_wide

SERIES_FILE = config.ROOT / "series.yaml"


def load_series() -> dict:
    if not SERIES_FILE.exists():
        raise FileNotFoundError(f"No series file at {SERIES_FILE}")
    return yaml.safe_load(SERIES_FILE.read_text(encoding="utf-8")) or {}


def _handle_long(name: str, spec: dict):
    if "fred" in spec:
        f = spec["fred"]
        df = fred.fetch(
            f["id"], start=f.get("start"), end=f.get("end"),
            frequency=f.get("frequency"), units=f.get("units"),
        )
    else:
        k = spec["kosis"]
        df = kosis.fetch(name, k["url"], **k.get("overrides", {}))
    if df.empty:
        print(f"[warn] {name}: no data returned")
        return
    df = df.copy()
    df["series_id"] = name

    out = config.DATA_DIR / f"{name}.csv"
    if not out.exists():
        df.to_csv(out, index=False, encoding="utf-8-sig")
        span = f"{df['date'].min().date()} -> {df['date'].max().date()}"
        print(f"[new]  {name}: {len(df)} rows, {span} -> {out.name}")
        return

    s = merge.merge(name, df, out)
    msg = (f"[merge] {name}: +{s['added']} new, {s['revised']} revised, "
           f"{s['total']} total -> {out.name}")
    if s["revised"]:
        msg += f"  (logged to _changes/{name}.csv)"
    print(msg)
    if s["dup_fresh"] or s["dup_existing"]:
        print(f"          [!] duplicate dates collapsed "
              f"(fresh={s['dup_fresh']}, existing={s['dup_existing']}). If this "
              f"series has multiple categories per date, mark it wide: true.")
    if s["added_dates"]:
        shown = ", ".join(d.date().isoformat() for d in s["added_dates"][:8])
        if s["added"] > 8:
            shown += f", ... (+{s['added'] - 8} more)"
        print(f"          new:     {shown}")
    for rev in s["revisions"][:5]:
        print(f"          revised: {rev['date'].date()}: "
              f"{rev['old_value']} -> {rev['new_value']}")
    if s["revised"] > 5:
        print(f"          ... and {s['revised'] - 5} more")


def _handle_wide(name: str, spec: dict):
    k = spec["kosis"]
    wide, info = kosis.fetch_wide(name, k["url"], **k.get("overrides", {}))
    if wide.empty or wide.shape[1] <= 1:
        print(f"[warn] {name}: no data returned")
        return

    ncols = wide.shape[1] - 1
    out = config.DATA_DIR / f"{name}.csv"
    if not out.exists():
        wide.to_csv(out, index=False, encoding="utf-8-sig")
        span = f"{wide['date'].min().date()} -> {wide['date'].max().date()}"
        print(f"[new]  {name}: {len(wide)} rows x {ncols} cols, {span} "
              f"-> {out.name}")
        print(f"          split by: {info['varying'] or 'single column'}")
        print(f"          columns:  {_preview(info['columns'])}")
        return

    s = merge_wide.merge_wide(name, wide, out)
    msg = (f"[merge] {name}: +{s['added']} new dates, {s['revised']} revised "
           f"cells, {s['total_rows']}x{s['total_cols']} -> {out.name}")
    if s["revised"]:
        msg += f"  (logged to _changes/{name}.csv)"
    print(msg)
    if s["new_cols"]:
        print(f"          new columns: {_preview(s['new_cols'])}")
    if s["added_dates"]:
        shown = ", ".join(d.date().isoformat() for d in s["added_dates"][:8])
        if s["added"] > 8:
            shown += f", ... (+{s['added'] - 8} more)"
        print(f"          new dates:   {shown}")
    for rev in s["revisions"][:5]:
        print(f"          revised: {rev['date'].date()} [{rev['column']}]: "
              f"{rev['old_value']} -> {rev['new_value']}")
    if s["revised"] > 5:
        print(f"          ... and {s['revised'] - 5} more")


def _preview(cols, n=6):
    cols = list(cols)
    head = ", ".join(cols[:n])
    return head + (f", ... (+{len(cols) - n} more)" if len(cols) > n else "")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    series = load_series()
    names = args or list(series)

    for name in names:
        if name not in series:
            print(f"[skip] '{name}' not in series.yaml")
            continue
        spec = series[name]
        try:
            is_wide = "kosis" in spec and spec["kosis"].get("wide", False)
            if is_wide:
                _handle_wide(name, spec)
            elif "fred" in spec or "kosis" in spec:
                _handle_long(name, spec)
            else:
                print(f"[skip] '{name}': needs a 'fred' or 'kosis' block.")
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()