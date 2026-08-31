# -*- coding: utf-8 -*-
"""산업생산 리서치 노트 HTML 렌더러.

국내 리서치 하우스 스타일.
나눔스퀘어 서체, 절제된 색조, 한글 표기,
단어 내 줄바꿈 없음. 출처는 KOSIS.

주의:
_TEMPLAGE는 str.format()으로 렌더링되므로
CSS/JavaScript의 중괄호는 반드시 {{ }} 형태로 작성한다.
"""

from __future__ import annotations

import datetime as dt

import numpy as np


def _is_na(v):
    """None / NaN 여부."""
    if v is None:
        return True

    try:
        return bool(np.isnan(v))
    except (TypeError, ValueError):
        return False


def _sign(v, dp=1):
    """부호가 있는 숫자를 HTML span으로 출력."""
    if _is_na(v):
        return '<span class="na">-</span>'

    cls = (
        "up"
        if v > 0
        else "dn"
        if v < 0
        else "fl"
    )

    sgn = "+" if v > 0 else ""

    return (
        f'<span class="{cls}">'
        f'{sgn}{v:.{dp}f}'
        f"</span>"
    )


def _plain(v, dp=1):
    """부호 없이 일반 숫자로 출력."""
    if _is_na(v):
        return "-"

    return f"{v:.{dp}f}"


CONS_LABELS = {
    "consensus_YoY": "컨센서스",
    "min_YoY": "최소",
    "max_YoY": "최대",
    "median_YoY": "중앙값",
}

AVG_LABELS = {
    "3mo": "3개월",
    "6mo": "6개월",
    "1yr": "1년",
    "2yr": "2년",
}


