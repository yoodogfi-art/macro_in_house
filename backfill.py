#!/usr/bin/env python3
"""One-time backfill for KOSIS series whose per-request range is limited.

Walks from a start period to an end period in fixed-size chunks (default 24
months), pulls each chunk, and merges them into the one CSV — same fetch and
same merge logic as pull.py, so the result is identical to one big pull.

    python backfill.py kr_export_price_index
    python backfill.py kr_export_volume_index --start 200101 --end 202607
    python backfill.py kr_export_price_index --months 12   # smaller chunks

After the history is loaded once, you don't need this again — routine updates
go through `python pull.py`, which merges recent data into the same file.

Only KOSIS series are supported (FRED has no such limit; pull it normally).
Works for both wide (wide: true) and long KOSIS entries.
"""
from __future__ import annotations

import argparse
import time
import datetime as dt

from macro_data import config, kosis, merge, merge_wide
from pull import load_series


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="series name from series.yaml")
    ap.add_argument("--start", default="200101", help="YYYYMM (default 200101)")
    ap.add_argument("--end", default=dt.date.today().strftime("%Y%m"),
                    help="YYYYMM (default this month)")
    ap.add_argument("--months", type=int, default=24,
                    help="chunk size in months (default 24)")
    ap.add_argument("--pause", type=float, default=0.5,
                    help="seconds to wait between chunks (be polite to KOSIS)")
    args = ap.parse_args()

    series = load_series()
    if args.name not in series:
        print(f"'{args.name}' not in series.yaml")
        return
    spec = series[args.name]
    if "kosis" not in spec:
        print(f"'{args.name}' is not a KOSIS series; use pull.py.")
        return

    k = spec["kosis"]
    is_wide = k.get("wide", False)
    url = k["url"]
    out = config.DATA_DIR / f"{args.name}.csv"

    chunks = list(_month_iter(args.start, args.end, args.months))
    print(f"Backfilling {args.name}: {args.start} -> {args.end} "
          f"in {len(chunks)} chunk(s) of {args.months} months "
          f"({'wide' if is_wide else 'long'})")

    total_new = 0
    for i, (s, e) in enumerate(chunks, 1):
        try:
            if is_wide:
                wide, info = kosis.fetch_wide(
                    args.name, url, startPrdDe=s, endPrdDe=e
                )
                if wide.empty or wide.shape[1] <= 1:
                    print(f"  [{i}/{len(chunks)}] {s}-{e}: no data")
                else:
                    if not out.exists():
                        wide.to_csv(out, index=False, encoding="utf-8-sig")
                        added = len(wide)
                    else:
                        r = merge_wide.merge_wide(args.name, wide, out)
                        added = r["added"]
                    total_new += added
                    print(f"  [{i}/{len(chunks)}] {s}-{e}: "
                          f"+{added} dates, {wide.shape[1]-1} cols")
            else:
                df = kosis.fetch(args.name, url, startPrdDe=s, endPrdDe=e)
                if df.empty:
                    print(f"  [{i}/{len(chunks)}] {s}-{e}: no data")
                else:
                    df = df.copy()
                    df["series_id"] = args.name
                    if not out.exists():
                        df.to_csv(out, index=False, encoding="utf-8-sig")
                        added = len(df)
                    else:
                        r = merge.merge(args.name, df, out)
                        added = r["added"]
                    total_new += added
                    print(f"  [{i}/{len(chunks)}] {s}-{e}: +{added} dates")
        except Exception as exc:
            print(f"  [{i}/{len(chunks)}] {s}-{e}: FAIL "
                  f"{type(exc).__name__}: {exc}")
        time.sleep(args.pause)

    print(f"Done. {args.name}: ~{total_new} dates loaded -> {out.name}")
    print("From now on, just use `python pull.py` to keep it current.")


if __name__ == "__main__":
    main()