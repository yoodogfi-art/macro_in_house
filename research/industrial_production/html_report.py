# -*- coding: utf-8 -*-
"""산업생산 리서치 노트 HTML 렌더러.

국내 리서치 하우스 스타일. 나눔스퀘어 서체, 절제된 색조, 한글 표기,
단어 내 줄바꿈 없음. 출처는 KOSIS.
"""
from __future__ import annotations

import datetime as dt
import numpy as np


def _sign(v, dp=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span class="na">-</span>'
    cls = "up" if v > 0 else "dn" if v < 0 else "fl"
    sgn = "+" if v > 0 else ""
    return f'<span class="{cls}">{sgn}{v:.{dp}f}</span>'


def _plain(v, dp=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:.{dp}f}"


# 라벨: 화면 표기용 짧은 한글. 단어 내 줄바꿈 방지 위해 nowrap 처리.
CONS_LABELS = {
    "consensus_YoY": "컨센서스",
    "min_YoY": "최소",
    "max_YoY": "최대",
    "median_YoY": "중앙값",
}
AVG_LABELS = {"3mo": "3개월", "6mo": "6개월", "1yr": "1년", "2yr": "2년"}


def render(R, C) -> str:
    prod, yoy = R["prod"], R["yoy"]
    ai = R["all_ind"]
    last_actual = R["last_actual"]
    future_month = R["future_month"]
    logged = R.get("logged", {})
    # show the last N months of the full (projection-extended) index
    n = min(C.TABLE_MONTHS, len(ai))
    idx = ai.index[-n:]
    products = [p for p in C.PRODUCT_ORDER if p in prod.columns]
    today = dt.date.today().strftime("%Y-%m-%d")

    prod_head = "".join(f"<th>{p}</th>" for p in products)
    rows = []
    for d in idx:
        act_y = ai.loc[d, "actual_YoY_%"]
        act_m = ai.loc[d, "actual_MoM_%"]
        _av = ai.loc[d, "actual"]
        has_actual = _av is not None and not (isinstance(_av, float) and np.isnan(_av))
        is_last_actual = (d == last_actual)
        # a row is "future" only if flagged AND it has no real actual value.
        # if an actual exists for this month, it always renders (never blanked).
        is_future = (d == future_month) and not has_actual
        rcls = " class='r-last'" if is_last_actual else (
            " class='r-proj'" if is_future else "")

        # product YoY: blank only on a genuine future (no-actual) row
        if is_future:
            cells = "".join("<td class='na'>-</td>" for _ in products)
        else:
            cells = "".join(f"<td>{_sign(yoy.loc[d, p])}</td>"
                            if d in yoy.index else "<td class='na'>-</td>"
                            for p in products)

        # bold wrapper for the latest actual row's figures
        b0, b1 = ("<b>", "</b>") if is_last_actual else ("", "")

        actual_y = "<span class='na'>-</span>" if is_future else f"{b0}{_sign(act_y)}{b1}"
        actual_m = "<span class='na'>-</span>" if is_future else f"{b0}{_sign(act_m)}{b1}"

        dt_lbl = d.strftime("%Y.%m")
        if is_future:
            dt_lbl += "<span class='tag-p'>(E)</span>"

        rows.append(
            f"<tr{rcls}><td class='dt'>"
            f"<button class='xbtn' onclick='dropRow(this)' title='행 삭제' "
            f"data-noprint>&times;</button>{dt_lbl}</td>{cells}"
            f"<td class='sep'>{actual_y}</td>"
            f"<td>{actual_m}</td>"
            f"<td class='sep'>{_sign(ai.loc[d, 'proj_YoY_%'])}</td>"
            f"<td>{_sign(ai.loc[d, 'proj_MoM_%'])}</td>"
            f"<td class='sep'>{_sign(ai.loc[d, 'adjproj_YoY_%'])}</td></tr>"
        )
    body = "\n".join(rows)

    cons = "".join(
        f"<span class='cons-item'><span class='cons-k'>{CONS_LABELS.get(f, f)}</span>"
        f"<span class='cons-v edit' contenteditable='true' "
        f"data-edit='cons_{f}'>—</span></span>"
        for f in C.CONSENSUS_FIELDS
    )
    avgs = "".join(
        f"<div class='cell'><span class='k'>{AVG_LABELS.get(k, k)}</span>"
        f"<span class='v'>{_plain(v)}{'' if v is None or (isinstance(v, float) and np.isnan(v)) else '%'}</span></div>"
        for k, v in R["avgs"].items()
    )

    # equal-width columns: date + N products + 5 stat cols (no extra delete col)
    colgroup = "<col class='c-dt'>"
    colgroup += "".join("<col class='c-prod'>" for _ in products)
    colgroup += "".join("<col class='c-stat'>" for _ in range(5))
    # product columns share one width computed from remaining space
    prod_w = f"{round(62.0 / max(len(products), 1), 3)}%"

    # bridge diagnostics note
    bs = R.get("bridge")
    if bs and future_month is not None:
        bridge_note = (
            f"전망(E)은 수출물량 브릿지 회귀 나우캐스트: "
            f"생산 전년비 = {bs['alpha']:.1f} + {bs['beta']:.2f}×수출 전년비 "
            f"(표본 {bs['n_obs']}개월). "
            f"해당월 수출 전년비 {bs['export_yoy']:+.1f} → 생산 전년비 {bs['bridge_yoy']:+.1f}."
        )
    else:
        bridge_note = "수출이 생산을 선행하지 않아 전망 나우캐스트 미생성 (실적만 표시)."

    return _TEMPLATE.format(
        today=today, n=n, prod_head=prod_head, body=body,
        cons=cons, avgs=avgs, colgroup=colgroup, prod_w=prod_w,
        bridge_note=bridge_note,
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>산업생산 동향</title>
<link href="https://cdn.jsdelivr.net/gh/moonspam/NanumSquare@2.0/nanumsquare.css" rel="stylesheet">
<style>
  @page {{ size:A4 portrait; margin:14mm; }}
  :root {{
    --ink:#1a1a1a; --hd:#12432b; --hd2:#1a5638; --rule:#c9cdd2;
    --soft:#f4f7f4; --band:#fafbfa; --acc:#12432b;
    --up:#c0392b; --dn:#1b5faa; --mut:#6a7078;
  }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; padding:0; }}
  body {{ font-family:'NanumSquare','Malgun Gothic',sans-serif;
    color:var(--ink); background:#fff; -webkit-print-color-adjust:exact;
    print-color-adjust:exact; }}
  .page {{ width:182mm; margin:0 auto; }}

  .masthead {{ border-bottom:2.5px solid var(--hd); padding-bottom:7px;
    margin-bottom:3px; display:flex; align-items:flex-end;
    justify-content:space-between; }}
  .masthead h1 {{ font-size:23px; font-weight:800; margin:0; letter-spacing:-.5px;
    color:var(--hd); }}
  .masthead .meta {{ font-size:10px; color:var(--mut); text-align:right;
    line-height:1.5; white-space:nowrap; }}
  .lede {{ font-size:11px; color:#40454b; margin:6px 0 12px; font-weight:600;
    line-height:1.5; }}

  .band {{ display:grid; grid-template-columns:74px repeat(4,1fr); gap:0;
    border:1px solid var(--rule);
    margin-bottom:6px; }}
  .band .tag {{ background:var(--soft); font-size:10px; font-weight:800;
    color:var(--hd); display:flex; align-items:center; padding:0 10px;
    border-right:1px solid var(--rule); white-space:nowrap; line-height:1.3; }}
  .band .cell {{ padding:6px 10px; border-right:1px solid var(--rule);
    display:flex; flex-direction:column; gap:2px; }}
  .band .cell:last-child {{ border-right:0; }}
  .band .k {{ font-size:9.5px; color:var(--mut); font-weight:700;
    white-space:nowrap; }}
  .band .v {{ font-size:14px; font-weight:800; color:var(--ink); }}
  .band .v.blank {{ height:15px; }}

  .sect {{ display:flex; align-items:baseline; justify-content:space-between;
    background:var(--hd); color:#fff; padding:5px 10px; margin-top:12px; }}
  .sect .t {{ font-size:11.5px; font-weight:800; letter-spacing:.3px; }}
  .sect .u {{ font-size:9.5px; font-weight:700; color:#c6d0dd; }}

  table {{ border-collapse:collapse; width:100%; font-size:9px;
    table-layout:fixed; }}
  col.c-dt {{ width:52px; }}
  col.c-prod {{ width:{prod_w}; }}
  col.c-stat {{ width:38px; }}
  thead th {{ background:var(--hd2); color:#fff; font-weight:700;
    padding:5px 1px; text-align:right; border:1px solid #2b6a47;
    line-height:1.15; overflow:hidden; font-size:8.5px; }}
  thead th:first-child {{ text-align:center; }}
  tbody td {{ padding:4px 2px; text-align:right; border:1px solid var(--rule);
    white-space:nowrap; overflow:hidden; }}
  tbody tr:nth-child(even) {{ background:var(--band); }}
  td.dt {{ text-align:center; font-weight:800; color:var(--hd);
    background:var(--soft); }}
  tbody tr:nth-child(even) td.dt {{ background:#e7ede8; }}
  td.sep {{ border-left:2px solid var(--hd); }}
  thead th.sep {{ border-left:2px solid #3f7a58; }}
  .up {{ color:var(--up); font-weight:700; }}
  .dn {{ color:var(--dn); font-weight:700; }}
  .fl {{ color:#555; }} .na {{ color:#b7bcc2; }}
  tr.r-last td {{ background:#eaf3ec !important; }}
  tr.r-last td.dt {{ background:#d7e7db !important; }}
  tr.r-last b {{ font-weight:800; }}
  tr.r-proj td {{ background:#fbfaf3 !important; font-style:normal; }}
  tr.r-proj td.dt {{ background:#f2eede !important; color:#7a6a1e; }}
  .tag-p {{ font-size:8px; color:#7a6a1e; margin-left:2px; vertical-align:top; }}

  .foot {{ font-size:9px; color:var(--mut); margin-top:5px; line-height:1.55; }}
  .summary {{ border:1px solid var(--rule); background:#f0f4f1;
    padding:10px 13px; font-size:11.5px; line-height:1.7; font-weight:800;
    color:var(--hd); margin-top:2px; }}
  .summary:hover {{ background:#eaf1ec; }}
  .cmt {{ border:1px solid var(--rule); background:#fff;
    padding:10px 13px; font-size:10.5px; line-height:1.9; color:#2a2f2b;
    margin-top:2px; }}
  .cmt:hover {{ background:#fcfcfb; }}
  .cons-line {{ margin:10px 0 0; padding:7px 2px; font-size:10.5px;
    color:#2a2f2b; border-top:1px solid var(--rule); }}
  .cons-tag {{ font-weight:800; color:var(--hd); margin-right:12px; }}
  .cons-item {{ margin-right:18px; white-space:nowrap; }}
  .cons-k {{ color:var(--mut); margin-right:4px; }}
  .cons-v {{ font-weight:700; min-width:34px; display:inline-block; }}

  .edit {{ outline:none; }}
  .edit:hover {{ background:#fffde9; }}
  .edit:focus {{ background:#fffdf0; box-shadow:inset 0 0 0 1px #b7a94a; }}
  .cmt.edit {{ cursor:text; }}
  .cmt.edit:hover {{ background:#fbfaf0; }}
  span.v.edit {{ display:inline-block; min-width:60px; cursor:text; }}
  td.dt {{ position:relative; }}
  .xbtn {{ position:absolute; left:1px; top:50%; transform:translateY(-50%);
    border:none; background:transparent; color:#c0392b; font-size:12px;
    line-height:1; cursor:pointer; padding:0 2px; font-weight:800; opacity:0; }}
  tr:hover .xbtn {{ opacity:1; }}
  .xbtn:hover {{ color:#fff; background:#c0392b; border-radius:2px; }}
  .toolbar {{ max-width:182mm; margin:14px auto 30px; padding:10px 12px;
    background:#eef3ef; border:1px solid var(--rule);
    display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
  .toolbar button {{ font-family:inherit; font-size:11px; font-weight:800;
    padding:7px 14px; border:1px solid var(--hd); background:#fff; color:var(--hd);
    border-radius:3px; cursor:pointer; }}
  .toolbar button.tb-primary {{ background:var(--hd); color:#fff; }}
  .toolbar button:hover {{ opacity:.88; }}
  .toolbar .tb-note {{ font-size:10px; color:var(--mut); line-height:1.4; }}

  @media print {{
    [data-noprint] {{ display:none !important; }}
    .edit:hover, .edit:focus {{ background:transparent !important; box-shadow:none !important; }}
    .toolbar {{ display:none !important; }}
    body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}

    .summary, .cons-v {{
      -webkit-user-modify: read-only !important;
      overflow: visible !important;
      height: auto !important;
      pointer-events: none;
      border: 1px solid var(--rule) !important;
      background: #fff !important;
    }}
    .summary {{ background: #f0f4f1 !important; }}

    .cmt {{
      overflow: visible !important;
      height: auto !important;
      border: 1px solid var(--rule) !important;
      background: #fff !important;
      color: #2a2f2b !important;
      font-size: 10.5px !important;
      padding: 6px 12px !important;
      line-height: 1.55 !important;
      margin-top: 1px !important;
      white-space: normal !important;
    }}

    .summary, .cmt {{ page-break-inside:avoid; break-inside:avoid; }}
    .sect {{ page-break-after:avoid; break-after:avoid; }}
    .sect {{ margin-top:7px !important; padding:3px 10px !important; }}
    .summary {{ padding:6px 12px !important; line-height:1.5 !important; margin-top:1px !important; }}
    .foot {{ margin-top:3px !important; }}
    tbody td {{ padding-top:2px !important; padding-bottom:2px !important; }}
    thead th {{ padding-top:3px !important; padding-bottom:3px !important; }}
    .cons-line {{ margin-top:6px !important; padding:5px 2px !important; }}
  }}
</style></head>
<body>
<div class="page">

  <div class="masthead">
    <h1>산업생산 동향</h1>
    <div class="meta">출처: KOSIS<br>작성일: {today}</div>
  </div>
  <div class="lede">전산업 및 주요 품목 생산지수 &mdash; 전년동월비 및 전월비,
    실적 대 전망 비교.</div>

  <div class="band">
    <div class="tag">전산업<br>전년비 평균</div>
    {avgs}
  </div>

  <div class="sect">
    <span class="t">주요 품목 전년동월비 · 전산업 실적 대 전망</span>
    <span class="u">단위: %</span>
  </div>
  <table>
    <colgroup>{colgroup}</colgroup>
    <thead><tr>
      <th>날짜</th>{prod_head}
      <th class="sep">실적<br>전년비</th><th>실적<br>전월비</th>
      <th class="sep">전망<br>전년비</th><th>전망<br>전월비</th>
      <th class="sep">조정전망<br>전년비</th>
    </tr></thead>
    <tbody>
    {body}
    </tbody>
  </table>
  <div class="foot">선박은 강선 기준 대용치. 광공업생산(실적)은 전산업 생산 실적.<br>{bridge_note}</div>

  <div class="sect">
    <span class="t">요약</span>
  </div>
  <div class="summary edit" contenteditable="true" data-edit="summary">
    전산업생산은 회복 흐름을 이어가며 전월비 개선. 수출 증가세가 생산을 견인하는 가운데
    반도체·자동차 중심의 강세가 지속. 향후 대외 수요와 재고 조정 국면을 주시.
  </div>

  <div class="sect">
    <span class="t">코멘트</span>
  </div>
  <div class="cmt edit" contenteditable="true" data-edit="comment">
    광공업생산 전월비 +3.9%, 전년비 ±x.x% — 회복 흐름 지속.
    조업일수 nn일 (전월대비 ±n일, 전년대비 ±n일)
    수출 xxx억달러 (전월 ±xx억달러), 전년동기비 ±xx.x% 증가.
    수입 xxx억달러 (전월 ±xx억달러), 전년비 ±x.x% 증가.
    무역수지 ±xxx억달러 흑자 · 경상수지 ±xxx억달러 흑자.
    반도체 — 서버·메모리·가격 코멘트 (관련 품목 전년비 ±xx.x%).
  </div>

  <div class="cons-line">
    <span class="cons-tag">컨센서스</span>{cons}
  </div>

</div>

<div class="toolbar" data-noprint>
  <button onclick="savePDF()" class="tb-primary">PDF로 저장</button>
  <button onclick="restoreRows()">행 복원</button>
  <button onclick="resetAll()">원본 복원</button>
  <span class="tb-note">[PDF로 저장] 클릭 → 인쇄 대화상자에서 대상을 "PDF로 저장(Save as PDF)"으로 선택 후 저장. 요약·코멘트·컨센서스는 클릭해 편집. 표의 × 로 행 삭제(세션 한정). 편집 내용은 브라우저에 자동 저장되며 원본 데이터(CSV·JSON)에는 영향 없음.</span>
</div>

<script>
(function() {{
  var KEY = "ip_report_edits_v1";

  function save() {{
    var data = {{ fields:{{}} }};
    document.querySelectorAll("[data-edit]").forEach(function(el) {{
      data.fields[el.getAttribute("data-edit")] = el.innerHTML;
    }});
    try {{ localStorage.setItem(KEY, JSON.stringify(data)); }} catch(e) {{}}
  }}

  function load() {{
    var raw;
    try {{ raw = localStorage.getItem(KEY); }} catch(e) {{ return; }}
    if (!raw) return;
    var data = JSON.parse(raw);
    Object.keys(data.fields || {{}}).forEach(function(k) {{
      var el = document.querySelector('[data-edit="' + k + '"]');
      // [핵심 수정] 저장된 값이 비어있지 않을 때만 복원하여 기본 텍스트가 날아가는 것을 방지
      var val = data.fields[k];
      if (el && val && val.trim() !== "" && val !== "<br>") {{
        el.innerHTML = val;
      }}
    }});
  }}

  window.dropRow = function(btn) {{
    btn.closest("tr").style.display = "none";
  }};

  window.restoreRows = function() {{
    document.querySelectorAll("tbody tr").forEach(function(tr) {{
      tr.style.display = "";
    }});
  }};

  window.resetAll = function() {{
    try {{ localStorage.removeItem(KEY); }} catch(e) {{}}
    location.reload();
  }};

  window.savePDF = function() {{
    window.print();
  }};

  document.addEventListener("input", function(e) {{
    if (e.target.closest("[data-edit]")) {{ save(); }}
  }});

  load();
}})();
</script>
</body></html>
"""