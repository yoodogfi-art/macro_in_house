#!/usr/bin/env python3
"""
Korea industrial-production analysis + research-paper prototype.

build_table.py 자체를 직접 실행하면 됩니다.

    python build_table.py

또는 프로젝트 어디서든:

    python research/industrial_production/build_table.py

핵심 로직
----------
1. 산업생산 실적 발표 여부와 관계없이 전망값을 항상 계산한다.
2. 전망 대상월은 "수출물량 YoY가 계산 가능한 가장 최근 월"이다.
3. 따라서 전망 대상월의 산업생산 실적이 이미 발표되어 있어도
   전망값(projection)은 그대로 저장한다.
4. 조정전망 전년비는 다음과 같이 계산한다.

       조정전망 전년비 = 전망 전년비 - 실제 전년비

5. projection_log.csv에는 같은 전망월을 매 실행마다 최신 전망으로 갱신한다.
6. 이후 실제값이 발표되면 기존 전망 로그에 실제값과 오차를 자동으로 채운다.
"""

from __future__ import annotations

import sys
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# config import
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config as C  # noqa: E402


# ---------------------------------------------------------------------------
# load / clean
# ---------------------------------------------------------------------------

def _load_wide(path: Path) -> pd.DataFrame:
    """wide CSV를 읽고 월 단위 날짜로 정리한다."""

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. "
            f"Run `python pull.py` first, or check the filename."
        )

    df = pd.read_csv(
        path,
        parse_dates=["date"],
    )

    # 중복 2001-01-02 제거
    df = df[
        df["date"] != pd.Timestamp(C.DUP_DATE)
    ].reset_index(drop=True)

    # 모든 날짜를 월초 기준으로 통일
    df["date"] = df["date"].values.astype("datetime64[M]")

    df = (
        df.sort_values("date")
        .drop_duplicates(
            subset="date",
            keep="first",
        )
        .reset_index(drop=True)
    )

    return df


def load_products() -> pd.DataFrame:
    """주요 품목 생산지수를 불러온다."""

    vol = _load_wide(C.VOLUME_CSV)

    keep = ["date"]
    rename = {}
    missing = []

    for label, col in C.PRODUCT_MAP.items():
        if col in vol.columns:
            keep.append(col)
            rename[col] = label
        else:
            missing.append((label, col))

    if missing:
        print("[warn] unmatched products:", missing)

    return (
        vol[keep]
        .rename(columns=rename)
        .set_index("date")
        .sort_index()
    )


def load_all_industry() -> pd.Series:
    """전산업 생산지수를 불러온다."""

    tot = _load_wide(C.TOTAL_CSV)

    if C.ALL_INDUSTRY_COL not in tot.columns:
        raise KeyError(
            f"'{C.ALL_INDUSTRY_COL}' not in "
            f"{C.TOTAL_CSV.name}; "
            f"columns are {list(tot.columns)}"
        )

    return (
        tot.set_index("date")[C.ALL_INDUSTRY_COL]
        .sort_index()
        .rename("all_industry")
    )


def load_export_aggregate() -> pd.Series:
    """
    수출물량 지수의 전체 품목 평균.

    해당 월 일부 변수만 존재하더라도
    존재하는 숫자들의 평균으로 계산한다.
    """

    vol = (
        _load_wide(C.VOLUME_CSV)
        .set_index("date")
        .sort_index()
    )

    num = vol.apply(
        pd.to_numeric,
        errors="coerce",
    )

    # skipna=True가 기본이므로 해당 월 일부 변수만 있어도
    # 존재하는 값으로 aggregate가 계산된다.
    agg = num.mean(
        axis=1,
        skipna=True,
    )

    # 모든 변수가 NaN인 월은 전망에 사용하지 않는다.
    agg = agg.where(
        num.notna().any(axis=1)
    )

    return agg.rename("export_agg")


# ---------------------------------------------------------------------------
# regression
# ---------------------------------------------------------------------------

def _ols(
    x: np.ndarray,
    y: np.ndarray,
):
    """y = alpha + beta*x OLS."""

    A = np.column_stack(
        [
            np.ones_like(x),
            x,
        ]
    )

    coef, *_ = np.linalg.lstsq(
        A,
        y,
        rcond=None,
    )

    return (
        float(coef[0]),
        float(coef[1]),
    )


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------

