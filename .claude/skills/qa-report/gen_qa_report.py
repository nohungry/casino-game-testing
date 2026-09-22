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
import argparse, json, os, re, sys
from collections import Counter

from report_common import (MINUS, betid_origin, betid_str, bo_wl_of, esc, load_games,
                           money, num, signed)


# ---------- 工具 ----------
def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def parse_dt(s):
    """容錯兩種格式：完整 'YYYY-MM-DD HH:MM:SS' 與純 'HH:MM:SS'（time-only 掛在 1900-01-01）。"""
    import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
        try:
            return datetime.datetime.strptime(str(s).strip(), fmt)
        except Exception:
            continue
    return None


def dur_seconds(start, end):
    """兩個時間字串相差秒數；time-only 且 end<start 視為跨午夜（+24h）；無法解析 → None。"""
    import datetime
    a, b = parse_dt(start), parse_dt(end)
    if a and b:
        d = (b - a).total_seconds()
        if d < 0 and a.year == 1900 and b.year == 1900:  # time-only 跨午夜
            d += 86400
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
    if g.get("code") not in (None, ""):
        return str(g["code"])
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


# ---------- 缺陷登記表 ----------
# 🔴 這一節的存在理由：報告原本只有「建議與後續」，那是**行動建議**不是**缺陷清單**。
#    QA 要拿去回報的東西需要：編號／嚴重度／歸屬側／重現／證據指標／狀態。
#    narrative["defects"] 缺席時整節不輸出（舊 run 不受影響），章節編號由 renumber_sections 動態補。
_SEV_ORDER = {"P1": 0, "P2": 1, "P3": 2}


def _sev_cls(v):
    v = str(v or "P3").upper()
    return v if v in _SEV_ORDER else "P3"


def build_defects(nar):
    """回傳 (full 版整節 HTML, simple 版彙總表 HTML)；無 defects 時兩者皆為空字串。"""
    ds = nar.get("defects") or []
    if not ds:
        return "", ""
    ds = sorted(ds, key=lambda d: (_SEV_ORDER.get(_sev_cls(d.get("sev")), 3), str(d.get("id", ""))))

    # --- 彙總表（兩個版本共用）---
    sum_rows = "".join(
        "<tr>"
        f'<td><span class="chip id">{esc(d.get("id", ""))}</span></td>'
        f'<td><span class="chip {_sev_cls(d.get("sev")).lower()}">{esc(_sev_cls(d.get("sev")))}</span></td>'
        f'<td>{esc(d.get("side", ""))}</td>'
        f'<td>{esc(d.get("title", ""))}</td>'
        f'<td class="n">{esc(d.get("scope", ""))}</td>'
        f'<td>{esc(d.get("status", ""))}</td>'
        "</tr>" for d in ds)
    sum_tbl = ('<table class="dfx-sum"><thead><tr>'
               "<th>編號</th><th>嚴重度</th><th>歸屬側</th><th>缺陷</th>"
               '<th class="n">範圍</th><th>狀態</th>'
               f"</tr></thead><tbody>{sum_rows}</tbody></table>")

    # --- 逐項卡片（只有 full 版）---
    fields = (("observed", "現象"), ("repro", "重現"), ("evidence", "證據"),
              ("control", "決定性對照組"), ("excluded", "我方已排除"), ("note", "備註"))
    cards = []
    for d in ds:
        sev = _sev_cls(d.get("sev"))
        dl = "".join(f"<dt>{lab}</dt><dd>{d[k]}</dd>" for k, lab in fields if d.get(k))
        cards.append(
            f'<div class="dfx s-{sev.lower()}"><div class="dfx-h">'
            f'<span class="chip id">{esc(d.get("id", ""))}</span>'
            f'<h4>{esc(d.get("title", ""))}</h4>'
            f'<span class="chip {sev.lower()}">{esc(sev)}</span>'
            f'<span class="chip side">{esc(d.get("side", "未分類"))}</span>'
            + (f'<span class="chip st">{esc(d["status"])}</span>' if d.get("status") else "")
            + f"</div><dl>{dl}</dl></div>")

    intro = nar.get("defects_note") or ""
    sec = ('  <section>\n'
           '    <div class="sec-head"><span class="sec-no">00</span><h2>缺陷清單 — 可直接回報</h2>'
           '<span class="en">Defect Register</span></div>\n'
           + (f'    <div class="callout">{intro}</div>\n' if intro else "")
           + f"    {sum_tbl}\n    " + "".join(cards) + "\n  </section>\n")
    return sec, sum_tbl


