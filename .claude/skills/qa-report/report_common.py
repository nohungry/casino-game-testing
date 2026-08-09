# -*- coding: utf-8 -*-
"""report_common.py — 報告產生器共用：games.jsonl 載入（容錯）+ 欄位正規化 + 格式化。

canonical schema（game-batch-runner 寫出）為準；歷史 run 用過多套別名欄位，
normalize_games() 統一補到 canonical 欄（不覆蓋既有值），多套 jsonl 都吃得下。
"""
import html
import json
import re
import sys

MINUS = "−"

# canonical 欄 ← 別名（依序取第一個有值的）
ALIAS = {
    "status": ("verdict",),
    "before_bal": ("bal_before", "balance_before"),
    "after_bal": ("bal_after", "balance_after"),
    "name": ("game",),
    # 捕魚等無離散 SPIN 的型態記 total_bet（= 發數 × 砲倍）。canonical bet 的語意是
    # 「該款投注額」（非單注）：拉霸每款一注所以恰等於單注，捕魚則為該款合計。
    # >20 單注紅線判準看 bet_per_shot，不可拿此欄判。
    "bet": ("total_bet",),
    # est_win 是 delta 反推的推估派彩（非實讀）：允許補進 win 欄但 normalize 會設
    # win_est 旗標，報告層必須標「推估」呈現（2026-08-08 裁示：合法但要標記）。
    "win": ("win_gross", "est_win"),
    "spin_time": ("bet_time", "spin_at", "fire_start_at"),
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


_ISO_TS = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$")

# normalize 後值以此格式為準（與後台 betTime 同格式，對帳對時用）
_TS_FIELDS = ("spin_time", "before_read_time", "after_read_time")


def norm_ts(s):
    """ISO 8601（含 T / 毫秒 / +0800 / +08:00 / Z）→ canonical 'YYYY-MM-DD HH:MM:SS'；
    已是 canonical 或認不得的值原樣返回。"""
    if not isinstance(s, str):
        return s
    m = _ISO_TS.match(s.strip())
    return f"{m.group(1)} {m.group(2)}" if m else s


def normalize_games(rows):
    """套 ALIAS 把別名欄補進 canonical 欄，時間欄正規化；回傳原 list（就地修改）。"""
    for g in rows:
        for canon, aliases in ALIAS.items():
            if g.get(canon) in (None, ""):
                for al in aliases:
                    if g.get(al) not in (None, ""):
                        g[canon] = g[al]
                        if canon == "win" and al == "est_win":
                            g["win_est"] = True
                        break
        for f in _TS_FIELDS:
            if g.get(f):
                g[f] = norm_ts(g[f])
    return rows


def dedupe_retries(rows):
    """同一 idx 有多行 = 收尾重試補的新紀錄 → 以「最後一行」為準
    （test-game-brand SKILL.md 6.5：重試成功補一行新紀錄，彙整時以新行為準）。

    回傳 (kept_rows, n_superseded)。舊行只是不列入彙整，仍留在 games.jsonl 供追溯；
    重試的來龍去脈靠新行的 note 欄呈現，不靠把失敗行留在表上充當證據
    ——留著會讓 KPI 的「異常 N 款」把已修好的款算成失敗，反而誤導。
    idx 為 None 的行不做去重（無從判斷是否同一款）。
    """
    last_pos = {}
    for i, g in enumerate(rows):
        if g.get("idx") is not None:
            last_pos[g["idx"]] = i
    kept = [g for i, g in enumerate(rows)
            if g.get("idx") is None or last_pos[g["idx"]] == i]
    return kept, len(rows) - len(kept)


def load_games(path):
    """載入 + 正規化 + 重試去重（彙整用）。要拿到未去重的原始行請用 load_jsonl。"""
    kept, _ = dedupe_retries(normalize_games(load_jsonl(path)))
    return kept


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