def project(
    ai: pd.Series,
    exp: pd.Series,
):
    """
    수출물량 선행지표를 이용해 전산업 생산 전망을 계산한다.

    중요:
    --------
    기존 코드처럼 "실제값보다 미래인 월"만 전망월로 잡지 않는다.

    수출 YoY가 존재하는 가장 최근 월이면,
    그 월의 산업생산 실제값이 이미 발표됐더라도
    전망값을 계산하고 저장한다.

    예:
        2026-07 산업생산 실적 발표됨
        2026-07 수출물량 데이터 존재

    -> 2026-07 전망값도 계산
    -> 실제값도 존재
    -> 조정전망 전년비 = 전망 YoY - 실제 YoY
    """

    ai = ai.sort_index()
    exp = exp.sort_index()

    # -----------------------------------------------------------------------
    # YoY
    # -----------------------------------------------------------------------

    ai_yoy = (
        ai.pct_change(12)
        * 100
    )

    exp_yoy = (
        exp.pct_change(12)
        * 100
    )

    # -----------------------------------------------------------------------
    # regression sample
    # -----------------------------------------------------------------------

    fit = pd.concat(
        [
            ai_yoy.rename("y"),
            exp_yoy.rename("x"),
        ],
        axis=1,
    ).dropna()

    if len(fit) < C.BRIDGE_MIN_OBS:
        print(
            "[warn] insufficient bridge observations: "
            f"{len(fit)} < {C.BRIDGE_MIN_OBS}"
        )

        idx = ai.index.union(
            exp_yoy.dropna().index
        ).sort_values()

        empty = pd.Series(
            np.nan,
            index=idx,
        )

        return (
            empty.rename("projection"),
            empty.rename("adjusted_projection"),
            None,
            None,
        )

    alpha, beta = _ols(
        fit["x"].values,
        fit["y"].values,
    )

    # -----------------------------------------------------------------------
    # projection index
    # -----------------------------------------------------------------------

    full_idx = (
        ai.index
        .union(exp_yoy.dropna().index)
        .sort_values()
    )

    projection = pd.Series(
        np.nan,
        index=full_idx,
        dtype=float,
    )

    adjusted = pd.Series(
        np.nan,
        index=full_idx,
        dtype=float,
    )

    # 최근 실제 생산 YoY를 seasonal anchor로 사용
    anchor_yoy = (
        ai_yoy
        .dropna()
        .tail(C.ANCHOR_WINDOW)
        .mean()
    )

    # -----------------------------------------------------------------------
    # calculate every available projection
    # -----------------------------------------------------------------------

    for d in full_idx:

        # 수출 YoY가 없는 월은 전망 불가
        if d not in exp_yoy.index:
            continue

        x_now = exp_yoy.loc[d]

        if pd.isna(x_now):
            continue

        # bridge forecast YoY
        bridge_yoy = (
            alpha
            + beta * x_now
        )

        # 전년 동월 생산지수
        base_date = d - pd.DateOffset(
            months=12
        )

        base = ai.get(
            base_date,
            np.nan,
        )

        if pd.isna(base):
            continue

        # bridge level
        proj_level = (
            base
            * (1 + bridge_yoy / 100)
        )

        # seasonal anchor level
        anchor_level = (
            base
            * (1 + anchor_yoy / 100)
        )

        # blended adjusted level
        adj_level = (
            C.BRIDGE_BLEND * proj_level
            + (1 - C.BRIDGE_BLEND)
            * anchor_level
        )

        projection.loc[d] = proj_level
        adjusted.loc[d] = adj_level

    # -----------------------------------------------------------------------
    # IMPORTANT:
    # 가장 최근 "전망 가능한 월"을 항상 forecast_month로 사용
    #
    # actual release 여부는 여기서 보지 않는다.
    # -----------------------------------------------------------------------

    available_forecast_months = (
        exp_yoy.dropna().index
    )

    if len(available_forecast_months) == 0:
        forecast_month = None
        stats = None

        return (
            projection,
            adjusted,
            forecast_month,
            stats,
        )

    # 실제 산업생산이 발표됐더라도 가장 최근 수출월을 전망월로 사용
    forecast_month = (
        available_forecast_months[-1]
    )

    forecast_export_yoy = (
        exp_yoy.loc[forecast_month]
    )

    forecast_bridge_yoy = (
        alpha
        + beta * forecast_export_yoy
    )

    stats = {
        "alpha": alpha,
        "beta": beta,
        "n_obs": len(fit),

        "bridge_yoy": float(
            forecast_bridge_yoy
        ),

        "export_yoy": float(
            forecast_export_yoy
        ),

        "anchor_yoy": float(
            anchor_yoy
        ),
    }

    return (
        projection,
        adjusted,
        forecast_month,
        stats,
    )


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def trailing_yoy_averages(
    ai: pd.Series,
) -> dict:
    """전산업 생산 YoY trailing average."""

    yoy = (
        ai.pct_change(12)
        * 100
    ).dropna()

    out = {}

    for label, n in C.AVG_WINDOWS.items():

        if len(yoy):
            out[label] = round(
                yoy.tail(n).mean(),
                2,
            )
        else:
            out[label] = np.nan

    return out


