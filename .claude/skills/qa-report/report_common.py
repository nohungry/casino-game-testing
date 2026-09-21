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


def _join_ids(b, sep):
    if isinstance(b, (list, tuple)):
        return sep.join(str(x) for x in b if x not in (None, ""))
    return str(b)


def betid_origin(g):
    """這一列的注單號來自哪裡 —— 回傳 "bo" / "ingame" / None。

    X-131：`bo_betid` 是後台投注報表的注單號（對帳釘回）；`betid` 是**遊戲端**的
    round id／bet-history id，兩者語義不同。報告模板過去逐字寫著「注單號＝後台
    「注單」欄」，套在只有 `betid` 的 run 上就是一句假陳述 —— 所以呼叫端必須能
    分辨來源，才能決定要不要下那句斷言。
    """
    # 🔴 `ALIAS` 已把 ("bo_betid", "bo_betids") 併進 `betid`（僅在 betid 為空時），
    #    所以「`betid` 有值」不代表它是遊戲端 id —— 必須先看 bo_* 原欄位，
    #    否則會把真正的後台注單號誤標成遊戲端局號（正是這個函式要防的那種假陳述）。
    for k in ("bo_betid", "bo_betids"):
        if g.get(k) not in (None, ""):
            return "bo"
    if g.get("betid") not in (None, ""):
        return "ingame"
    return None


def betid_str(g, sep=", "):
    """注單號字串：`bo_betid` 優先，退回 `betid`。

    優先序不可反過來：對帳釘回的後台注單號才是可逐筆對單的鍵，`betid` 只是遊戲端局號。
    """
    b = None
    for k in ("bo_betid", "bo_betids", "betid"):
        if g.get(k) not in (None, ""):
            b = g[k]
            break
    if b in (None, ""):
        return ""
    return _join_ids(b, sep)


def bo_wl_of(g):
    """後台輸贏：相容兩種欄位名（`bo_winlose` 舊名／`bo_wl` 對帳新名）。

    只讀不寫；兩者皆缺回 None（呼叫端據此隱藏 KPI，而不是顯示 0）。
    """
    for k in ("bo_winlose", "bo_wl"):
        v = g.get(k)
        if num(v):
            return v
    return None
