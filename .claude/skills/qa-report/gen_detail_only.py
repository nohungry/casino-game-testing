#!/usr/bin/env python3
# 產一張「只有逐款明細表」的獨立單檔 HTML：滿版、自動換行、表頭固定，免左右拖動。
# 用法：python3 gen_detail_only.py <report_dir> [--out path.html] [--title 標題]
import argparse, html, json, os, sys

from report_common import load_games, num

def esc(x):
    return html.escape("" if x is None else str(x))

def money(x):
    return f"{x:,.2f}" if num(x) else esc(x or "")

def signed(x):
    return (f"+{x:,.2f}" if x > 0 else f"{x:,.2f}") if num(x) else ""

def betid(g):
    b = g.get("betid")
    if b in (None, ""): return ""
    if isinstance(b, (list, tuple)):
        return "<br>".join(esc(x) for x in b if x not in (None, ""))
    return esc(b)

ap = argparse.ArgumentParser()
ap.add_argument("report_dir")
ap.add_argument("--out", default=None)
ap.add_argument("--title", default="逐款明細")
ap.add_argument("--names", default=None, help="代碼→前台遊戲名 JSON（鍵為 code 代碼；舊 jsonl 的 img 欄自動視為 code）")
ap.add_argument("--subtitle", default=None,
                help="標題旁副標（如「品牌（帳號）」）。不給則讀 report_dir/run-meta.json 的 display_name/account；都沒有就不顯示。")
a = ap.parse_args()

rd = a.report_dir.rstrip("/")
# load_games：壞行容錯 + 欄位別名正規化（兩套 jsonl schema 都吃得下）
games = sorted(load_games(os.path.join(rd, "games.jsonl")), key=lambda g: g.get("idx", 0))
out = a.out or os.path.join(rd, "detail-only.html")

# 站點/品牌/帳號一律「從資料帶入」，腳本本身不寫死任何具體值（站點無預設、帳號無預設）。
meta = {}
_mp = os.path.join(rd, "run-meta.json")
if os.path.exists(_mp):
    try:
        meta = json.load(open(_mp, encoding="utf-8")) or {}
    except Exception:
        meta = {}
if a.subtitle is not None:
    subtitle = a.subtitle
else:
    _brand = meta.get("display_name") or meta.get("brand") or ""
    _acct = meta.get("account") or ""
    subtitle = _brand + (f"（{_acct}）" if _acct else "")

# 前台遊戲名對照（鍵 = img 代碼）；有給就以前台名為主顯示，原記錄名列為次要。
fe_names = {}
if a.names and os.path.exists(a.names):
    with open(a.names, encoding="utf-8") as f:
        fe_names = {str(k): v for k, v in json.load(f).items() if not str(k).startswith("_")}

def disp_name(g):
    code = str(g.get("code") or "")
    fe = fe_names.get(code)
    orig = g.get("name") or ""
    if fe:
        sub = f'<span class="orig">原記錄：{esc(orig)}</span>' if orig else ""
        return f'{esc(fe)}{sub}'
    return esc(orig)

rows = []
for g in games:
    st = g.get("status") or "?"
    st_cls = "pass" if st == "PASS" else ("fail" if st in ("LOAD_FAIL", "FAIL") else "skip")
    d = g.get("delta")
    d_cls = "pos" if (num(d) and d > 0) else ("neg" if (num(d) and d < 0) else "")
    wl = g.get("bo_winlose")
    wl_cls = "pos" if (num(wl) and wl > 0) else ("neg" if (num(wl) and wl < 0) else "")
    rows.append(
        "<tr>"
        f'<td class="n">{esc(g.get("idx"))}</td>'
        f'<td class="n">{esc(g.get("code") or "")}</td>'
        f'<td class="game">{disp_name(g)}</td>'
        f'<td class="n">{esc(g.get("bet")) if num(g.get("bet")) else ""}</td>'
        f'<td class="n">{money(g.get("before_bal"))}</td>'
        f'<td class="n">{money(g.get("after_bal"))}</td>'
        f'<td class="n {d_cls}">{signed(d)}</td>'
        f'<td class="n {wl_cls}">{signed(wl) if num(wl) else ""}</td>'
        f'<td class="t">{esc(g.get("spin_time") or "")}</td>'
        f'<td class="bid">{betid(g)}</td>'
        f'<td><span class="st {st_cls}">{esc(st)}</span></td>'
        f'<td class="note">{esc(g.get("note") or "")}</td>'
        "</tr>")