def consensus_block() -> dict:
    """수기 컨센서스 영역."""

    return {
        f: None
        for f in C.CONSENSUS_FIELDS
    }


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build():

    print("[start] loading data...")

    prod = load_products()
    ai = load_all_industry()
    exp = load_export_aggregate()

    print(
        f"[data] production: "
        f"{prod.index.min().date()} -> "
        f"{prod.index.max().date()}"
    )

    print(
        f"[data] all-industry: "
        f"{ai.index.min().date()} -> "
        f"{ai.index.max().date()}"
    )

    export_available = (
        exp.dropna().index
    )

    if len(export_available):
        print(
            f"[data] export aggregate: "
            f"{export_available.min().date()} -> "
            f"{export_available.max().date()}"
        )
    else:
        print(
            "[warn] no export aggregate data"
        )

    # 품목 YoY / MoM
    yoy = (
        prod.pct_change(12)
        * 100
    )

    mom = (
        prod.pct_change(1)
        * 100
    )

    # 전망
    (
        proj,
        adj,
        forecast_month,
        bstats,
    ) = project(
        ai,
        exp,
    )

    # 전망 때문에 확장된 index
    full_idx = proj.index

    ai_full = ai.reindex(
        full_idx
    )

    # 실제 YoY / MoM
    ai_yoy = (
        ai_full.pct_change(12)
        * 100
    )

    ai_mom = (
        ai_full.pct_change(1)
        * 100
    )

    # -----------------------------------------------------------------------
    # forecast YoY / MoM
    # -----------------------------------------------------------------------

    proj_yoy = (
        proj
        / ai_full.shift(12)
        - 1
    ) * 100

    proj_mom = (
        proj
        / ai_full.shift(1)
        - 1
    ) * 100

    # -----------------------------------------------------------------------
    # adjusted projection YoY
    #
    # 사용자가 원하는 정의:
    #
    #     조정전망 전년비
    #       = 전망값 전년비 - 실제값 전년비
    #
    # 따라서 실제값이 발표된 월에서는 숫자가 나오고,
    # 실제값이 아직 없으면 NaN이다.
    # -----------------------------------------------------------------------

    adj_proj_yoy_raw = (
        adj
        / ai_full.shift(12)
        - 1
    ) * 100

    adj_yoy = ai_yoy - proj_yoy

    all_ind = pd.DataFrame(
        {
            "actual": ai_full,

            "projection": proj,

            "adjusted_projection": adj,

            "actual_YoY_%": ai_yoy,

            "actual_MoM_%": ai_mom,

            "proj_YoY_%": proj_yoy,

            "proj_MoM_%": proj_mom,

            "adjproj_YoY_%": adj_yoy,
        }
    )

    return {
        "prod": prod,

        "yoy": yoy,

        "mom": mom,

        "all_ind": all_ind,

        "avgs": trailing_yoy_averages(
            ai
        ),

        "consensus": consensus_block(),

        "last_actual": ai.index[-1],

        "future_month": forecast_month,

        "forecast_month": forecast_month,

        "bridge": bstats,
    }


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------

def write_csv_xlsx(R):

    print("[write] CSV / XLSX...")

    # 품목 생산지수
    R["prod"].to_csv(
        C.OUT_DIR / "ip_clean_volume.csv",
        encoding="utf-8-sig",
    )

    # 전산업 actual / projection
    R["all_ind"][
        [
            "actual",
            "projection",
            "adjusted_projection",
        ]
    ].to_csv(
        C.OUT_DIR / "ip_clean_total.csv",
        encoding="utf-8-sig",
    )

    with pd.ExcelWriter(
        C.OUT_DIR / "ip_analysis_table.xlsx",
        engine="openpyxl",
        datetime_format="yyyy-mm",
    ) as xw:

        R["prod"].round(3).to_excel(
            xw,
            sheet_name="production_level",
        )

        R["yoy"].round(1).to_excel(
            xw,
            sheet_name="YoY_pct",
        )

        R["mom"].round(1).to_excel(
            xw,
            sheet_name="MoM_pct",
        )

        R["all_ind"].round(2).to_excel(
            xw,
            sheet_name="all_industry",
        )

        pd.DataFrame(
            {
                "trailing_YoY_avg_%":
                    R["avgs"]
            }
        ).to_excel(
            xw,
            sheet_name="stats",
        )

        pd.DataFrame(
            {
                "value":
                    R["consensus"]
            }
        ).to_excel(
            xw,
            sheet_name="consensus_manual",
        )


