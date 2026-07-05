# -*- coding: utf-8 -*-
"""report_common.py — 報告產生器共用：games.jsonl 載入（容錯）+ 欄位正規化 + 格式化。

canonical schema（game-batch-runner 寫出）為準；歷史 run 用過另一套別名欄位，
normalize_games() 統一補到 canonical 欄（不覆蓋既有值），兩套 jsonl 都吃得下。
"""
import html
import json
import sys

MINUS = "−"

# canonical 欄 ← 別名（依序取第一個有值的）
ALIAS = {
    "status": ("verdict",),
    "before_bal": ("bal_before",),
    "after_bal": ("bal_after",),
    "name": ("game",),
    "win": ("win_gross",),
    "spin_time": ("bet_time",),
    "betid": ("bo_betid", "bo_betids"),
    "code": ("img",),
}


def load_jsonl(path):
    """逐行讀 jsonl；壞行跳過並在 stderr 警告（容忍半途中斷的 run），不整支 crash。"""
    rows, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                bad += 1
                print(f"WARN: {path}:{lineno} 非合法 JSON，已跳過（{e}）", file=sys.stderr)
    if bad:
        print(f"WARN: 共跳過 {bad} 行壞資料，報告數字以可解析的 {len(rows)} 行為準", file=sys.stderr)
    return rows


def normalize_games(rows):
    """套 ALIAS 把別名欄補進 canonical 欄；回傳原 list（就地修改）。"""
    for g in rows:
        for canon, aliases in ALIAS.items():
            if g.get(canon) in (None, ""):
                for al in aliases:
                    if g.get(al) not in (None, ""):
                        g[canon] = g[al]
                        break
    return rows


def load_games(path):
    return normalize_games(load_jsonl(path))


# ---------- 格式化 ----------
def num(x):
    return isinstance(x, (int, float))


def money(x):
    return f"{x:,.2f}" if num(x) else ""


def signed(x, minus=MINUS):
    if not num(x):
        return ""
    s = f"{abs(x):,.2f}"
    return f"+{s}" if x >= 0 else f"{minus}{s}"


def esc(s):
    return html.escape(str(s if s is not None else ""))


def betid_str(g, sep=", "):
    b = g.get("betid")
    if b in (None, ""):
        return ""
    if isinstance(b, (list, tuple)):
        return sep.join(str(x) for x in b if x not in (None, ""))
    return str(b)
