# -*- coding: utf-8 -*-
"""gen_run_artifacts.py — 從 games.jsonl 確定性產出 run-summary.md + games.csv。

run mode §7 的彙整產物由本腳本產生（取代編排層手刻），數字可被人工逐筆核對。
post 對帳釘回 betid/bo_gamename 後重跑本腳本即可帶入注單號欄。

用法：
    uv run .claude/skills/test-game-brand/gen_run_artifacts.py <report_dir>
（無 uv 時 python3 亦可；純標準庫。）
"""
import argparse
import json
import os
import sys

# 復用 qa-report 的共用模組（容錯載入 + 欄位正規化 + 格式化）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qa-report"))
from report_common import betid_str, load_games, num  # noqa: E402

CSV_COLS = ["idx", "code", "name", "before_bal", "after_bal", "delta", "bet", "win",
            "before_read_time", "spin_time", "after_read_time", "betid", "bo_gamename", "status"]

NON_PASS_HINT = ("> 非 PASS 款是最該人工跟進的：區分「下注不成立/載入失敗（環境問題）」與"
                 "「讀不到餘額/卡住（測試面問題）」；後台查無非 PASS 款注單屬預期。")


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def cell(v):
    return "" if v in (None, "") else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_dir")
    a = ap.parse_args()
    rd = a.report_dir.rstrip("/")

    games_path = os.path.join(rd, "games.jsonl")
    if not os.path.exists(games_path):
        sys.exit(f"ERROR: 找不到 {games_path}，請先跑 run。")
    games = sorted(load_games(games_path), key=lambda g: (g.get("idx") is None, g.get("idx")))
    meta = load_json(os.path.join(rd, "run-meta.json"), {}) or {}
    glist = ((load_json(os.path.join(rd, "full-game-list.json"), {}) or {}).get("games")) or []
    total_listed = len(glist) or len(games)

    # ---- 統計（全由資料算，不心算）----
    by_status = {}
    for g in games:
        by_status[g.get("status") or "?"] = by_status.get(g.get("status") or "?", 0) + 1
    passed = [g for g in games if g.get("status") == "PASS"]
    non_pass = [g for g in games if g.get("status") != "PASS"]
    pass_delta = round(sum(g["delta"] for g in passed if num(g.get("delta"))), 2)
    n_betid = sum(1 for g in games if betid_str(g))
    has_bo_gn = any(g.get("bo_gamename") for g in games)

    # ---- games.csv ----
    import csv
    csv_path = os.path.join(rd, "games.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for g in games:
            w.writerow([betid_str(g) if c == "betid" else cell(g.get(c)) for c in CSV_COLS])

    # ---- run-summary.md ----
    L = []
    brand = meta.get("display_name") or meta.get("brand") or ""
    L.append(f"# {brand} 批次測試 run-summary\n")
    if meta.get("lobby_url"):
        L.append(f"- lobby：{meta['lobby_url']}")
    bits = [b for b in (meta.get("account"), meta.get("started_at"),
                        f"→ {meta['ended_at']}" if meta.get("ended_at") else None) if b]
    if bits:
        L.append(f"- 帳號/時間：{'　'.join(str(b) for b in bits)}")
    L.append(f"- 總款數：**{total_listed}**　跑完：{len(games)}　覆蓋率：{len(games)}/{total_listed}\n")
    L.append("## 裁決摘要")
    L.append(f"- **PASS（有確認餘額變化）：{by_status.get('PASS', 0)} 款** ← 驗收看這個，不是只 click 成功的款數")
    L.append("- 各狀態：" + "、".join(f"{k} {v}" for k, v in sorted(by_status.items(), key=lambda kv: -kv[1])))
    L.append(f"- **PASS 款總 delta：{pass_delta}**")
    L.append(f"- 已記後台注單號（betid）：{n_betid} 款" + ("" if n_betid else "（run 完為 0 屬正常，post 對帳後重跑本腳本帶入）"))
    L.append("")
    if non_pass:
        L.append("## 非 PASS 款")
        L.append("| idx | 代碼 | 遊戲名 | 狀態 | note |")
        L.append("|---|---|---|---|---|")
        for g in non_pass:
            L.append(f"| {cell(g.get('idx'))} | {cell(g.get('code'))} | {cell(g.get('name'))} "
                     f"| {cell(g.get('status'))} | {str(g.get('note') or '')[:80]} |")
        L.append("")
        L.append(NON_PASS_HINT + "\n")
    L.append("## 逐款明細表")
    gn_col = " 後台遊戲名 |" if has_bo_gn else ""
    L.append(f"| 編號 | 代碼 | 遊戲名 |{gn_col} 進入前 | 進入後 | delta | 注額 | 中獎 | spin 時間 | 注單號 | 狀態 |")
    L.append("|---|---|---|" + ("---|" if has_bo_gn else "") + "---|---|---|---|---|---|---|---|")
    for g in games:
        gn = f" {cell(g.get('bo_gamename')) or '—'} |" if has_bo_gn else ""
        L.append(f"| {cell(g.get('idx'))} | {cell(g.get('code'))} | {cell(g.get('name'))} |{gn} "
                 f"{cell(g.get('before_bal'))} | {cell(g.get('after_bal'))} | {cell(g.get('delta'))} | "
                 f"{cell(g.get('bet'))} | {cell(g.get('win'))} | {cell(g.get('spin_time'))} | "
                 f"{betid_str(g) or '—'} | {cell(g.get('status'))} |")
    md_path = os.path.join(rd, "run-summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    print(json.dumps({"out_md": md_path, "out_csv": csv_path, "rows": len(games),
                      "by_status": by_status, "pass_delta": pass_delta,
                      "betid_rows": n_betid, "bo_gamename": has_bo_gn}, ensure_ascii=False))


if __name__ == "__main__":
    main()
