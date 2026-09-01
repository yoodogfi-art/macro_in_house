#!/usr/bin/env python3
"""Backfill KOSIS history and refresh every series in one run.

    python backfill.py                       # refresh EVERYTHING (one click)
    python backfill.py kr_export_volume_index    # just one series
    python backfill.py kr_export_price_index --start 200101 --end 202607
    python backfill.py kr_export_volume_index --months 12   # smaller chunks

With NO series name, this refreshes all of series.yaml: KOSIS series are pulled
in fixed-size chunks (their per-request range is limited) and FRED series are
pulled normally (no such limit). Everything is MERGED into the existing CSVs —
new dates appended, revised values overwritten, gaps (e.g. a missing latest
month) filled — nothing is wiped. If any series fails, the run stops there and
names it.

KOSIS chunking uses the same fetch + merge logic as pull.py, so the result is
identical to one big pull. After history is loaded once, routine updates can go
through `python pull.py`; running this again is always safe (it just re-merges).
"""
from __future__ import annotations

import argparse
import time
import datetime as dt

from macro_data import config, kosis, merge, merge_wide
from pull import load_series, _handle_long


def _add_months(ym: int, n: int) -> int:
    """ym is YYYYMM as int; return YYYYMM n months later."""
    y, m = divmod(ym, 100)
    total = y * 12 + (m - 1) + n
    ny, nm = divmod(total, 12)
    return ny * 100 + (nm + 1)


def _month_iter(start: str, end: str, months: int):
    """Yield (startPrdDe, endPrdDe) chunk bounds as YYYYMM strings, inclusive,
    each spanning at most `months` months."""
    cur = int(start)
    stop = int(end)
    while cur <= stop:
        chunk_end = min(_add_months(cur, months - 1), stop)
        yield f"{cur:06d}", f"{chunk_end:06d}"
        cur = _add_months(chunk_end, 1)


def backfill_kosis(name: str, spec: dict, start: str, end: str,
                   months: int, pause: float) -> int:
    """Chunked backfill of one KOSIS series. Returns dates loaded."""
    k = spec["kosis"]
    is_wide = k.get("wide", False)
    url = k["url"]
    out = config.DATA_DIR / f"{name}.csv"

    chunks = list(_month_iter(start, end, months))
    print(f"[kosis] {name}: {start} -> {end} in {len(chunks)} chunk(s) "
          f"of {months}m ({'wide' if is_wide else 'long'})")

    total_new = 0
    for i, (s, e) in enumerate(chunks, 1):
        if is_wide:
            wide, info = kosis.fetch_wide(name, url, startPrdDe=s, endPrdDe=e)
            if wide.empty or wide.shape[1] <= 1:
                print(f"    [{i}/{len(chunks)}] {s}-{e}: no data")
            else:
                if not out.exists():
                    wide.to_csv(out, index=False, encoding="utf-8-sig")
                    added = len(wide)
                else:
                    added = merge_wide.merge_wide(name, wide, out)["added"]
                total_new += added
                print(f"    [{i}/{len(chunks)}] {s}-{e}: "
                      f"+{added} dates, {wide.shape[1]-1} cols")
        else:
            df = kosis.fetch(name, url, startPrdDe=s, endPrdDe=e)
            if df.empty:
                print(f"    [{i}/{len(chunks)}] {s}-{e}: no data")
            else:
                df = df.copy()
                df["series_id"] = name
                if not out.exists():
                    df.to_csv(out, index=False, encoding="utf-8-sig")
                    added = len(df)
                else:
                    added = merge.merge(name, df, out)["added"]
                total_new += added
                print(f"    [{i}/{len(chunks)}] {s}-{e}: +{added} dates")
        time.sleep(pause)

    print(f"    -> {name}: ~{total_new} dates -> {out.name}")
    return total_new


def refresh_one(name: str, spec: dict, start: str, end: str,
                months: int, pause: float) -> None:
    """Refresh a single series: KOSIS -> chunked backfill, FRED -> normal pull."""
    if "kosis" in spec:
        backfill_kosis(name, spec, start, end, months, pause)
    elif "fred" in spec:
        print(f"[fred]  {name}: normal pull (no chunking needed)")
        _handle_long(name, spec)     # same path pull.py uses; merges into CSV
    else:
        print(f"[skip]  {name}: no 'kosis' or 'fred' block.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", default=None,
                    help="series name from series.yaml; omit to refresh ALL")
    ap.add_argument("--start", default="200101", help="YYYYMM (default 200101)")
    ap.add_argument("--end", default=dt.date.today().strftime("%Y%m"),
                    help="YYYYMM (default this month)")
    ap.add_argument("--months", type=int, default=24,
                    help="KOSIS chunk size in months (default 24)")
    ap.add_argument("--pause", type=float, default=0.5,
                    help="seconds between KOSIS chunks (be polite to KOSIS)")
    args = ap.parse_args()

    series = load_series()

    # which series to refresh
    if args.name is None:
        names = list(series)
        print(f"Refreshing ALL {len(names)} series in series.yaml "
              f"(KOSIS backfilled, FRED pulled). Merges into existing CSVs.\n")
    else:
        if args.name not in series:
            print(f"'{args.name}' not in series.yaml")
            return
        names = [args.name]

    done = 0
    for name in names:
        try:
            refresh_one(name, series[name], args.start, args.end,
                        args.months, args.pause)
            done += 1
            print()
        except Exception as exc:
            # stop-on-first-failure (per design): name it and halt
            print(f"\n[STOP] '{name}' failed after {done} ok: "
                  f"{type(exc).__name__}: {exc}")
            print("Nothing after this point was refreshed. Fix and re-run.")
            raise SystemExit(1)

    print(f"Done. Refreshed {done}/{len(names)} series.")
    print("Routine updates from here can go through `python pull.py`.")


if __name__ == "__main__":
    main()