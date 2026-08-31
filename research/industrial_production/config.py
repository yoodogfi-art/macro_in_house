"""Paths and constants for the industrial_production research module.

Resolves the project root (macro_in_house/) by walking up from this file, so the
scripts work regardless of where they're invoked from. Reads the wide CSVs that
pull.py / merge_wide.py write into data/.
"""
from __future__ import annotations

from pathlib import Path

# research/industrial_production/config.py -> project root is two levels up.
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUT_DIR = HERE / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Source CSVs (wide) produced by the puller. Names match the current repo.
VOLUME_CSV = DATA_DIR / "kr_export_volume_index.csv"
TOTAL_CSV = DATA_DIR / "kr_total_production_index.csv"

# Spurious duplicate first row: 2001-01-01 appears twice (as -01 and -02).
DUP_DATE = "2001-01-02"

# image-1 export category -> production-index column (locked-in mapping).
# 선박 uses 강선 as a proxy: no clean shipbuilding line exists in this index.
PRODUCT_MAP = {
    "이차전지": "전지",
    "석유제품": "석탄및석유제품",
    "석유화학": "기초유기화학물질",
    "철강제품": "철강1차제품",
    "반도체": "반도체",
    "평판DP": "LCD평판디스플레이",
    "무선통신": "통신및방송장비",
    "가전": "가정용전기기기",
    "일반기계": "일반목적용기계",
    "자동차": "자동차",
    "선박": "강선",
}
PRODUCT_ORDER = list(PRODUCT_MAP.keys())

# All-industry production column in the total-production wide CSV.
ALL_INDUSTRY_COL = "전산업생산지수(농림어업_제외)"

# ---------------------------------------------------------------------------
# Projection settings — bridge regression (leading-indicator nowcast)
# ---------------------------------------------------------------------------
# The forward month is nowcast from a driver that is observed for that month
# BEFORE the production print (exports lead production by ~1 release cycle).
# We never project a month whose driver is not yet observed.
#
# Driver: aggregate export volume (mean of all export-volume items), YoY %.
# Model : production_yoy = alpha + beta * export_yoy   (OLS on history)
BRIDGE_MIN_OBS = 24          # minimum overlapping months required to fit
BRIDGE_BLEND = 0.7           # adjusted = BLEND*bridge + (1-BLEND)*seasonal anchor
ANCHOR_WINDOW = 3            # trailing-months for the seasonal YoY anchor

# How many most-recent months to show in the main table.
# You have full history (2001.01-2026.07), so 24 months always populate.
TABLE_MONTHS = 24

# Trailing-average windows (months) reported for the all-industry YoY.
# Averages of YoY growth, not of the level.
AVG_WINDOWS = {"3mo": 3, "6mo": 6, "1yr": 12, "2yr": 24}

# Consensus / min / max / median block: manually supplied by the analyst.
# Left as None so the paper renders blank cells to fill in.
CONSENSUS_FIELDS = ["consensus_YoY", "min_YoY", "max_YoY", "median_YoY"]