def write_html(R):

    print("[write] HTML...")

    from html_report import render

    html = render(
        R,
        C,
    )

    (
        C.OUT_DIR / "ip_report.html"
    ).write_text(
        html,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# projection log
# ---------------------------------------------------------------------------

LOG_PATH_NAME = "projection_log.csv"

LOG_COLS = [
    "target_month",
    "run_date",
    "proj_level",
    "proj_yoy",
    "adj_proj_yoy",
    "export_yoy_used",
    "beta",
    "n_obs",
    "actual_level",
    "actual_yoy",
    "error_level",
    "error_yoy",
]


def update_projection_log(R):

    log_path = (
        C.OUT_DIR
        / LOG_PATH_NAME
    )

    # -----------------------------------------------------------------------
    # 기존 log
    # -----------------------------------------------------------------------

    if log_path.exists():

        log = pd.read_csv(
            log_path,
            parse_dates=[
                "target_month"
            ],
        )

        for c in LOG_COLS:

            if c not in log.columns:
                log[c] = np.nan

    else:

        log = pd.DataFrame(
            columns=LOG_COLS
        )

    # -----------------------------------------------------------------------
    # 현재 전망
    # -----------------------------------------------------------------------

    ai = R["all_ind"]

    # build()에서 forecast_month를 넣음
    fm = R.get(
        "forecast_month",
        R.get("future_month"),
    )

    bs = R.get("bridge")

    # -----------------------------------------------------------------------
    # 전망값은 실제 발표 여부와 관계없이 무조건 저장
    # -----------------------------------------------------------------------

    if (
        fm is not None
        and bs is not None
        and fm in ai.index
    ):

        proj_level = ai.loc[
            fm,
            "projection",
        ]

        proj_yoy = ai.loc[
            fm,
            "proj_YoY_%",
        ]

        adj_proj_yoy = ai.loc[
            fm,
            "adjproj_YoY_%",
        ]

        actual_level = ai.loc[
            fm,
            "actual",
        ]

        actual_yoy = ai.loc[
            fm,
            "actual_YoY_%",
        ]

        # 실제값이 이미 발표됐다면 바로 오차 계산
        if pd.notna(
            proj_level
        ) and pd.notna(
            actual_level
        ):
            error_level = (
                float(proj_level)
                - float(actual_level)
            )
        else:
            error_level = np.nan

        if pd.notna(
            proj_yoy
        ) and pd.notna(
            actual_yoy
        ):
            error_yoy = (
                float(proj_yoy)
                - float(actual_yoy)
            )
        else:
            error_yoy = np.nan

        row = {
            "target_month":
                pd.Timestamp(fm),

            "run_date":
                dt.date.today().isoformat(),

            "proj_level":
                round(
                    float(proj_level),
                    3,
                )
                if pd.notna(proj_level)
                else np.nan,

            "proj_yoy":
                round(
                    float(proj_yoy),
                    3,
                )
                if pd.notna(proj_yoy)
                else np.nan,

            "adj_proj_yoy":
                round(
                    float(adj_proj_yoy),
                    3,
                )
                if pd.notna(adj_proj_yoy)
                else np.nan,

            "export_yoy_used":
                round(
                    float(bs["export_yoy"]),
                    3,
                ),

            "beta":
                round(
                    float(bs["beta"]),
                    4,
                ),

            "n_obs":
                int(bs["n_obs"]),

            "actual_level":
                round(
                    float(actual_level),
                    3,
                )
                if pd.notna(actual_level)
                else np.nan,

            "actual_yoy":
                round(
                    float(actual_yoy),
                    3,
                )
                if pd.notna(actual_yoy)
                else np.nan,

            "error_level":
                round(
                    float(error_level),
                    3,
                )
                if pd.notna(error_level)
                else np.nan,

            "error_yoy":
                round(
                    float(error_yoy),
                    3,
                )
                if pd.notna(error_yoy)
                else np.nan,
        }

        # 동일 전망월은 최신 계산값으로 갱신
        log = log[
            log["target_month"]
            != pd.Timestamp(fm)
        ]

        log = pd.concat(
            [
                log,
                pd.DataFrame([row]),
            ],
            ignore_index=True,
        )

        print(
            f"[projection] saved: "
            f"{pd.Timestamp(fm).strftime('%Y-%m')}"
        )

        print(
            f"[projection] "
            f"forecast YoY = "
            f"{proj_yoy:+.2f}%"
        )

        if pd.notna(actual_yoy):

            print(
                f"[projection] "
                f"actual YoY = "
                f"{actual_yoy:+.2f}%"
            )

            print(
                f"[projection] "
                f"adjusted YoY = "
                f"{adj_proj_yoy:+.2f}% "
                f"(forecast - actual)"
            )

    else:

        print(
            "[warn] no valid projection "
            "month to save"
        )

    # -----------------------------------------------------------------------
    # 과거 전망의 실제값 업데이트
    #
    # 이전 실행 당시에는 실제값이 없었지만,
    # 이후 실제 발표가 된 경우 자동으로 채운다.
    # -----------------------------------------------------------------------

    actual_lvl = R[
        "all_ind"
    ]["actual"]

    actual_yoy = R[
        "all_ind"
    ]["actual_YoY_%"]

    for i, r in log.iterrows():

        tm = pd.Timestamp(
            r["target_month"]
        )

        if (
            tm in actual_lvl.index
            and pd.notna(
                actual_lvl.loc[tm]
            )
        ):

            av = float(
                actual_lvl.loc[tm]
            )

            ay_value = (
                actual_yoy.loc[tm]
                if tm in actual_yoy.index
                else np.nan
            )

            ay = (
                float(ay_value)
                if pd.notna(ay_value)
                else np.nan
            )

            log.at[
                i,
                "actual_level",
            ] = round(
                av,
                3,
            )

            log.at[
                i,
                "actual_yoy",
            ] = (
                round(
                    ay,
                    3,
                )
                if pd.notna(ay)
                else np.nan
            )

            # 전망 level - 실제 level
            if pd.notna(
                r.get("proj_level")
            ):

                log.at[
                    i,
                    "error_level",
                ] = round(
                    float(
                        r["proj_level"]
                    )
                    - av,
                    3,
                )

            # 전망 YoY - 실제 YoY
            if (
                pd.notna(
                    r.get("proj_yoy")
                )
                and pd.notna(ay)
            ):

                log.at[
                    i,
                    "error_yoy",
                ] = round(
                    float(
                        r["proj_yoy"]
                    )
                    - ay,
                    3,
                )

    # -----------------------------------------------------------------------
    # save
    # -----------------------------------------------------------------------

    log = (
        log
        .sort_values(
            "target_month"
        )
        .reset_index(
            drop=True
        )
    )

    log = log[
        LOG_COLS
    ]

    log.to_csv(
        log_path,
        index=False,
        encoding="utf-8-sig",
    )

    return log


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():

    print("=" * 70)
    print("industrial_production / build_table.py")
    print("=" * 70)

    R = build()

    write_csv_xlsx(R)

    write_html(R)

    log = update_projection_log(R)

    n = min(
        C.TABLE_MONTHS,
        len(R["prod"]),
    )

    print()
    print(
        f"[ok] {len(R['prod'])} rows, "
        f"{R['prod'].index.min().date()} -> "
        f"{R['prod'].index.max().date()}"
    )

    print(
        f"[ok] trailing YoY avgs: "
        f"{R['avgs']}"
    )

    fm = R.get(
        "forecast_month",
        R.get("future_month"),
    )

    if fm is not None:

        print(
            f"[ok] projection month: "
            f"{pd.Timestamp(fm).strftime('%Y-%m')}"
        )

        print(
            f"[ok] projection log: "
            f"{LOG_PATH_NAME} "
            f"({len(log)} tracked)"
        )

    else:

        print(
            "[warn] projection month: None"
        )

    n_filled = (
        int(
            log[
                "actual_level"
            ].notna().sum()
        )
        if len(log)
        else 0
    )

    print(
        f"[ok] projection log: "
        f"{len(log)} rows, "
        f"{n_filled} with actuals filled"
    )

    print(
        f"[ok] output directory: "
        f"{C.OUT_DIR}"
    )

    print(
        f"[ok] table shows last "
        f"{n} months"
    )

    print("=" * 70)
    print("[done] build_table.py finished")
    print("=" * 70)


if __name__ == "__main__":
    main()
