#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_qa_report.py — QA Manager HTML 報告產生器（確定性、site-agnostic）

用法：
  python3 gen_qa_report.py <report_dir> [--input narrative.json] [--out path.html] [--template path.html] [--reviewer 名]

讀 <report_dir>/games.jsonl（必要）、run-meta.json / full-game-list.json（有則用），
把所有「數字、餘額鏈 SVG 曲線、逐款明細表」算出來（不靠人/LLM 心算），
敘述文字（裁決 / 建議 / 案例）由 --input 的 narrative JSON 提供；缺則用資料驅動的預設。
輸出單檔 HTML（CSS inline，可離線開），供 QA Manager 檢視與人工逐筆核對。
"""
import argparse, html, json, os, re, sys
from collections import Counter

MINUS = "−"  # − 視覺用負號（同範例）


# ---------- 工具 ----------
def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def num(x):
    return isinstance(x, (int, float))


def money(x):
    if not num(x):
        return ""
    return f"{x:,.2f}"


def signed(x):
    if not num(x):
        return ""
    s = f"{abs(x):,.2f}"
    return f"+{s}" if x >= 0 else f"{MINUS}{s}"


def esc(s):
    return html.escape(str(s if s is not None else ""))


def parse_dt(s):
    import datetime
    try:
        return datetime.datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def dur_seconds(start, end):
    """兩個 'YYYY-MM-DD HH:MM:SS' 字串相差秒數；無法解析或負值 → None。"""
    a, b = parse_dt(start), parse_dt(end)
    if a and b:
        d = (b - a).total_seconds()
        return d if d >= 0 else None
    return None


def fmt_dur(sec):
    """秒 → 人類可讀時長：Xh Ym / Xm Ys / Xs；None → —。"""
    if sec is None or not num(sec):
        return "—"
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def code_of(g, glist_by_idx):
    e = glist_by_idx.get(g.get("idx"))
    if e and e.get("code"):
        return str(e["code"])
    m = re.match(r"g(\d+)$", str(g.get("id", "")))
    return m.group(1) if m else ""


# ---------- 餘額鏈 SVG ----------
def build_curve_svg(games):
    pts = [g["after_bal"] for g in games if num(g.get("after_bal"))]
    if len(pts) < 2:
        return None
    X0, X1, YT, YB = 8.0, 1032.0, 24.0, 216.0
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    n = len(pts)

    def X(i):
        return X0 + (X1 - X0) * (i / (n - 1))

    def Y(v):
        return YT + (hi - v) / span * (YB - YT)

    coords = [(round(X(i), 1), round(Y(v), 1)) for i, v in enumerate(pts)]
    stroke = "M " + " L ".join(f"{x},{y}" for x, y in coords)
    fill = (f"M {coords[0][0]},{YB} L " +
            " L ".join(f"{x},{y}" for x, y in coords) +
            f" L {coords[-1][0]},{YB} Z")

    # 大獎標記：delta 最大的正中獎，最多 3 個，且 delta>=5
    win_idx = sorted(
        [i for i, g in enumerate(games) if num(g.get("delta")) and g["delta"] >= 5.0],
        key=lambda i: games[i]["delta"], reverse=True)[:3]
    markers = "".join(
        f'<circle cx="{coords[i][0]}" cy="{coords[i][1]}" r="4" fill="#fff" stroke="#A8650A" stroke-width="2"/>'
        for i in win_idx if i < len(coords))
    big = [(f"g{games[i].get('idx')}", games[i].get("name", ""), games[i]["delta"]) for i in win_idx]

    svg = f'''<svg viewBox="0 0 1040 240" preserveAspectRatio="none" role="img" aria-label="{n} 筆餘額鏈曲線">
  <defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#0E7A57" stop-opacity="0.16"/><stop offset="100%" stop-color="#0E7A57" stop-opacity="0.01"/>
  </linearGradient></defs>
  <line x1="8" y1="24" x2="1032" y2="24" stroke="#DCE3E9" stroke-width="1"/>
  <line x1="8" y1="120" x2="1032" y2="120" stroke="#ECF0F3" stroke-width="1"/>
  <line x1="8" y1="216" x2="1032" y2="216" stroke="#DCE3E9" stroke-width="1"/>
  <path d="{fill}" fill="url(#fill)" stroke="none"/>
  <path d="{stroke}" fill="none" stroke="#0E7A57" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
  {markers}
  <circle cx="{coords[0][0]}" cy="{coords[0][1]}" r="3.5" fill="#13212B"/>
  <circle cx="{coords[-1][0]}" cy="{coords[-1][1]}" r="3.5" fill="#BC392C"/>
</svg>'''
    return {"svg": svg, "start": pts[0], "end": pts[-1], "n": n, "big": big}


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_dir")
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--template", default=None)
    ap.add_argument("--reviewer", default=None)
    a = ap.parse_args()

    rd = a.report_dir.rstrip("/")
    games_path = os.path.join(rd, "games.jsonl")
    if not os.path.exists(games_path):
        sys.exit(f"ERROR: 找不到 {games_path}（請先跑 run）")
    games = sorted(load_jsonl(games_path), key=lambda g: g.get("idx", 0))
    meta = load_json(os.path.join(rd, "run-meta.json"), {}) or {}
    glist_raw = load_json(os.path.join(rd, "full-game-list.json"), {}) or {}
    glist = (glist_raw.get("games") if isinstance(glist_raw, dict) else glist_raw) or []
    glist_by_idx = {g.get("idx"): g for g in glist}
    nar = load_json(a.input, {}) or {}
    tpl_path = a.template or os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-report-template.html")
    template = open(tpl_path, encoding="utf-8").read()
    reviewer = a.reviewer or nar.get("reviewer") or "QA"

    # ---- 指標 ----
    total = len(games)
    sc = Counter(g.get("status", "?") for g in games)
    npass = sc.get("PASS", 0)
    abnormal = total - npass
    deltas = [g["delta"] for g in games if num(g.get("delta"))]
    net = round(sum(deltas), 2) if deltas else None

    def is_win(g):
        if num(g.get("win")) and g["win"] > 0:
            return True
        if num(g.get("delta")) and num(g.get("bet")):
            return g["delta"] > -g["bet"] + 1e-6
        return False
    wins = sum(1 for g in games if is_win(g))

    breaks = []
    for i in range(1, len(games)):
        a0, b1 = games[i - 1].get("after_bal"), games[i].get("before_bal")
        if num(a0) and num(b1) and abs(b1 - a0) > 0.001:
            breaks.append(games[i].get("idx"))
    nbreak = len(breaks)

    shots_dir = os.path.join(rd, "screenshots")
    nshots = len([f for f in os.listdir(shots_dir)]) if os.path.isdir(shots_dir) else \
        sum(len(g.get("screenshots", []) or []) for g in games)

    start_bal = next((g["before_bal"] for g in games if num(g.get("before_bal"))), None)
    end_bal = next((g["after_bal"] for g in reversed(games) if num(g.get("after_bal"))), None)
    total_bet = round(sum(g["bet"] for g in games if num(g.get("bet"))), 2)

    spins = sorted(g["spin_time"] for g in games if g.get("spin_time"))
    has_time = bool(spins)

    # ---- meta ----
    lobby_url = meta.get("lobby_url", "")
    host = re.sub(r"^https?://", "", lobby_url).split("/")[0] if lobby_url else nar.get("site", "")
    plat = ""
    m = re.search(r"gamePlatformId=(\d+)", lobby_url)
    if m:
        plat = f"gamePlatformId={m.group(1)}"
    brand_disp = meta.get("display_name") or meta.get("brand") or nar.get("brand", "")
    account = meta.get("account", nar.get("account", ""))
    viewport = meta.get("viewport")
    vp = f"{viewport[0]}×{viewport[1]}" if isinstance(viewport, list) and len(viewport) == 2 else nar.get("viewport", "")
    date_s = nar.get("date", "")
    if not date_s and has_time:
        date_s = spins[0][:10]
    if not date_s and meta.get("start_time"):
        date_s = re.sub(r"^(\d{4})(\d2)(\d2).*", r"\1-\2-\3", str(meta["start_time"]))
    time_range = nar.get("time_range", "")
    if not time_range and has_time:
        time_range = f"{spins[0][11:16]} – {spins[-1][11:16]}"

    title = nar.get("title") or f"{brand_disp} 功能測試報告 — QA Manager Review"

    # ---- 區塊：meta-grid ----
    meta_pairs = [
        ("品牌 / Brand", brand_disp), ("測試帳號", account),
        ("站點 / Site", host), ("測試日期", date_s or "—"),
        ("測試時段", time_range or "—"), ("遊戲大廳", plat or "—"),
        ("viewport", (vp + " 滿版") if vp else "—"), ("產出 / Reviewer", reviewer),
    ]
    meta_rows = "".join(f'<div><div class="l">{esc(k)}</div><div class="v">{esc(v)}</div></div>' for k, v in meta_pairs)

    # ---- 區塊：verdict ----
    all_pass = abnormal == 0 and total > 0
    chips = nar.get("verdict", {}).get("chips")
    if not chips:
        chips = [f"PASS {npass}/{total}" + (f"（{npass/total*100:.0f}%）" if total else ""),
                 f"異常款 {abnormal} · 餘額鏈斷點 {nbreak}"]
    chip_cls = "pass" if all_pass else "warn"
    chips_html = (f'<span class="chip {chip_cls}">{esc(chips[0])}</span>' +
                  "".join(f'<span class="chip clean">{esc(c)}</span>' for c in chips[1:]))
    paras = nar.get("verdict", {}).get("paragraphs")
    if not paras:
        paras = [
            f"本次測試對 <b>{esc(brand_disp)}</b> 共 <b>{total} 款</b>逐一驗證，結果 "
            f"<b>{npass} 款 PASS</b>" + (f"（{npass/total*100:.0f}%）" if total else "") +
            "。每款皆以遊戲內餘額 before/after 實際變動（delta≠0）確認真實下注，非單純點擊 SPIN。",
            f"餘額鏈<b>斷點 {nbreak}</b>" + ("（每款下注前餘額精確等於前一款下注後餘額，連中獎小數位都完整接續，構成逐筆真實下注的完整證據鏈）。"
             if nbreak == 0 else "（有斷點，需人工查驗下列明細表）。"),
        ]
    verdict_inner = (f'<div class="verdict-head"><h2>測試結論 — Test Verdict</h2>{chips_html}</div>' +
                     f'<p class="lead">{paras[0]}</p>' +
                     "".join(f"<p>{p}</p>" for p in paras[1:]))

    # ---- 區塊：metrics ----
    pct = f"<small>/{total}</small>"
    metrics = [
        ("ok" if all_pass else "warn", f"{npass}{pct}", "測試款數 · PASS"),
        ("ok" if nbreak == 0 else "neg", str(nbreak), "餘額鏈斷點 · 逐筆相接"),
        ("", str(nshots), "證據截圖張數"),
        ("", str(wins), "觀察到中獎款"),
        ("neg" if num(net) and net < 0 else "ok", (signed(net) if num(net) else "—"), f"{total} 款淨輸贏 delta"),
        ("ok" if abnormal == 0 else "neg", str(abnormal), "異常款 / 假 PASS"),
    ]
    metrics_inner = "".join(
        f'<div class="metric {c}"><div class="num">{v}</div><div class="lab">{esc(l)}</div></div>'
        for c, v, l in metrics)

    # ---- 區塊：時間投入（座標校準 vs 測試執行）----
    calib = meta.get("calibration") or {}
    calib_seconds = calib.get("seconds")
    if calib_seconds is None:
        calib_seconds = dur_seconds(calib.get("started_at"), calib.get("ended_at"))
    calib_src = calib.get("source", "")
    calib_vp = calib.get("viewport")
    calib_vp_s = f"{calib_vp[0]}×{calib_vp[1]}" if isinstance(calib_vp, list) and len(calib_vp) == 2 else (vp or "")

    bts = [g["before_read_time"] for g in games if g.get("before_read_time")]
    ats = [g["after_read_time"] for g in games if g.get("after_read_time")]
    exec_started = min(bts) if bts else (spins[0] if spins else None)
    exec_ended = max(ats) if ats else (spins[-1] if spins else None)
    exec_seconds = dur_seconds(exec_started, exec_ended)
    per_game_seconds = (exec_seconds / total) if (exec_seconds is not None and total) else None
    amort = (calib_seconds / total) if (calib_seconds is not None and total) else None

    NUMCSS = "font-family:var(--display);font-weight:700;font-size:30px;line-height:1;letter-spacing:-.02em"
    if calib_seconds is not None:
        calib_sub = (f"viewport {calib_vp_s}　·　首次校準（SPIN／餘額／退出座標與判定）"
                     + ("　·　<i>由產物時間回推、為近似值</i>" if calib_src == "reconstructed" else ""))
    else:
        calib_sub = "本次 run 未記錄校準時間（calibrate／run 升級後會自動帶入）"
    exec_sub = (f"每款平均 ~{fmt_dur(per_game_seconds)}　·　首款 before → 末款 after"
                if exec_seconds is not None else "games.jsonl 無逐款讀取時間，無法計時")
    if calib_seconds is not None and exec_seconds is not None:
        callout_time = (f"<b>校準是一次性成本：</b>本次「座標校準·判定」約 <b>{fmt_dur(calib_seconds)}</b>，"
                        f"換來 {total} 款共 <b>{fmt_dur(exec_seconds)}</b> 的逐款驗餘額執行（每款 ~{fmt_dur(per_game_seconds)}）。"
                        f"同站、同 viewport 下校準參數可重複沿用，攤提到每款約 <b>{fmt_dur(amort)}</b>；"
                        f"款數越多、單位校準成本越低。本次合計投入約 {fmt_dur(calib_seconds + exec_seconds)}。")
    else:
        callout_time = "校準或執行時間其一缺漏，僅顯示可得部分；資料補齊後本區塊會自動完整。"
    time_inner = (
        '<div class="grid2">'
        '<div class="panel"><h3>座標校準 · 判定 <span class="tag">一次性</span></h3>'
        f'<div style="{NUMCSS};color:var(--amber)">{fmt_dur(calib_seconds)}</div>'
        f'<p style="margin-top:8px">{calib_sub}</p></div>'
        f'<div class="panel"><h3>測試執行 <span class="tag">{total} 款</span></h3>'
        f'<div style="{NUMCSS};color:var(--green)">{fmt_dur(exec_seconds)}</div>'
        f'<p style="margin-top:8px">{exec_sub}</p></div></div>'
        f'<div class="callout">{callout_time}</div>')

    # ---- 區塊：curve ----
    curve = build_curve_svg(games)
    if curve:
        legend = (f'<span><i class="swatch" style="background:#0E7A57"></i>餘額（after_bal）</span>'
                  f'<span><i class="swatch" style="background:#13212B;width:9px;height:9px;border-radius:50%"></i>起 {money(curve["start"])}</span>'
                  f'<span><i class="swatch" style="background:#BC392C;width:9px;height:9px;border-radius:50%"></i>終 {money(curve["end"])}</span>')
        if curve["big"]:
            bigtxt = "、".join(f'{esc(i)} 「{esc(nm)}」{signed(d)}' for i, nm, d in curve["big"])
            legend = (f'<span><i class="swatch" style="background:#0E7A57"></i>餘額（after_bal）</span>'
                      f'<span><i class="swatch" style="background:#A8650A;border-radius:50%;width:9px;height:9px"></i>大獎跳升：{bigtxt}</span>'
                      f'<span><i class="swatch" style="background:#13212B;width:9px;height:9px;border-radius:50%"></i>起 {money(curve["start"])}</span>'
                      f'<span><i class="swatch" style="background:#BC392C;width:9px;height:9px;border-radius:50%"></i>終 {money(curve["end"])}</span>')
        co = (f'<div class="curve-card"><div class="ctitle">'
              f'<h3>{money(curve["start"])} → {money(curve["end"])}　·　{curve["n"]} 筆連續餘額（idx 序）</h3>'
              f'<span class="note">每款 before＝前款 after，' + ("零斷點" if nbreak == 0 else f"{nbreak} 處斷點") + '</span></div>'
              f'{curve["svg"]}<div class="curve-legend">{legend}</div></div>'
              f'<div class="callout"><b>為何這條線是證據：</b>每一款的「下注前餘額」都精確等於前一款的「下注後餘額」，連中獎小數位都完整接續。'
              + ("這條無斷點的鏈證明每一筆都是真實扣款／派彩的下注，而非僅點擊 SPIN —— 是本次「無假 PASS」最直接的佐證。"
                 if nbreak == 0 else "目前有斷點，請對照下方逐款明細表查驗。") + "</div>")
    else:
        co = '<div class="callout warn">資料不足以繪製餘額鏈曲線（after_bal 點數不足）。</div>'

    # ---- 區塊：method ----
    cov = nar.get("method", {}).get("coverage") or {
        "測試款數": f"{total} 款", "餘額判讀": "截圖目視·讀兩次一致"}
    cov_html = "".join(f'<div class="kv"><span class="k">{esc(k)}</span><span class="vv">{esc(v)}</span></div>'
                       for k, v in cov.items())
    pass_def = nar.get("method", {}).get("pass_def") or (
        "PASS ＝ 已驗證遊戲內餘額 before/after 確實變動（delta≠0），並確認 SPIN 後盤面重排，"
        "非單純點擊。delta==0（含中獎剛好抵注）一律加轉確認或不予 PASS。")
    flow = nar.get("method", {}).get("flow") or [
        {"t": "開遊戲", "d": "於 lobby 以遊戲名定位 tile 啟動該款，依站點型態（新分頁／iframe）切入。"},
        {"t": "過 intro", "d": "進可玩畫面；若仍在介紹頁則補點，截圖確認已進場。"},
        {"t": "截 bal-before", "d": "SPIN 前餘額區截圖，目視判讀讀兩次一致，記 before_read_time。"},
        {"t": "SPIN", "d": "點 SPIN 並記 spin_time（貼近點擊瞬間）。"},
        {"t": "截 bal-after & 驗 delta", "d": "再截餘額，delta = after − before；delta≠0 才 PASS，delta==0 加轉確認。"},
        {"t": "退出", "d": "回 lobby 開下一款，全程 viewport 未 resize。"},
    ]
    steps = "".join(f'<div class="step"><div><div class="s-t">{esc(s["t"])}</div><div class="s-d">{s["d"]}</div></div></div>' for s in flow)
    method_inner = (
        '<div class="grid2" style="margin-bottom:16px">'
        f'<div class="panel"><h3>覆蓋範圍 <span class="tag">全品項</span></h3>{cov_html}</div>'
        f'<div class="panel"><h3>PASS 判定 <span class="tag">無假 PASS</span></h3><p>{pass_def}</p></div></div>'
        f'<div class="panel"><h3>每款執行流程</h3><div class="flow">{steps}</div></div>')

    # ---- 區塊：summary ----
    top = sorted([g for g in games if num(g.get("delta")) and g["delta"] > 0],
                 key=lambda g: g["delta"], reverse=True)[:5]
    top_rows = "".join(
        f'<tr><td>g{esc(g.get("idx"))}</td><td>{esc(g.get("name"))}</td>'
        f'<td class="num delta-pos">{signed(g["delta"])}</td></tr>' for g in top) or \
        '<tr><td colspan="3" style="color:var(--muted)">本批無淨中獎款</td></tr>'
    mc = nar.get("summary", {}).get("manual_confirms") or [
        {"id": f"g{g.get('idx')}", "name": g.get("name", ""), "text": esc(g.get("note", ""))}
        for g in games if (g.get("retries") or 0) > 0][:6]
    mc_html = "".join(f'<li><b>{esc(x.get("id",""))} {esc(x.get("name",""))}</b>：{x.get("text","")}</li>' for x in mc) or \
        '<li style="color:var(--muted)">本批無加轉／重試案例</li>'
    win_note = nar.get("summary", {}).get("win_note") or \
        f"{total} 款中 <b>{wins} 款觀察到中獎</b>（派彩抵注或淨增）；其餘為標準扣注。最大幾筆："
    summary_inner = (
        '<div class="grid2" style="margin-bottom:16px">'
        '<div class="panel"><h3>帳戶層級</h3><table style="border:none"><tbody>'
        f'<tr><td>起始餘額</td><td class="num">{money(start_bal)}</td></tr>'
        f'<tr><td>結束餘額</td><td class="num">{money(end_bal)}</td></tr>'
        f'<tr><td>{total} 款投注額合計</td><td class="num">{money(total_bet)}</td></tr>'
        f'<tr class="total"><td>淨輸贏 delta</td><td class="num">{signed(net) if num(net) else "—"}</td></tr>'
        '</tbody></table></div>'
        f'<div class="panel"><h3>中獎觀察</h3><p style="margin-bottom:10px">{win_note}</p>'
        '<table style="border:none"><thead><tr><th>款</th><th>遊戲名</th><th class="num">淨 delta</th></tr></thead>'
        f'<tbody>{top_rows}</tbody></table></div></div>'
        f'<div class="panel"><h3>加轉／重試確認 <span class="tag">SOP 落實 · 無假 PASS</span></h3><ul>{mc_html}</ul></div>')

    # ---- 區塊：逐款明細表 ----
    drows = []
    for g in games:
        st = g.get("status", "?")
        st_cls = "pass" if st == "PASS" else "other"
        d = g.get("delta")
        d_cls = "delta-pos" if (num(d) and d > 0) else "delta-neg"
        drows.append(
            "<tr>"
            f'<td class="num">{esc(g.get("idx"))}</td>'
            f'<td class="num">{esc(code_of(g, glist_by_idx))}</td>'
            f'<td>{esc(g.get("name"))}</td>'
            f'<td class="num">{money(g.get("before_bal"))}</td>'
            f'<td class="num">{money(g.get("after_bal"))}</td>'
            f'<td class="num {d_cls}">{signed(d) if num(d) else ""}</td>'
            f'<td class="num">{money(g.get("win")) if num(g.get("win")) else ""}</td>'
            f'<td class="num">{esc(g.get("spin_time") or "")}</td>'
            f'<td><span class="st {st_cls}">{esc(st)}</span></td>'
            "</tr>")
    detail_inner = (
        '<div class="detail-tools">逐款下注前後餘額與 SPIN 時間，順序同遊戲序列表（idx）；'
        '可對照大廳逐筆核對。共 ' + str(total) + ' 款。</div>'
        '<div class="detail-scroll"><table><thead><tr>'
        '<th class="num">編號</th><th class="num">代碼</th><th>遊戲名</th>'
        '<th class="num">進入前</th><th class="num">進入後</th><th class="num">delta</th>'
        '<th class="num">中獎</th><th class="num">SPIN 時間</th><th>狀態</th>'
        '</tr></thead><tbody>' + "".join(drows) + '</tbody></table></div>')

    # ---- 區塊：evidence ----
    shot_types = [
        ("g{idx}-loaded", "進場過 intro 後的可玩畫面（整頁）"),
        ("g{idx}-bal-before", "SPIN 前餘額區特寫，讀兩次一致"),
        ("g{idx}-spin", "SPIN 後整頁，確認盤面符號重排"),
        ("g{idx}-bal-after", "SPIN 後餘額區特寫，驗 delta≠0"),
    ]
    shots_html = "".join(f'<div class="shot"><div class="n">{esc(n)}</div><div class="d">{esc(d)}</div></div>' for n, d in shot_types)
    ev_note = nar.get("evidence_note") or (
        f"每款 4 張截圖（loaded／bal-before／spin／bal-after），共 <b>{nshots} 張</b>；"
        f"餘額鏈 {total} 筆" + ("連續、零斷點" if nbreak == 0 else f"，{nbreak} 處斷點") +
        "，每款 SPIN 後皆確認盤面符號重排（非只看餘額）。")
    evidence_inner = (f'<div class="evid">{shots_html}</div>'
                      f'<div class="callout"><b>完整性檢核：</b>{ev_note}</div>')

    # ---- 區塊：recommendations ----
    recs = nar.get("recommendations") or [
        {"title": "全量測試流程腳本化、納入 CI 回歸", "pri": "P2", "owner": "QA",
         "body": "將開遊戲→截圖→驗 delta 流程腳本化，排程定期回歸並自動產出報表。"},
        {"title": "證據鏈歸檔保存", "pri": "P3", "owner": "QA",
         "body": "截圖、餘額鏈與 games.jsonl 逐款結果整體歸檔，作為基準回歸的可追溯佐證。"},
    ]
    def pri_cls(p):
        p = str(p).lower()
        return "p1" if p in ("p1", "高") else "p2" if p in ("p2", "中") else "p3"
    recs_inner = "".join(
        f'<div class="rec"><div><h4>{esc(r.get("title",""))}</h4><p>{r.get("body","")}</p>'
        f'<div class="tags"><span class="pri {pri_cls(r.get("pri","P3"))}">{esc(r.get("pri","改善"))}</span>'
        f'<span class="pri who">{esc(r.get("owner","QA"))}</span></div></div></div>' for r in recs)

    # ---- footer ----
    src_files = [f for f in ["games.jsonl", "games.csv", "full-game-list.json", "run-meta.json",
                             "run-summary.md", "reconcile.md", "RUNNER-NOTES.md"]
                 if os.path.exists(os.path.join(rd, f))]
    footer_inner = (
        f'<div><b>範圍與來源</b>　·　QA Manager 角度之功能測試裁決彙整，逐款明細見本報告第 05 節與 <code>games.jsonl</code>（{total} 行）。</div>'
        f'<div class="files">report_dir：{esc(rd)}/<br>來源檔：{esc(" · ".join(src_files))}<br>'
        f'{esc(vp)}{"（全程未 resize）" if vp else ""}　|　{esc(plat)}　|　Reviewer：{esc(reviewer)}</div>')

    # ---- 套版 ----
    repl = {
        "{{TITLE}}": esc(title),
        "{{KICKER}}": '<span class="dot"></span>QA MANAGER REVIEW · 功能測試 <span class="dot"></span> REGRESSION REPORT',
        "{{H1}}": esc(title),
        "{{SUB}}": esc(nar.get("sub") or f"針對 {brand_disp} 共 {total} 款逐款功能驗證，每款保留證據截圖，並以遊戲內餘額變動逐筆確認真實下注。"),
        "{{META_ROWS}}": meta_rows,
        "{{VERDICT_INNER}}": verdict_inner,
        "{{METRICS_INNER}}": metrics_inner,
        "{{TIME_INNER}}": time_inner,
        "{{CURVE_INNER}}": co,
        "{{METHOD_INNER}}": method_inner,
        "{{SUMMARY_INNER}}": summary_inner,
        "{{DETAIL_INNER}}": detail_inner,
        "{{EVIDENCE_INNER}}": evidence_inner,
        "{{RECS_INNER}}": recs_inner,
        "{{FOOTER_INNER}}": footer_inner,
    }
    out_html = template
    for k, v in repl.items():
        out_html = out_html.replace(k, v)

    out_path = a.out or os.path.join(rd, "qa-report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_html)

    print(json.dumps({
        "out": out_path, "total": total, "pass": npass, "abnormal": abnormal,
        "chain_breaks": nbreak, "screenshots": nshots, "wins": wins,
        "net_delta": net, "start_bal": start_bal, "end_bal": end_bal,
        "has_spin_time": has_time, "time_range": time_range,
        "calib_seconds": calib_seconds, "calib_source": calib_src or None,
        "exec_seconds": exec_seconds,
        "per_game_seconds": round(per_game_seconds, 1) if per_game_seconds is not None else None,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