def render(R, C) -> str:
    prod = R["prod"]
    yoy = R["yoy"]
    ai = R["all_ind"]

    last_actual = R["last_actual"]

    # ------------------------------------------------------------------
    # forecast_month 우선.
    # 새 build_table.py는 forecast_month를 사용하고,
    # 기존 build_table.py는 future_month를 사용할 수 있으므로
    # 둘 다 호환한다.
    # ------------------------------------------------------------------
    forecast_month = R.get("forecast_month")

    if forecast_month is None:
        forecast_month = R.get("future_month")

    # ------------------------------------------------------------------
    # 최근 N개월
    # ------------------------------------------------------------------
    n = min(
        C.TABLE_MONTHS,
        len(ai),
    )

    idx = ai.index[-n:]

    products = [
        p
        for p in C.PRODUCT_ORDER
        if p in prod.columns
    ]

    today = dt.date.today().strftime(
        "%Y-%m-%d"
    )

    # ------------------------------------------------------------------
    # header
    # ------------------------------------------------------------------
    prod_head = "".join(
        f"<th>{p}</th>"
        for p in products
    )

    # ------------------------------------------------------------------
    # table rows
    # ------------------------------------------------------------------
    rows = []

    for d in idx:

        is_last_actual = (
            d == last_actual
        )

        is_forecast = (
            forecast_month is not None
            and d == forecast_month
        )

        # 실제 발표 여부와 관계없이
        # forecast_month는 전망 행으로 표시한다.
        rcls = (
            " class='r-last'"
            if is_last_actual
            else (
                " class='r-proj'"
                if is_forecast
                else ""
            )
        )

        # --------------------------------------------------------------
        # 품목 YoY
        #
        # 전망 대상월이라도 실제 품목 데이터가 있으면 표시한다.
        # 즉 "전망월 = 무조건 blank"가 아니다.
        # --------------------------------------------------------------
        cells = "".join(
            (
                f"<td>{_sign(yoy.loc[d, p])}</td>"
                if d in yoy.index
                and p in yoy.columns
                and not _is_na(yoy.loc[d, p])
                else "<td class='na'>-</td>"
            )
            for p in products
        )

        # --------------------------------------------------------------
        # 최신 실제 행 강조
        # --------------------------------------------------------------
        b0, b1 = (
            ("<b>", "</b>")
            if is_last_actual
            else ("", "")
        )

        act_y = ai.loc[
            d,
            "actual_YoY_%"
        ]

        act_m = ai.loc[
            d,
            "actual_MoM_%"
        ]

        # 실제값이 존재하면 표시.
        # 전망월이라는 이유만으로 실제값을 지우지 않는다.
        actual_y = (
            f"{b0}{_sign(act_y)}{b1}"
            if not _is_na(act_y)
            else "<span class='na'>-</span>"
        )

        actual_m = (
            f"{b0}{_sign(act_m)}{b1}"
            if not _is_na(act_m)
            else "<span class='na'>-</span>"
        )

        # --------------------------------------------------------------
        # date label
        # --------------------------------------------------------------
        dt_lbl = d.strftime(
            "%Y.%m"
        )

        if is_forecast:
            dt_lbl += (
                "<span class='tag-p'>"
                "(E)"
                "</span>"
            )

        # --------------------------------------------------------------
        # forecast / adjusted forecast
        # --------------------------------------------------------------
        proj_yoy = ai.loc[
            d,
            "proj_YoY_%"
        ]

        proj_mom = ai.loc[
            d,
            "proj_MoM_%"
        ]

        adjproj_yoy = ai.loc[
            d,
            "adjproj_YoY_%"
        ]

        rows.append(
            f"<tr{rcls}>"
            f"<td class='dt'>"

            f"<button "
            f"class='xbtn' "
            f"onclick='dropRow(this)' "
            f"title='행 삭제' "
            f"data-noprint>"
            f"&times;"
            f"</button>"

            f"{dt_lbl}"
            f"</td>"

            f"{cells}"

            f"<td class='sep'>"
            f"{actual_y}"
            f"</td>"

            f"<td>"
            f"{actual_m}"
            f"</td>"

            f"<td class='sep'>"
            f"{_sign(proj_yoy)}"
            f"</td>"

            f"<td>"
            f"{_sign(proj_mom)}"
            f"</td>"

            f"<td class='sep'>"
            f"{_sign(adjproj_yoy)}"
            f"</td>"

            f"</tr>"
        )

    body = "\n".join(rows)

    # ------------------------------------------------------------------
    # consensus
    # ------------------------------------------------------------------
    cons = "".join(
        (
            f"<div class='cell'>"
            f"<span class='k'>"
            f"{CONS_LABELS.get(f, f)}"
            f"</span>"
            f"<span "
            f"class='v blank edit' "
            f"contenteditable='true' "
            f"data-edit='cons_{f}'"
            f">&nbsp;</span>"
            f"</div>"
        )
        for f in C.CONSENSUS_FIELDS
    )

    # ------------------------------------------------------------------
    # trailing averages
    # ------------------------------------------------------------------
    avgs = "".join(
        (
            f"<div class='cell'>"
            f"<span class='k'>"
            f"{AVG_LABELS.get(k, k)}"
            f"</span>"
            f"<span class='v'>"
            f"{_plain(v)}"
            f"{'' if _is_na(v) else '%'}"
            f"</span>"
            f"</div>"
        )
        for k, v in R["avgs"].items()
    )

    # ------------------------------------------------------------------
    # table widths
    # ------------------------------------------------------------------
    colgroup = (
        "<col class='c-dt'>"
    )

    colgroup += "".join(
        "<col class='c-prod'>"
        for _ in products
    )

    colgroup += "".join(
        "<col class='c-stat'>"
        for _ in range(5)
    )

    prod_w = (
        f"{round(62.0 / max(len(products), 1), 3)}%"
    )

    # ------------------------------------------------------------------
    # bridge diagnostics
    # ------------------------------------------------------------------
    bs = R.get("bridge")

    if (
        bs
        and forecast_month is not None
    ):

        bridge_note = (
            "전망(E)은 수출물량 브릿지 회귀 "
            "나우캐스트: "
            f"생산 전년비 = "
            f"{bs['alpha']:.1f} + "
            f"{bs['beta']:.2f}×수출 전년비 "
            f"(표본 {bs['n_obs']}개월). "
            f"해당월 수출 전년비 "
            f"{bs['export_yoy']:+.1f} "
            f"→ 생산 전년비 "
            f"{bs['bridge_yoy']:+.1f}."
        )

    else:

        bridge_note = (
            "수출물량 데이터가 부족하여 "
            "전망 나우캐스트를 생성하지 못했습니다."
        )

    # ------------------------------------------------------------------
    # IMPORTANT
    #
    # 아래 _TEMPLATE는 .format()을 사용한다.
    # 따라서 CSS/JS의 모든 { }는 {{ }}로 escape되어 있다.
    # ------------------------------------------------------------------
    return _TEMPLATE.format(
        today=today,
        n=n,
        prod_head=prod_head,
        body=body,
        cons=cons,
        avgs=avgs,
        colgroup=colgroup,
        prod_w=prod_w,
        bridge_note=bridge_note,
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">

<head>
<meta charset="utf-8">

<title>산업생산 동향</title>

<link
  href="https://cdn.jsdelivr.net/gh/moonspam/NanumSquare@2.0/nanumsquare.css"
  rel="stylesheet"
>

<style>

@page {{
  size: A4 portrait;
  margin: 14mm;
}}

:root {{
  --ink:#1a1a1a;
  --hd:#12432b;
  --hd2:#1a5638;
  --rule:#c9cdd2;
  --soft:#f4f7f4;
  --band:#fafbfa;
  --acc:#12432b;
  --up:#c0392b;
  --dn:#1b5faa;
  --mut:#6a7078;
}}

* {{
  box-sizing:border-box;
}}

html,
body {{
  margin:0;
  padding:0;
}}

body {{
  font-family:
    'NanumSquare',
    'Malgun Gothic',
    sans-serif;

  color:var(--ink);
  background:#fff;

  -webkit-print-color-adjust:exact;
  print-color-adjust:exact;
}}

.page {{
  width:182mm;
  margin:0 auto;
}}

.masthead {{
  border-bottom:2.5px solid var(--hd);
  padding-bottom:7px;
  margin-bottom:3px;

  display:flex;
  align-items:flex-end;
  justify-content:space-between;
}}

.masthead h1 {{
  font-size:23px;
  font-weight:800;
  margin:0;
  letter-spacing:-.5px;
  color:var(--hd);
}}

.masthead .meta {{
  font-size:10px;
  color:var(--mut);
  text-align:right;
  line-height:1.5;
  white-space:nowrap;
}}

.lede {{
  font-size:11px;
  color:#40454b;
  margin:6px 0 12px;
  font-weight:600;
  line-height:1.5;
}}

.band {{
  display:grid;
  grid-template-columns:74px repeat(4,1fr);
  gap:0;

  border:1px solid var(--rule);
  border-left:3px solid var(--acc);

  margin-bottom:6px;
}}

.band .tag {{
  background:var(--soft);
  font-size:10px;
  font-weight:800;
  color:var(--hd);

  display:flex;
  align-items:center;

  padding:0 10px;

  border-right:1px solid var(--rule);

  white-space:nowrap;
  line-height:1.3;
}}

.band .cell {{
  padding:6px 10px;

  border-right:1px solid var(--rule);

  display:flex;
  flex-direction:column;
  gap:2px;
}}

.band .cell:last-child {{
  border-right:0;
}}

.band .k {{
  font-size:9.5px;
  color:var(--mut);
  font-weight:700;
  white-space:nowrap;
}}

.band .v {{
  font-size:14px;
  font-weight:800;
  color:var(--ink);
}}

.band .v.blank {{
  height:15px;
}}

.sect {{
  display:flex;
  align-items:baseline;
  justify-content:space-between;

  background:var(--hd);
  color:#fff;

  padding:5px 10px;
  margin-top:12px;
}}

.sect .t {{
  font-size:11.5px;
  font-weight:800;
  letter-spacing:.3px;
}}

.sect .u {{
  font-size:9.5px;
  font-weight:700;
  color:#c6d0dd;
}}

table {{
  border-collapse:collapse;
  width:100%;

  font-size:9px;

  table-layout:fixed;
}}

col.c-dt {{
  width:52px;
}}

col.c-prod {{
  width:{prod_w};
}}

col.c-stat {{
  width:38px;
}}

thead th {{
  background:var(--hd2);
  color:#fff;

  font-weight:700;

  padding:5px 1px;

  text-align:right;

  border:1px solid #2b6a47;

  line-height:1.15;

  overflow:hidden;

  font-size:8.5px;
}}

thead th:first-child {{
  text-align:center;
}}

tbody td {{
  padding:4px 2px;

  text-align:right;

  border:1px solid var(--rule);

  white-space:nowrap;
  overflow:hidden;
}}

tbody tr:nth-child(even) {{
  background:var(--band);
}}

td.dt {{
  text-align:center;

  font-weight:800;
  color:var(--hd);

  background:var(--soft);
}}

tbody tr:nth-child(even) td.dt {{
  background:#e7ede8;
}}

td.sep {{
  border-left:2px solid var(--hd);
}}

thead th.sep {{
  border-left:2px solid #3f7a58;
}}

.up {{
  color:var(--up);
  font-weight:700;
}}

.dn {{
  color:var(--dn);
  font-weight:700;
}}

.fl {{
  color:#555;
}}

.na {{
  color:#b7bcc2;
}}

tr.r-last td {{
  background:#eaf3ec !important;
}}

tr.r-last td.dt {{
  background:#d7e7db !important;
}}

tr.r-last b {{
  font-weight:800;
}}

tr.r-proj td {{
  background:#fbfaf3 !important;
  font-style:normal;
}}

tr.r-proj td.dt {{
  background:#f2eede !important;
  color:#7a6a1e;
}}

.tag-p {{
  font-size:8px;
  color:#7a6a1e;

  margin-left:2px;

  vertical-align:top;
}}

.foot {{
  font-size:9px;
  color:var(--mut);

  margin-top:5px;

  line-height:1.55;
}}

.cmt {{
  border:1px solid var(--rule);
  border-left:3px solid var(--acc);

  background:var(--band);

  padding:9px 11px;

  font-size:10.5px;

  line-height:1.7;

  margin-top:2px;
}}

.cmt .lead {{
  font-weight:800;
  color:var(--hd);
}}

.cmt .fill {{
  font-size:9px;
  color:var(--mut);

  margin-top:5px;
}}

.edit {{
  outline:none;
}}

.edit:hover {{
  background:#fffde9;
}}

.edit:focus {{
  background:#fffdf0;

  box-shadow:
    inset 0 0 0 1px #b7a94a;
}}

.cmt.edit {{
  cursor:text;
}}

.cmt.edit:hover {{
  background:#fbfaf0;
}}

span.v.edit {{
  display:inline-block;
  min-width:60px;
  cursor:text;
}}

td.dt {{
  position:relative;
}}

.xbtn {{
  position:absolute;

  left:1px;
  top:50%;

  transform:translateY(-50%);

  border:none;

  background:transparent;

  color:#c0392b;

  font-size:12px;

  line-height:1;

  cursor:pointer;

  padding:0 2px;

  font-weight:800;

  opacity:0;
}}

tr:hover .xbtn {{
  opacity:1;
}}

.xbtn:hover {{
  color:#fff;
  background:#c0392b;
  border-radius:2px;
}}

.toolbar {{
  max-width:182mm;

  margin:14px auto 30px;

  padding:10px 12px;

  background:#eef3ef;

  border:1px solid var(--rule);
  border-left:3px solid var(--acc);

  display:flex;

  align-items:center;

  gap:10px;

  flex-wrap:wrap;
}}

.toolbar button {{
  font-family:inherit;

  font-size:11px;

  font-weight:800;

  padding:7px 14px;

  border:1px solid var(--hd);

  background:#fff;

  color:var(--hd);

  border-radius:3px;

  cursor:pointer;
}}

.toolbar button.tb-primary {{
  background:var(--hd);
  color:#fff;
}}

.toolbar button:hover {{
  opacity:.88;
}}

.toolbar .tb-note {{
  font-size:10px;
  color:var(--mut);
  line-height:1.4;
}}

@media print {{

  [data-noprint] {{
    display:none !important;
  }}

  .edit:hover,
  .edit:focus {{
    background:transparent !important;
    box-shadow:none !important;
  }}

  .toolbar {{
    display:none !important;
  }}

  body {{
    -webkit-print-color-adjust:exact;
    print-color-adjust:exact;
  }}

}}

</style>
</head>

<body>

<div class="page">

  <div class="masthead">

    <h1>
      산업생산 동향
    </h1>

    <div class="meta">
      출처: KOSIS<br>
      작성일: {today}
    </div>

  </div>


  <div class="lede">
    전산업 및 주요 품목 생산지수
    &mdash;
    전년동월비 및 전월비,
    실적 대 전망 비교.
  </div>


  <div class="band">

    <div class="tag">
      컨센서스
    </div>

    {cons}

  </div>


  <div class="band">

    <div class="tag">
      전산업<br>
      전년비 평균
    </div>

    {avgs}

  </div>


  <div class="sect">

    <span class="t">
      주요 품목 전년동월비 · 전산업 실적 대 전망
    </span>

    <span class="u">
      단위: %
    </span>

  </div>


  <table>

    <colgroup>
      {colgroup}
    </colgroup>

    <thead>

      <tr>

        <th>
          날짜
        </th>

        {prod_head}

        <th class="sep">
          실적<br>
          전년비
        </th>

        <th>
          실적<br>
          전월비
        </th>

        <th class="sep">
          전망<br>
          전년비
        </th>

        <th>
          전망<br>
          전월비
        </th>

        <th class="sep">
          조정전망<br>
          전년비
        </th>

      </tr>

    </thead>

    <tbody>

      {body}

    </tbody>

  </table>


  <div class="foot">

    선박은 강선 기준 대용치.
    광공업생산(실적)은 전산업 생산 실적.

    <br>

    {bridge_note}

  </div>


  <div class="sect">

    <span class="t">
      코멘트
    </span>

  </div>


  <div
    class="cmt edit"
    contenteditable="true"
    data-edit="comment"
  >

    <span class="lead">
      [월] 광공업생산 전월비 [+x.x],
      전년비 [±x.x].
    </span>

    (조업일수 [nn]일,
    전월대비 [±n]일,
    전년대비 [±n]일)

    <br>

    [월] 수출 [금액]억달러
    (전월 [±xx]억달러),
    전년동기비 [±xx.x] 증가.

    <br>

    [월] 수입 [금액]억달러
    (전월 [±xx]억달러),
    전년비 [±x.x] 증가.

    <br>

    [월] 무역수지 [±xxx]억달러 흑자,
    경상수지 [±xxx]억달러 흑자.

    <br>

    반도체는
    [서버·메모리·가격 코멘트]
    (관련 품목 전년비 [±xx.x]).

    <div class="fill" data-noprint>
      대괄호 항목은 월별 발표치로 채워 사용.
      이 영역은 직접 편집 가능.
    </div>

  </div>

</div>


<div
  class="toolbar"
  data-noprint
>

  <button
    onclick="window.print()"
    class="tb-primary"
  >
    PDF 저장
  </button>

  <button
    onclick="resetAll()"
  >
    원본 복원
  </button>

  <span class="tb-note">
    코멘트·컨센서스 칸은 클릭해 편집.
    표의 × 로 행 삭제.
    편집 내용은 브라우저에 자동 저장되며
    원본 데이터(CSV·JSON)에는 영향 없음.
  </span>

</div>


<script>

(function() {{

  var KEY = "ip_report_edits_v1";


  function save() {{

    var data = {{
      fields: {{}},
      dropped: []
    }};


    document
      .querySelectorAll("[data-edit]")
      .forEach(function(el) {{

        data.fields[
          el.getAttribute("data-edit")
        ] = el.innerHTML;

      }});


    document
      .querySelectorAll("tbody tr")
      .forEach(function(tr, i) {{

        if (
          tr.style.display === "none"
        ) {{

          data.dropped.push(i);

        }}

      }});


    try {{

      localStorage.setItem(
        KEY,
        JSON.stringify(data)
      );

    }} catch(e) {{}}

  }}


  function load() {{

    var raw;


    try {{

      raw = localStorage.getItem(KEY);

    }} catch(e) {{

      return;

    }}


    if (!raw) return;


    var data;

    try {{

      data = JSON.parse(raw);

    }} catch(e) {{

      return;

    }}


    Object
      .keys(data.fields || {{}})
      .forEach(function(k) {{

        var el =
          document.querySelector(
            '[data-edit="' + k + '"]'
          );


        if (el) {{

          el.innerHTML =
            data.fields[k];

        }}

      }});


    var rows =
      document.querySelectorAll(
        "tbody tr"
      );


    (data.dropped || [])
      .forEach(function(i) {{

        if (rows[i]) {{

          rows[i].style.display =
            "none";

        }}

      }});

  }}


  window.dropRow = function(btn) {{

    var tr =
      btn.closest("tr");


    if (!tr) return;


    tr.style.display =
      "none";


    save();

  }};


  window.resetAll = function() {{

    try {{

      localStorage.removeItem(KEY);

    }} catch(e) {{}}


    location.reload();

  }};


  document.addEventListener(
    "input",
    function(e) {{

      if (
        e.target.closest(
          "[data-edit]"
        )
      ) {{

        save();

      }}

    }}
  );


  load();

}})();

</script>

</body>
</html>
"""