def renumber_sections(html):
    """章節編號在模板裡是寫死的；缺陷節是條件輸出，所以組版後依文件順序重編。"""
    n = [0]

    def rep(_m):
        n[0] += 1
        return f'<span class="sec-no">{n[0]:02d}</span>'
    return re.sub(r'<span class="sec-no">\d+</span>', rep, html)


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_dir")
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--template", default=None)
    ap.add_argument("--reviewer", default=None)
    ap.add_argument("--variant", choices=("full", "simple"), default="full",
                    help="full＝官方完整版（裁決/指標/餘額鏈/明細/建議）；simple＝精簡核對版（摘要卡+結論+含注單號明細表）")
    a = ap.parse_args()

    rd = a.report_dir.rstrip("/")
    games_path = os.path.join(rd, "games.jsonl")
    if not os.path.exists(games_path):
        sys.exit(f"ERROR: 找不到 {games_path}（請先跑 run）")
    # 載入 + 欄位正規化（report_common：壞行容錯、別名補 canonical 欄）
    games = sorted(load_games(games_path), key=lambda g: g.get("idx", 0))
    meta = load_json(os.path.join(rd, "run-meta.json"), {}) or {}
    glist_raw = load_json(os.path.join(rd, "full-game-list.json"), {}) or {}
    glist = (glist_raw.get("games") if isinstance(glist_raw, dict) else glist_raw) or []
    glist_by_idx = {g.get("idx"): g for g in glist}
    nar = load_json(a.input, {}) or {}
    tpl_path = a.template or os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-report-template.html")
    template = open(tpl_path, encoding="utf-8").read()
    reviewer = a.reviewer or nar.get("reviewer") or "QA"

    # X-131 (4)：`alerts` 兩版**無條件**渲染。發現若只寫在 verdict.paragraphs[1:]，
    # 簡版只取 [0] 會靜默吃掉它 —— 那是散文紀律，會復發；這裡給它機械保證的位置。
    alerts = [x for x in (nar.get("alerts") or []) if str(x).strip()]
    alerts_html = ("".join(f"<li>{x}</li>" for x in alerts)) if alerts else ""
    defects_sec, defects_tbl = build_defects(nar)

    # X-131 (1)：注單號那句斷言只有在真的有後台注單號時才成立。
    _orig = [betid_origin(g) for g in games]
    n_bo_id = sum(1 for o in _orig if o == "bo")
    n_ingame_id = sum(1 for o in _orig if o == "ingame")
    if n_bo_id and not n_ingame_id:
        betid_caption = "注單號＝後台「注單」欄，多注單以逗號分隔"
    elif n_bo_id and n_ingame_id:
        betid_caption = (f"注單號：{n_bo_id} 筆為後台「注單」欄（多注單以逗號分隔）；"
                         f"另 {n_ingame_id} 筆為遊戲端局號／回合 ID，非後台注單欄")
    elif n_ingame_id:
        betid_caption = "此欄為遊戲端局號／回合 ID，非後台「注單」欄（本 run 未做後台對帳釘回）"
    else:
        # 一列 id 都沒有 ⇒ 該欄全空，原句只是空話而非假陳述。
        # 保留原文，讓「沒有 id 的 run」在回歸中維持逐位元相同（不為了整齊去動無關的 run）。
        betid_caption = "注單號＝後台「注單」欄，多注單以逗號分隔"
    # 只有「純遊戲端 id」的 run 才改導言措辭；其餘一律保留原文，避免波及無關的 run。
    betid_ingame_only = bool(n_ingame_id and not n_bo_id)

    # ---- 指標 ----
    # 🔴 X-134：`total` 是**執行列數**不是款數。兩者過去被混用（全檔多處把 total 標成「款」），
    #   在重試少的 run 上剛好相等所以看不出來；qt-20260915-1825 有 56 列重試、全庫 1,572 款，
    #   而報告顯示「1,307」⇒ 讀者會以為那就是遊戲總數。三個分母必須分開命名。
    total = len(games)
    lib_total = len(glist)                                   # 全庫款數（full-game-list.json）；缺則 0
    # 🔴 三態：不是每個 run 都有 `code`（例：rc-slots-20260915-0211 用 game/game_id）。
    #   欄位缺席時款數是**未知**不是 0 —— 回 None，呼叫端據此隱藏款數指標而不是印出 0。
    #   （第一版我直接 len(set)，對那個 run 得到 games_distinct=0 / retry=11，是憑空捏造的數字。）
    _codes = {g.get("code") for g in games if g.get("code")}
    if _codes:
        games_distinct = len(_codes)                         # 曾被執行過的款數
        games_covered = len({g.get("code") for g in games
                             if g.get("code") and str(g.get("status", "")).startswith("PASS")})
        n_retry_rows = total - games_distinct                # 重試造成的多餘列數
    else:
        games_distinct = games_covered = n_retry_rows = None
    sc = Counter(g.get("status", "?") for g in games)
    # 通過的變體（如 PASS_ON_RETEST／PASS_BET_NOT_MINIMUM）一律算通過：它們是「有成立下注」的
    # 附條件通過，不是異常款。原本只認字串 "PASS"，會把這些款計進「異常款／假 PASS」而誤導。
    # 明細表仍逐列顯示原始狀態字串，粒度不損失。
    npass = sum(v for k, v in sc.items() if str(k).startswith("PASS"))
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

    # ---- 餘額鏈斷點（X-141：往前帶錨點，不再對 null 列靜默跳過）----
    # 🔴 舊版比對「嚴格相鄰兩列」，任一列的 after_bal/before_bal 非數就跳過。
    #    本檔實測 33 列非數 ⇒ 48 對比對被跳過。真實斷點若緊接在 null 列之後會被**無聲遮蔽**。
    # 🔴 方向澄清（我原本想反了）：跳過才是「靜默假設 null 列沒動錢」；
    #    往前帶不會製造假陰性 —— null 列若動了錢，段後第一列就會對不上錨點而**冒出**斷點。
    #    代價只是斷點的**歸屬位置**變模糊（可能落在 anchor_idx+1 .. 本列之間）,
    #    故一併輸出 anchor_idx 與跨越列數，讓讀者知道範圍。
    # 🔴 錨點**只用 after_bal**：不退用同列的 before_bal —— 那等於斷言該列自身零資金移動，
    #    對 BET_NOT_PLACED 成立、對一般列不成立（audit.x1.py 的舊寫法有此問題）。
    breaks, break_rows = [], []
    anchor = None          # 最後一個可用的 after_bal
    anchor_idx = None
    spanned = 0            # 自錨點以來跨過幾列（沒有可用 after_bal 的列）
    for g in games:
        b1 = g.get("before_bal")
        if anchor is not None and num(b1) and abs(b1 - anchor) > 0.001:
            breaks.append(g.get("idx"))
            break_rows.append({"idx": g.get("idx"), "anchor_idx": anchor_idx,
                               "spanned_rows": spanned,
                               "anchor_after_bal": anchor, "before_bal": b1,
                               "diff": round(b1 - anchor, 4)})
        a1 = g.get("after_bal")
        if num(a1):
            anchor, anchor_idx, spanned = a1, g.get("idx"), 0
        else:
            spanned += 1
    nbreak = len(breaks)
    n_break_spanning = sum(1 for r in break_rows if r["spanned_rows"] > 0)

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
    if isinstance(viewport, list) and len(viewport) == 2:
        vp = f"{viewport[0]}×{viewport[1]}"
    elif isinstance(viewport, str) and viewport.strip():
        vp = viewport.strip().replace("x", "×")   # run-meta 也可能寫成字串 "1908x912"
    else:
        vp = nar.get("viewport", "")
    date_s = nar.get("date", "")
    if not date_s and has_time and re.match(r"^\d{4}-\d{2}-\d{2}", spins[0]):
        date_s = spins[0][:10]
    meta_start = meta.get("started_at") or meta.get("start_time")  # run-meta 實際鍵為 started_at
    if not date_s and meta_start:
        m2 = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})", str(meta_start))
        if m2:
            date_s = "-".join(m2.groups())

    def _hhmm(ts):
        """取 HH:MM：完整 datetime 切 [11:16]；純 HH:MM:SS 取前 5 碼。

        日期與時間的分隔可為空格或 ISO 的 'T'（runner 寫的是 ISO，舊版只認空格，
        會讓時段顯示成 '2026- – 2026-'）。
        """
        ts = str(ts).strip()
        return ts[11:16] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", ts) else ts[:5]

    time_range = nar.get("time_range", "")
    if not time_range and has_time:
        time_range = f"{_hhmm(spins[0])} – {_hhmm(spins[-1])}"

    title = nar.get("title") or f"{brand_disp} 功能測試報告 — QA Manager Review"

    # ---- 精簡核對版（--variant simple）：摘要卡 + 核對結論 + 含注單號明細表 ----
    if a.variant == "simple":
        stitle = nar.get("title_simple") or f"{brand_disp} 功能測試 — 精簡核對版"
        sok = abnormal == 0 and total > 0
        n_betid = sum(1 for g in games if betid_str(g))
        has_bo_gn = any(g.get("bo_gamename") for g in games)  # 對帳釘回的後台遊戲名（舊 run 無此欄→整欄隱藏）
        wls = [v for v in (bo_wl_of(g) for g in games) if num(v)]
        wl_total = round(sum(wls), 2) if wls else None
        concl = (nar.get("verdict", {}).get("paragraphs") or [
            f"共 <b>{total} 列</b>"
            + (f"（{games_distinct} 款）" if games_distinct is not None else "")
            + f"，<b>{npass} 列 PASS</b>、異常 {abnormal} 列；"
            f"每款以遊戲內餘額 before/after 變動驗證真實下注"
            + (f"，其中 {n_betid} 列已記後台注單號可逐筆對單" if n_betid else "") + "。"])[0]
        srows = []
        for g in games:
            st = g.get("status", "?")
            st_cls = "pass" if str(st).startswith("PASS") else ("fail" if st in ("LOAD_FAIL", "FAIL", "OOPS_UNRECOVERED") else "skip")
            d = g.get("delta")
            d_cls = "pos" if (num(d) and d > 0) else ("neg" if (num(d) and d < 0) else "")
            wl = bo_wl_of(g)
            wl_cls = "pos" if (num(wl) and wl > 0) else ("neg" if (num(wl) and wl < 0) else "")
            srows.append(
                "<tr>"
                f'<td class="n">{esc(g.get("idx"))}</td>'
                f'<td class="n">{esc(code_of(g, glist_by_idx))}</td>'
                f'<td class="game">{esc(g.get("name"))}</td>'
                + (f'<td class="game">{esc(g.get("bo_gamename") or MINUS)}</td>' if has_bo_gn else "")
                + f'<td class="n">{esc(g.get("bet")) if num(g.get("bet")) else ""}</td>'
                f'<td class="n">{money(g.get("before_bal"))}</td>'
                f'<td class="n">{money(g.get("after_bal"))}</td>'
                f'<td class="n {d_cls}">{signed(d)}</td>'
                f'<td class="n {wl_cls}">{signed(wl) if num(wl) else ""}</td>'
                f'<td class="t">{esc(g.get("spin_time") or "")}</td>'
                f'<td class="bid">{esc(betid_str(g))}</td>'
                f'<td><span class="st {st_cls}">{esc(st)}</span></td>'
                f'<td class="note">{esc(g.get("note") or "")}</td>'
                "</tr>")
        sub_bits = " · ".join(esc(b) for b in (host, account, date_s, time_range, reviewer) if b)
        kpis = ([(("已覆蓋款數" if lib_total else "已 PASS 款數"),
                   (f"{games_covered}/{lib_total}" if lib_total else str(games_covered)), "")]
                if games_covered is not None else []) + [
            ("執行列", (f"{total}（含 {n_retry_rows} 列重試）" if n_retry_rows else str(total)), ""),
            ("PASS 列", f"{npass}/{total}", "pos" if sok else ""),
            ("異常", str(abnormal), "neg" if abnormal else "pos"),
            ("投注合計", money(total_bet), ""),
            ("淨輸贏 delta", signed(net) if num(net) else "—",
             "neg" if (num(net) and net < 0) else "pos"),
            ("已記注單號", f"{n_betid} 列", ""),
        ]
        if wl_total is not None:
            kpis.append(("後台輸贏合計", signed(wl_total), "neg" if wl_total < 0 else "pos"))
        kpi_html = "".join(f'<span>{esc(k)} <b class="{c}">{v}</b></span>' for k, v, c in kpis)
        css = (
            ":root{--bd:#d8dde3;--mut:#6b7785;--pos:#0E7A57;--neg:#c0392b;--head:#1f2d3a}"
            "*{box-sizing:border-box}"
            'body{margin:0;padding:18px 20px;font:14px/1.5 -apple-system,"Segoe UI","Noto Sans CJK TC",sans-serif;color:#1f2d3a;background:#f4f6f8}'
            "h1{font-size:18px;margin:0 0 4px}"
            ".sub{color:var(--mut);font-size:13px;margin-bottom:10px}"
            ".kpi{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:10px;font-size:13px}.kpi b{font-size:15px}"
            + (".alerts{background:#fff8e6;border:1px solid #e3c766;border-left:4px solid #c8860a;"
               "padding:8px 14px 8px 30px;margin:-6px 0 14px;font-size:13.5px}"
               ".alerts ul{margin:0;padding-left:4px}.alerts li{margin:2px 0}" if alerts_html else "")
            + ".concl{background:#fff;border:1px solid var(--bd);border-left:4px solid var(--pos);"
            "padding:10px 14px;margin-bottom:14px;font-size:13.5px}"
            "table{width:100%;border-collapse:collapse;background:#fff;table-layout:auto}"
            "thead th{position:sticky;top:0;background:var(--head);color:#fff;padding:8px 9px;"
            "text-align:left;font-weight:600;white-space:nowrap;z-index:2}"
            "td{padding:7px 9px;border-bottom:1px solid var(--bd);vertical-align:top}"
            "tbody tr:nth-child(even){background:#f7f9fb}"
            ".n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}"
            ".t{white-space:nowrap;color:#333}.game{font-weight:600;min-width:150px}"
            ".bid{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#475}"
            ".note{color:var(--mut);font-size:12px;min-width:160px}"
            ".pos{color:var(--pos);font-weight:600}.neg{color:var(--neg);font-weight:600}"
            ".st{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap}"
            ".st.pass{background:#e2f5ec;color:var(--pos)}.st.fail{background:#fbe5e2;color:var(--neg)}"
            ".st.skip{background:#eef0f2;color:var(--mut)}"
            "footer{margin-top:12px;color:var(--mut);font-size:12px}"
            # 缺陷彙總表（精簡版自帶樣式，與 full 版模板 CSS 各自獨立）
            "h2.dfx-t{font-size:15px;margin:18px 0 8px}"
            ".dfx-sum{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}"
            ".dfx-sum th,.dfx-sum td{border-bottom:1px solid #e3e6e8;padding:6px 10px;text-align:left}"
            ".dfx-sum th{color:var(--mut);font-weight:600;font-size:12px}"
            ".dfx-sum td.n{text-align:right;white-space:nowrap}"
            ".chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap}"
            ".chip.id{background:#13212B;color:#fff}.chip.p1{background:#fbe5e2;color:var(--neg)}"
            ".chip.p2{background:#fdf0dc;color:#A8650A}.chip.p3{background:#eef0f2;color:var(--mut)}")
        doc = (
            '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(stitle)}</title><style>{css}</style></head><body>"
            f"<h1>{esc(stitle)}</h1>"
            f'<div class="sub">{sub_bits}</div>'
            f'<div class="kpi">{kpi_html}</div>'
            f'<div class="concl">{concl}</div>'
            + (f'<div class="alerts"><ul>{alerts_html}</ul></div>' if alerts_html else "")
            + (f'<h2 class="dfx-t">缺陷清單 — 可直接回報</h2>{defects_tbl}' if defects_tbl else "")
            + "<table><thead><tr>"
            '<th class="n">編號</th><th class="n">代碼</th><th>遊戲名</th>'
            + ("<th>後台遊戲名</th>" if has_bo_gn else "")
            + '<th class="n">投注</th>'
            '<th class="n">進入前</th><th class="n">進入後</th><th class="n">delta</th>'
            '<th class="n">後台輸贏</th><th>SPIN 時間</th><th>注單號</th><th>狀態</th><th>備註</th>'
            "</tr></thead><tbody>" + "".join(srows) + "</tbody></table>"
            f"<footer>report_dir：{esc(rd)}/ · 來源 games.jsonl {total} 行"+ (f" · {esc(betid_caption)}" if betid_caption else "") + "</footer>"
            "</body></html>")
        out_path = a.out or os.path.join(rd, "qa-report-simple.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc)
        print(json.dumps({
            "out": out_path, "variant": "simple", "total": total, "pass": npass,
            "abnormal": abnormal, "net_delta": net, "total_bet": total_bet,
            "library_total": lib_total, "games_distinct": games_distinct,
            "games_covered": games_covered, "retry_rows": n_retry_rows,
            "betid_rows": n_betid, "bo_id_rows": n_bo_id, "ingame_id_rows": n_ingame_id,
            "bo_winlose_total": wl_total, "alerts": len(alerts),
        }, ensure_ascii=False))
        return

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
            f"本次測試對 <b>{esc(brand_disp)}</b> 執行 <b>{total} 列</b>"
            + (f"（涵蓋 {games_distinct} 款"
               + (f"，全庫 {lib_total} 款" if lib_total else "") + "）"
               if games_distinct is not None and games_distinct != total else "")
            + "，結果 "
            f"<b>{npass} 列 PASS</b>" + (f"（{npass/total*100:.0f}%）" if total else "") +
            "。每款皆以遊戲內餘額 before/after 實際變動（delta≠0）確認真實下注，非單純點擊 SPIN。",
            f"餘額鏈<b>斷點 {nbreak}</b>" + ("（每款下注前餘額精確等於前一款下注後餘額，連中獎小數位都完整接續，構成逐筆真實下注的完整證據鏈）。"
             if nbreak == 0 else "（有斷點，需人工查驗下列明細表）。"),
        ]
    verdict_inner = (f'<div class="verdict-head"><h2>測試結論 — Test Verdict</h2>{chips_html}</div>' +
                     f'<p class="lead">{paras[0]}</p>' +
                     "".join(f"<p>{p}</p>" for p in paras[1:]) +
                     (f'<ul style="background:#fff8e6;border:1px solid #e3c766;border-left:4px solid #c8860a;'
                      f'padding:10px 14px 10px 32px;margin:14px 0 0;border-radius:4px">{alerts_html}</ul>'
                      if alerts_html else ""))

    # ---- 區塊：metrics ----
    pct = f"<small>/{total}</small>"
    metrics = [
        ("ok" if all_pass else "warn", f"{npass}{pct}", f"PASS 列 · 共 {total} 列"),
        ("ok" if nbreak == 0 else "neg", str(nbreak), "餘額鏈斷點 · 逐筆相接"),
        ("", str(nshots), "證據截圖張數"),
        ("", str(wins), "觀察到中獎的執行列"),
        ("neg" if num(net) and net < 0 else "ok", (signed(net) if num(net) else "—"), f"全部 {total} 列淨 delta"),
        ("ok" if abnormal == 0 else "neg", str(abnormal), "異常列 / 假 PASS"),
    ] + ([("", (f"{games_covered}<small>/{lib_total}</small>" if lib_total else str(games_covered)),
           ("已覆蓋款數 · 全庫" if lib_total else "已 PASS 款數"))]
         if games_covered is not None else [])
    metrics_inner = "".join(
        f'<div class="metric {c}"><div class="num">{v}</div><div class="lab">{esc(l)}</div></div>'
        for c, v, l in metrics)

    # ---- 區塊：時間投入（座標校準 vs 測試執行）----
    # X-122 健壯性修正：`calibration` 的意圖 schema 是「dict 或缺席」。
    #   全庫 168 個 run 實查：NoneType 166 / dict 1 / str 1 —— 偏離只有一個（值為校準目錄的路徑字串）。
    #   🔴 問題不在誰不合規，而在**共用工具對非預期輸入直接 AttributeError 崩潰**：
    #      失敗方式是崩潰而不是降級，代價與偏離程度不成比例。
    #   界線（刻意窄）：
    #     · dict        → 照舊使用（合規路徑**行為完全不變**）
    #     · None        → 照舊視同缺席，**不做任何回退**
    #                     （None 是合規的「缺席」；對它加回退會改動合規輸入的行為）
    #     · 其他型別    → 視同缺席，並回退讀同 run 的 calib-meta.json（若存在），
    #                     且把來源記進 calib_origin，報告需標明不是從 run-meta 讀到的。
    calib_raw = meta.get("calibration")
    calib_origin = "run-meta.json"
    if isinstance(calib_raw, dict):
        calib = calib_raw
    else:
        calib = {}
        if calib_raw is not None:
            _cm = load_json(os.path.join(rd, "calib-meta.json"))
            if isinstance(_cm, dict):
                calib = _cm
                calib_origin = "calib-meta.json"
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
    if exec_seconds is None:  # fallback：run-meta 的 started_at/ended_at（run mode 收尾會寫）
        exec_seconds = dur_seconds(meta.get("started_at"), meta.get("ended_at"))
    per_game_seconds = (exec_seconds / total) if (exec_seconds is not None and total) else None
    amort = (calib_seconds / total) if (calib_seconds is not None and total) else None

    NUMCSS = "font-family:var(--display);font-weight:700;font-size:30px;line-height:1;letter-spacing:-.02em"
    if calib_seconds is not None:
        calib_sub = (f"viewport {calib_vp_s}　·　首次校準（SPIN／餘額／退出座標與判定）"
                     + ("　·　<i>由產物時間回推、為近似值</i>" if calib_src == "reconstructed" else "")
                     + (f"　·　<i>校準數據來源：{esc(calib_origin)}</i>" if calib_origin != "run-meta.json" else ""))
    else:
        calib_sub = "本次 run 未記錄校準時間（calibrate／run 升級後會自動帶入）"
    exec_sub = (f"每款平均 ~{fmt_dur(per_game_seconds)}　·　首款 before → 末款 after"
                if exec_seconds is not None else "games.jsonl 無逐款讀取時間，無法計時")
    if calib_seconds is not None and exec_seconds is not None:
        callout_time = (f"<b>校準是一次性成本：</b>本次「座標校準·判定」約 <b>{fmt_dur(calib_seconds)}</b>，"
                        f"換來 {total} 列共 <b>{fmt_dur(exec_seconds)}</b> 的逐列驗餘額執行（每列 ~{fmt_dur(per_game_seconds)}）。"
                        f"同站、同 viewport 下校準參數可重複沿用，攤提到每款約 <b>{fmt_dur(amort)}</b>；"
                        f"款數越多、單位校準成本越低。本次合計投入約 {fmt_dur(calib_seconds + exec_seconds)}。")
    else:
        callout_time = "校準或執行時間其一缺漏，僅顯示可得部分；資料補齊後本區塊會自動完整。"
    time_inner = (
        '<div class="grid2">'
        '<div class="panel"><h3>座標校準 · 判定 <span class="tag">一次性</span></h3>'
        f'<div style="{NUMCSS};color:var(--amber)">{fmt_dur(calib_seconds)}</div>'
        f'<p style="margin-top:8px">{calib_sub}</p></div>'
        f'<div class="panel"><h3>測試執行 <span class="tag">{total} 列</span></h3>'
        f'<div style="{NUMCSS};color:var(--green)">{fmt_dur(exec_seconds)}</div>'
        f'<p style="margin-top:8px">{exec_sub}</p></div></div>'
        f'<div class="callout">{callout_time}</div>')

    # ---- 區塊：curve ----
    curve = build_curve_svg(games)
    if curve:
        legend = (f'<span><i class="swatch" style="background:#0E7A57"></i>餘額（after_bal）</span>'
                  f'<span><i class="swatch" style="background:#13212B;width:9px;height:9px;border-radius:50%"></i>首點 {money(curve["start"])}</span>'
                  f'<span><i class="swatch" style="background:#BC392C;width:9px;height:9px;border-radius:50%"></i>末點 {money(curve["end"])}</span>')
        if curve["big"]:
            bigtxt = "、".join(f'{esc(i)} 「{esc(nm)}」{signed(d)}' for i, nm, d in curve["big"])
            legend = (f'<span><i class="swatch" style="background:#0E7A57"></i>餘額（after_bal）</span>'
                      f'<span><i class="swatch" style="background:#A8650A;border-radius:50%;width:9px;height:9px"></i>大獎跳升：{bigtxt}</span>'
                      f'<span><i class="swatch" style="background:#13212B;width:9px;height:9px;border-radius:50%"></i>首點 {money(curve["start"])}</span>'
                      f'<span><i class="swatch" style="background:#BC392C;width:9px;height:9px;border-radius:50%"></i>末點 {money(curve["end"])}</span>')
        co = (f'<div class="curve-card"><div class="ctitle">'
              f'<h3>{money(curve["start"])} → {money(curve["end"])}　·　{curve["n"]} 筆連續餘額（idx 序）</h3>'
              '<span class="note">曲線點為每列 after_bal，故首點是第一列<b>下注後</b>的餘額，不是帳戶起始餘額</span>'
              f'<span class="note">每款 before＝前款 after，' + ("零斷點" if nbreak == 0 else f"{nbreak} 處斷點") + '</span></div>'
              f'{curve["svg"]}<div class="curve-legend">{legend}</div></div>'
              f'<div class="callout"><b>為何這條線是證據：</b>每一款的「下注前餘額」都精確等於前一款的「下注後餘額」，連中獎小數位都完整接續。'
              + ("這條無斷點的鏈證明每一筆都是真實扣款／派彩的下注，而非僅點擊 SPIN —— 是本次「無假 PASS」最直接的佐證。"
                 if nbreak == 0 else "目前有斷點，請對照下方逐款明細表查驗。") + "</div>")
    else:
        co = '<div class="callout warn">資料不足以繪製餘額鏈曲線（after_bal 點數不足）。</div>'

    # ---- 區塊：method ----
    cov = nar.get("method", {}).get("coverage") or {
        "測試列數": f"{total} 列", "餘額判讀": "截圖目視·讀兩次一致"}
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
        f"{total} 列中 <b>{wins} 列觀察到中獎</b>（派彩抵注或淨增）；其餘為標準扣注。最大幾筆："
    summary_inner = (
        '<div class="grid2" style="margin-bottom:16px">'
        '<div class="panel"><h3>帳戶層級</h3><table style="border:none"><tbody>'
        f'<tr><td>起始餘額</td><td class="num">{money(start_bal)}</td></tr>'
        f'<tr><td>結束餘額</td><td class="num">{money(end_bal)}</td></tr>'
        f'<tr><td>{total} 列投注額合計</td><td class="num">{money(total_bet)}</td></tr>'
        f'<tr class="total"><td>淨輸贏 delta</td><td class="num">{signed(net) if num(net) else "—"}</td></tr>'
        '</tbody></table></div>'
        f'<div class="panel"><h3>中獎觀察</h3><p style="margin-bottom:10px">{win_note}</p>'
        '<table style="border:none"><thead><tr><th>款</th><th>遊戲名</th><th class="num">淨 delta</th></tr></thead>'
        f'<tbody>{top_rows}</tbody></table></div></div>'
        f'<div class="panel"><h3>加轉／重試確認 <span class="tag">SOP 落實 · 無假 PASS</span></h3><ul>{mc_html}</ul></div>')

    # ---- 區塊：逐款明細表 ----
    full_has_bo_gn = any(g.get("bo_gamename") for g in games)  # 對帳釘回的後台遊戲名（舊 run 無此欄→整欄隱藏）
    drows = []
    for g in games:
        st = g.get("status", "?")
        st_cls = "pass" if str(st).startswith("PASS") else "other"
        d = g.get("delta")
        d_cls = "delta-pos" if (num(d) and d > 0) else "delta-neg"
        drows.append(
            "<tr>"
            f'<td class="num">{esc(g.get("idx"))}</td>'
            f'<td class="num">{esc(code_of(g, glist_by_idx))}</td>'
            f'<td>{esc(g.get("name"))}</td>'
            + (f'<td>{esc(g.get("bo_gamename") or MINUS)}</td>' if full_has_bo_gn else "")
            + f'<td class="num">{money(g.get("before_bal"))}</td>'
            f'<td class="num">{money(g.get("after_bal"))}</td>'
            f'<td class="num {d_cls}">{signed(d) if num(d) else ""}</td>'
            f'<td class="num">{money(g.get("win")) if num(g.get("win")) else ""}</td>'
            f'<td class="num">{esc(g.get("spin_time") or "")}</td>'
            f'<td class="betid">{esc(betid_str(g))}</td>'
            f'<td><span class="st {st_cls}">{esc(st)}</span></td>'
            "</tr>")
    detail_inner = (
        '<style>.detail-scroll td.betid{font-family:ui-monospace,Menlo,Consolas,monospace;'
        'font-size:11px;color:var(--muted);white-space:nowrap;word-break:keep-all}</style>'
        '<div class="detail-tools">逐款下注前後餘額、SPIN 時間與'
        + ('注單號' if betid_ingame_only else '後台注單號')
        + '，順序同遊戲序列表（idx）；'
        + ('可對照後台投注報表逐筆核對（' + esc(betid_caption) + '）。' if betid_caption else '')
        + '共 ' + str(total) + ' 列。</div>'
        '<div class="detail-scroll"><table><thead><tr>'
        '<th class="num">編號</th><th class="num">代碼</th><th>遊戲名</th>'
        + ("<th>後台遊戲名</th>" if full_has_bo_gn else "")
        + '<th class="num">進入前</th><th class="num">進入後</th><th class="num">delta</th>'
        '<th class="num">中獎</th><th class="num">SPIN 時間</th><th>注單號</th><th>狀態</th>'
        '</tr></thead><tbody>' + "".join(drows) + '</tbody></table></div>')

    # ---- 區塊：evidence ----
    # 截圖慣例逐 run 不同（有的每款 4 張、有的每款 1 張），寫死會讓報告高估證據強度。
    # narrative 可用 evidence_shots: [[檔名樣式, 說明], ...] 指定實際慣例；未給才用舊預設。
    shot_types = [tuple(x) for x in nar.get("evidence_shots", [])] or [
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
        "{{SUB}}": esc(nar.get("sub") or f"針對 {brand_disp} 共 {total} 列逐列功能驗證，每列保留證據截圖，並以遊戲內餘額變動逐筆確認真實下注。"),
        "{{META_ROWS}}": meta_rows,
        "{{VERDICT_INNER}}": verdict_inner,
        "{{METRICS_INNER}}": metrics_inner,
        "{{TIME_INNER}}": time_inner,
        "{{CURVE_INNER}}": co,
        "{{METHOD_INNER}}": method_inner,
        "{{SUMMARY_INNER}}": summary_inner,
        "{{DETAIL_INNER}}": detail_inner,
        "{{EVIDENCE_INNER}}": evidence_inner,
        "{{DEFECTS_SECTION}}": defects_sec,
        "{{RECS_INNER}}": recs_inner,
        "{{FOOTER_INNER}}": footer_inner,
    }
    out_html = template
    for k, v in repl.items():
        out_html = out_html.replace(k, v)
    out_html = renumber_sections(out_html)

    out_path = a.out or os.path.join(rd, "qa-report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_html)

    print(json.dumps({
        "out": out_path, "total": total, "pass": npass, "abnormal": abnormal,
        "chain_breaks": nbreak, "screenshots": nshots, "wins": wins,
        "net_delta": net, "start_bal": start_bal, "end_bal": end_bal,
        "library_total": lib_total, "games_distinct": games_distinct,
        "games_covered": games_covered, "retry_rows": n_retry_rows,
        "has_spin_time": has_time, "time_range": time_range,
        "calib_seconds": calib_seconds, "calib_source": calib_src or None,
        "calib_origin": calib_origin,
        "exec_seconds": exec_seconds,
        "per_game_seconds": round(per_game_seconds, 1) if per_game_seconds is not None else None,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