n_pass = sum(1 for g in games if g.get("status") == "PASS")
n_bet = sum(g["bet"] for g in games if num(g.get("bet")))
n_wl = sum(g["bo_winlose"] for g in games if num(g.get("bo_winlose")))

doc = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(a.title)}{(' — ' + esc(subtitle)) if subtitle else ''}</title>
<style>
:root{{--bd:#d8dde3;--mut:#6b7785;--pos:#0E7A57;--neg:#c0392b;--head:#1f2d3a}}
*{{box-sizing:border-box}}
body{{margin:0;padding:18px 20px;font:14px/1.5 -apple-system,"Segoe UI","Noto Sans CJK TC",sans-serif;color:#1f2d3a;background:#f4f6f8}}
h1{{font-size:18px;margin:0 0 4px}}
.sub{{color:var(--mut);font-size:13px;margin-bottom:12px}}
.kpi{{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:12px;font-size:13px}}
.kpi b{{font-size:15px}}
table{{width:100%;border-collapse:collapse;background:#fff;table-layout:auto}}
thead th{{position:sticky;top:0;background:var(--head);color:#fff;padding:8px 9px;text-align:left;font-weight:600;white-space:nowrap;z-index:2}}
td{{padding:7px 9px;border-bottom:1px solid var(--bd);vertical-align:top}}
tbody tr:nth-child(even){{background:#f7f9fb}}
.n{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.t{{white-space:nowrap;color:#333}}
.game{{font-weight:600;min-width:150px}}
.game .orig{{display:block;font-weight:400;font-size:11px;color:var(--mut);margin-top:1px}}
.bid{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#475}}
.note{{color:var(--mut);font-size:12px;min-width:180px}}
.pos{{color:var(--pos);font-weight:600}}
.neg{{color:var(--neg);font-weight:600}}
.st{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap}}
.st.pass{{background:#e2f5ec;color:var(--pos)}}
.st.fail{{background:#fbe5e2;color:var(--neg)}}
.st.skip{{background:#eef0f2;color:var(--mut)}}
</style></head><body>
<h1>{esc(a.title)}{('　·　' + esc(subtitle)) if subtitle else ''}</h1>
<div class="sub">逐款下注前後餘額、後台輸贏、SPIN 時間與後台注單號，順序同 idx；可對照後台投注報表逐筆核對。多注單以換行分隔。</div>
<div class="kpi">
  <span>總款數 <b>{len(games)}</b></span>
  <span>PASS <b>{n_pass}</b></span>
  <span>投注額合計 <b>{n_bet:,.2f}</b></span>
  <span>後台輸贏合計 <b class="{ 'pos' if n_wl>0 else 'neg' }">{signed(round(n_wl,2))}</b></span>
</div>
<table><thead><tr>
<th class="n">編號</th><th class="n">代碼</th><th>遊戲名</th><th class="n">投注</th>
<th class="n">進入前</th><th class="n">進入後</th><th class="n">delta</th><th class="n">後台輸贏</th>
<th>投注時間</th><th>注單號</th><th>狀態</th><th>備註</th>
</tr></thead><tbody>
{''.join(rows)}
</tbody></table>
</body></html>"""

with open(out, "w", encoding="utf-8") as f:
    f.write(doc)
print(json.dumps({"out": out, "rows": len(games), "pass": n_pass,
                  "bet_total": round(n_bet, 2), "wl_total": round(n_wl, 2)}, ensure_ascii=False))
