#!/usr/bin/env python3
"""
One-off retrospective runs for research/industrial_production.

Reruns build_table.py as if the newest available month were an earlier one.
Touches nothing in the live pipeline — delete this file when you're caught up.

    python research/industrial_production/asof_run.py          # last N_RUNS months
    python research/industrial_production/asof_run.py 7        # last 7 months
    python research/industrial_production/asof_run.py --from 2026-02 --to 2026-06
    python research/industrial_production/asof_run.py --pdf    # also render PDFs
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config as C          # noqa: E402
import build_table as B     # noqa: E402


# ---------------------------------------------------------------------------
# settings — defaults when no CLI args are given
# ---------------------------------------------------------------------------

N_RUNS = 4                   # how many of the most recent months to rebuild
ASOF_START = None            # or pin an explicit range instead ("YYYY-MM")
ASOF_END = None

# Retrospective output root. Per-month subfolders for the paper; one shared
# projection log at the root so the runs accumulate instead of overwriting.
RETRO_ROOT = C.OUT_DIR.parent / "output_retro"

# Backdate run_date in the log to when the print would have landed.
# Your live row used target 2026-07 / run_date 2026-09-01, so +2 months.
FAKE_RUN_DATE = True
RUN_DATE_OFFSET_MONTHS = 2

# Slice the trailing-average windows by calendar month instead of by row.
# Your series runs 01-10 each year, so .tail(12) spans ~14 calendar months.
# Set False to reproduce the live report's behaviour exactly, warts included.
CALENDAR_WINDOWS = True


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="retrospective build_table runs",
    )

    p.add_argument(
        "n",
        nargs="?",
        type=int,
        default=None,
        help="rebuild the last N available months",
    )

    p.add_argument(
        "--from",
        dest="start",
        default=None,
        help="YYYY-MM (wins over N)",
    )

    p.add_argument(
        "--to",
        dest="end",
        default=None,
        help="YYYY-MM",
    )

    p.add_argument(
        "--pdf",
        action="store_true",
        help="also render each report to PDF via headless Chrome",
    )

    return p.parse_args()


# ---------------------------------------------------------------------------
# patches
# ---------------------------------------------------------------------------

CURRENT: pd.Timestamp | None = None

_orig_load_wide = B._load_wide
_orig_update_log = B.update_projection_log
_orig_avgs = B.trailing_yoy_averages


def _load_wide_asof(path, *args, **kwargs):
    """Truncate every source CSV at the pretend-newest month."""
    df = _orig_load_wide(path, *args, **kwargs)

    if CURRENT is None:
        return df

    return df[df["date"] <= CURRENT].reset_index(drop=True)


def _update_log_shared(R):
    """Write the projection log to RETRO_ROOT, not the per-month folder."""
    saved = C.OUT_DIR
    C.OUT_DIR = RETRO_ROOT
    try:
        return _orig_update_log(R)
    finally:
        C.OUT_DIR = saved


def _avgs_asof(ai):
    """전산업 전년비 평균, anchored on the pretend-newest month."""
    if CURRENT is not None:
        ai = ai.loc[:CURRENT]

    if not CALENDAR_WINDOWS:
        return _orig_avgs(ai)

    yoy = (ai.pct_change(12) * 100).dropna()

    if not len(yoy):
        return {k: np.nan for k in C.AVG_WINDOWS}

    end = yoy.index.max()
    out = {}

    for label, n in C.AVG_WINDOWS.items():
        start = end - pd.DateOffset(months=n - 1)
        w = yoy.loc[start:end]
        out[label] = round(w.mean(), 2) if len(w) else np.nan

    return out


B._load_wide = _load_wide_asof
B.update_projection_log = _update_log_shared
B.trailing_yoy_averages = _avgs_asof


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def resolve_asof_months(n=None, start=None, end=None) -> list[pd.Timestamp]:
    """Months that actually exist in the export CSV, newest-last.

    Derived from the data rather than a date_range: a month with no export row
    would truncate below itself, land forecast_month on the previous month, and
    emit a duplicate report under a misleading folder name.
    """
    dates = sorted(
        pd.Timestamp(d)
        for d in _orig_load_wide(C.VOLUME_CSV)["date"].unique()
    )

    hi = (
        pd.Timestamp(end) + pd.offsets.MonthBegin(0)
        if end
        else dates[-1]
    )

    months = [d for d in dates if d <= hi]

    if start:
        lo = pd.Timestamp(start) + pd.offsets.MonthBegin(0)
        months = [d for d in months if d >= lo]
    elif n:
        months = months[-n:]

    return months


def backdate_run_dates(log_path: Path) -> None:
    if not log_path.exists():
        return

    log = pd.read_csv(log_path, parse_dates=["target_month"])

    log["run_date"] = (
        log["target_month"] + pd.DateOffset(months=RUN_DATE_OFFSET_MONTHS)
    ).dt.date

    log.to_csv(log_path, index=False, encoding="utf-8-sig")


def _find_chrome() -> str | None:
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chrome"):
        p = shutil.which(c)
        if p:
            return p

    mac = Path(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    return str(mac) if mac.exists() else None


def html_to_pdf(html_path: Path) -> None:
    """Render the report to PDF headlessly.

    Renders the file AS WRITTEN — any 요약/코멘트 you typed in the browser lives
    in localStorage, not on disk, so it won't appear here. Use the toolbar
    button for those.
    """
    chrome = _find_chrome()

    if not chrome:
        print("[pdf] chrome not found — skipping")
        return

    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={html_path.with_suffix('.pdf')}",
            html_path.resolve().as_uri(),
        ],
        check=True,
    )

    print(f"[pdf] {html_path.with_suffix('.pdf').name}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def main() -> None:
    global CURRENT

    args = parse_args()

    start = args.start or ASOF_START
    end = args.end or ASOF_END

    months = resolve_asof_months(
        n=args.n or (None if start else N_RUNS),
        start=start,
        end=end,
    )

    if not months:
        print("[retro] no export months in the requested range")
        return

    RETRO_ROOT.mkdir(parents=True, exist_ok=True)
    live_out = C.OUT_DIR

    print(
        f"[retro] {len(months)} runs: "
        f"{months[0]:%Y-%m} -> {months[-1]:%Y-%m}"
    )

    for CURRENT in months:
        C.OUT_DIR = RETRO_ROOT / f"asof_{CURRENT:%Y%m}"
        C.OUT_DIR.mkdir(parents=True, exist_ok=True)

        print()
        print("#" * 70)
        print(f"# retrospective run — asof {CURRENT:%Y-%m}")
        print("#" * 70)

        try:
            B.main()

            if args.pdf:
                html_to_pdf(C.OUT_DIR / "ip_report.html")
        finally:
            C.OUT_DIR = live_out

    if FAKE_RUN_DATE:
        backdate_run_dates(RETRO_ROOT / B.LOG_PATH_NAME)
        print(f"[retro] run_date backdated (+{RUN_DATE_OFFSET_MONTHS}mo)")

    print()
    print(f"[retro] done — {RETRO_ROOT}")


# ---------------------------------------------------------------------------
# notes
#
# Rerunning over an overlapping range is safe: folders are keyed by month, so
# the HTMLs overwrite cleanly, and update_projection_log() drops any existing
# row for the same target_month before appending.
#
# But it never removes rows for months OUTSIDE the current range — run 7 then
# run 4 and the log still holds all seven. Delete
# output_retro/projection_log.csv for a clean rebuild.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    main()