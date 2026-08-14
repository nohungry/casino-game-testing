#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_smoke_report.py — 跨品牌載入冒煙檢查的聚合器。

讀 <umbrella_dir>/brands/*/games.jsonl（每品牌一個 report_dir），確定性產出
<umbrella_dir>/smoke-report.md（可選 --html）。所有數字由資料算出，不靠人心算。

🔴 本報告不含任何 PASS：本任務不下注、不驗餘額，故沒有任何一款構成本專案定義的
   PASS（PASS 的唯一定義是「已驗證餘額 delta ≠ 0」）。LAUNCH_OK 只代表前端資產
   載入成功，不代表可下注、可結算、後台會產生注單。

用法：
    uv run .claude/skills/smoke-launch/gen_smoke_report.py <umbrella_dir> [--html]
（無 uv 時 python3 亦可；純標準庫。）
"""
import argparse
import glob
import html
import json
import os
import sys

# 復用 qa-report 的共用模組（壞行容錯 + 欄位別名正規化 + 重試去重）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qa-report"))
from report_common import dedupe_retries, load_jsonl, normalize_games  # noqa: E402

# 顯示順序固定，讓每次產出的表格欄位一致（缺的印 0，不要動態省略欄位）
STATUSES = ["LAUNCH_OK", "LAUNCH_BLOCKED", "LAUNCH_TIMEOUT",
            "LAUNCH_NO_RESPONSE", "STUCK_RECOVERED", "SKIPPED"]

SCOPE_NOTICE = (
    "> 🔴 **本輪只驗「能否載入到 start / splash 畫面」。全程未下注、未讀取或比對任何餘額，"
    "因此本報告中沒有任何一款構成本專案定義的 PASS**（PASS 的唯一定義是「已驗證餘額 delta ≠ 0」）。\n"
    "> `LAUNCH_OK` **僅代表前端資產載入成功**，不代表該款可下注、可結算，或後台會產生注單。"
)

CANNOT_DETECT = """\
1. 🔴 **最大盲區 —— 「動畫跑但餘額凍結」會被記成 `LAUNCH_OK`。** 有些款前端資產完整載入、
   splash 正常、甚至主畫面可操作，但餘額永不變動、下注永不成立、後台 0 筆。本方法**完全偵測不到**。
   → **「能開起來」≠「能玩」≠「能下注」≠「能結算入後台」。**
2. **無法區分「未開通」與「當下抖動」**：單次量測非統計。BLOCKED/TIMEOUT 可能是網路或 CDN 瞬時問題，
   收尾重試一輪只是緩解。
3. **跨域 iframe 內只能靠像素判讀**：警告若畫在 canvas 上、或使用未涵蓋的語言/文案，關鍵字掃描會漏判，
   → 可能被誤標成 `LAUNCH_OK`。目視判定含主觀性。
4. **`splash` 與 `main` 的分界本身模糊**：有些款沒有 splash 直接進主畫面。`到達層級` 欄是判讀不是事實。
5. **登入態或遊戲錢包狀態污染**：token 中途過期、該品牌錢包沒錢，都會讓大量款變 BLOCKED，
   外觀與「未開通」難以區分，且無法回溯修正。
6. **不代表生產環境**，也**不是同一時刻的快照**（整批跨數小時甚至跨天，期間可能有部署或維護窗口）。
7. **遊戲代碼抓不到時 join 不可靠**：只能靠品牌內序號，跨 run 比對會失準（大廳排序會變）。
8. **未覆蓋**手機版／其他解析度／其他會員層級／其他入口（搜尋、熱門、收藏）。
9. **統計不獨立**：同供應商同引擎的款多半共命運，「OK 率 N%」**不能**解讀為「隨機抽一款有 N% 機率可用」。

**明確不能下的結論**：「X 款通過測試」「品牌 Y 可以上線」「OK 率＝可用率」「這批遊戲沒問題」。
**可以下的結論只有**：「在 <時間> 的 <站點>，這 X 款前端載入到了 start/splash 畫面；這 Y 款跳出了『<原文>』」。"""


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def cell(v):
    """None/空 一律印破折號，不要印 None 或 0 冒充量過的值。"""
    return "—" if v in (None, "") else str(v)


def pct(n, d):
    return f"{n / d * 100:.0f}%" if d else "—"


def n_tested(counts):
    """已測 = 取得結論的款數。🔴 SKIPPED 不算已測（根本沒跑），算進去會虛報覆蓋率。"""
    return sum(v for k, v in counts.items() if k != "SKIPPED")


def _listed_from(fgl, bmeta):
    """決定該品牌的清單分母：非空 list ＞ 有正面證據的 0 ＞ 盤點 listed_count ＞ 未知(None)。

    🔴 空 list 是【歧義】的，不可直接當成「量測到 0 款」：
    實測 live umbrella 六個品牌的 full-game-list.json 都是 `{"games": []}`、
    `unenumerable` 未設、`count` 為 None —— scout 其實是**沒列舉成功**（二層大廳在跨域
    iframe 內抓不到），只是寫了個空陣列。把它讀成「確認 0 張桌」會憑空生出假精確的分母，
    覆蓋率也會跟著失真。要當成 0，必須有生產端的正面證據（`count` 是數字，或 `enumerated`
    為真）；否則退回 listed_count，仍缺就是未知。
    """
    if fgl.get("unenumerable"):
        return None
    games = fgl.get("games")
    if isinstance(games, list) and games:
        return len(games)
    if isinstance(games, list) and not games:
        if isinstance(fgl.get("count"), int) or fgl.get("enumerated") is True:
            return 0                      # 生產端明說列舉過 → 0 是量測結果
        return bmeta.get("listed_count")  # 歧義 → 不假設，退回盤點值（可能是 None＝未知）
    return bmeta.get("listed_count")


def brand_verdict(counts, meta_verdict, listed=0):
    """品牌層級判讀。meta_verdict（brands.json 記的）優先，它涵蓋『根本沒跑成』的情形。

    🔴 覆蓋率不足 100% 時措辭一律標明「抽樣」：只驗了 5/243 卻寫「全數未能載入」
    會讓人以為 243 款都驗過，是最容易被誤引用的一句話。
    """
    tested = n_tested(counts)
    if meta_verdict:
        # 🔴 meta_verdict 不可直接原文照印 —— 那會讓下面整段「抽樣」措辭被旁路掉。
        #    實測：brands.json 記 LAUNCHABLE、實際只測 10/30，報告就印出光禿禿的
        #    「LAUNCHABLE」，讀者無從得知那是抽樣結論。新流程幾乎每個品牌都帶
        #    meta_verdict，等於這道防線在主路徑上完全沒生效。
        #    → meta_verdict 仍是判讀來源，但覆蓋率不足時一律加註分母。
        if tested and listed and tested < listed:
            return f"{meta_verdict}（抽樣 {tested}/{listed}）"
        if tested and listed is None:
            return f"{meta_verdict}（抽樣 {tested}/未知）"
        if not tested:
            # 純 API 預篩、UI 一次都沒點過 —— 必須讓讀者看得出來
            return f"{meta_verdict}（未經 UI 實測）"
        return meta_verdict
    if not tested:
        return "未測"
    ok = counts.get("LAUNCH_OK", 0)
    # 🔴 listed 為 None＝清單列舉不到（例如跨域 iframe 內的二層大廳）。
    #    這種情況一律標「抽樣」且分母寫「未知」—— None 是 falsy，若沿用 `partial = listed and ...`
    #    會落到 else 分支輸出「全數可載入」，等於用 3 張桌的結果宣稱整個品牌都好。
    denom = "未知" if listed is None else listed
    partial = (listed is None) or (listed and tested < listed)
    if ok == tested:
        return f"抽樣全數可載入（{tested}/{denom}）" if partial else "全數可載入"
    if ok == 0:
        return f"抽樣全數未能載入（{tested}/{denom}）" if partial else "全數未能載入"
    return f"抽樣部分可載入（{ok}/{tested}）" if partial else "部分可載入"


def collect(umbrella):
    """回傳 (rows, brands)；rows 是攤平的逐款紀錄，brands 是每品牌彙總。"""
    meta_by_slug = {}
    for b in (load_json(os.path.join(umbrella, "brands.json"), []) or []):
        if isinstance(b, dict) and b.get("bslug"):
            meta_by_slug[b["bslug"]] = b

    rows, brands = [], []
    for gpath in sorted(glob.glob(os.path.join(umbrella, "brands", "*", "games.jsonl"))):
        bdir = os.path.dirname(gpath)
        bslug = os.path.basename(bdir)
        bmeta = meta_by_slug.get(bslug, {})

        games, n_superseded = dedupe_retries(normalize_games(load_jsonl(gpath)))
        games.sort(key=lambda g: (g.get("idx") is None, g.get("idx")))

        # 分母優先序：full-game-list.json ＞ 盤點階段的 listed_count ＞ 未知
        # 🔴 清單標了 unenumerable（例如真人的二層大廳在跨域 iframe 內無法列舉）→ listed=None，
        #    絕不可 fallback 成「已跑行數」：那會讓「抽 3 張桌」印成「清單 3 / 覆蓋率 100%」。
        # 🔴 「確認過是 0 張」與「不知道有幾張」是兩件事，不可都用 falsy 兜成同一個值：
        #    前者印 0（是量測結果），後者印 —（是未量測）。
        fgl = load_json(os.path.join(bdir, "full-game-list.json"), {}) or {}
        listed = _listed_from(fgl, bmeta)
        probe = load_json(os.path.join(bdir, "brand-probe.json"), {}) or {}

        counts = {}
        for g in games:
            st = g.get("status") or "?"
            counts[st] = counts.get(st, 0) + 1
        for g in games:
            g["_bslug"] = bslug
            g["_bname"] = bmeta.get("display_name") or bslug
        rows.extend(games)

        brands.append({
            "bslug": bslug,
            "name": bmeta.get("display_name") or bslug,
            "listed": listed,          # 可能是 None＝未知，下游印「—」，不要用 `or len(games)` 兜
            "category": bmeta.get("category") or "?",
            "tested": n_tested(counts),
            "skipped": counts.get("SKIPPED", 0),
            "counts": counts,
            "superseded": n_superseded,
            "verdict": brand_verdict(counts, bmeta.get("brand_verdict"), listed),
            "confidence": (probe.get("confidence") or {}).get("ready"),
            "gaps": probe.get("gaps") or [],
            "probe": probe,
        })

    # 品牌層級不可用的（沒有 games.jsonl，連目錄都可能沒有）也要出現在報告裡
    seen = {b["bslug"] for b in brands}
    for slug, bmeta in meta_by_slug.items():
        if slug in seen:
            continue
        # 還沒跑的品牌也要進表：分母取盤點階段的 listed_count 或已產的 full-game-list.json
        _fj = load_json(os.path.join(umbrella, "brands", slug, "full-game-list.json"), {}) or {}
        _listed = _listed_from(_fj, bmeta)   # 與上面同一套判準，見 _listed_from 的說明
        brands.append({
            "bslug": slug, "name": bmeta.get("display_name") or slug,
            "listed": _listed,
            "category": bmeta.get("category") or "?",
            "tested": 0, "skipped": 0, "counts": {}, "superseded": 0,
            # 這一批是「一款都沒跑過」的品牌（例如只做了 API 預篩）。判讀一律附註出處，
            # 否則純 API 的結論會與 UI 實測的結論在同一欄裡長得一模一樣。
            "verdict": (f"{bmeta['brand_verdict']}（未經 UI 實測）"
                        if bmeta.get("brand_verdict") else "未測"),
            "confidence": None, "gaps": [], "probe": {},
        })
    brands.sort(key=lambda b: (b["category"], b["name"]))
    return rows, brands


def build_md(umbrella, rows, brands, meta):
    tot_listed = sum(b["listed"] or 0 for b in brands)          # None＝未知，不計入
    n_unknown = sum(1 for b in brands if b["listed"] is None)   # 有幾個品牌分母未知
    tot_tested = sum(b["tested"] for b in brands)      # 不含 SKIPPED
    tot_skipped = sum(b["skipped"] for b in brands)
    agg = {}
    for r in rows:
        st = r.get("status") or "?"
        agg[st] = agg.get(st, 0) + 1
    n_ok = agg.get("LAUNCH_OK", 0)

    L = []
    L.append(f"# 遊戲載入冒煙檢查 — {cell(meta.get('site_host'))} {cell(meta.get('started_at'))}\n")
    L.append(SCOPE_NOTICE + "\n")

    L.append("## 1. 執行資訊\n")
    L.append("| 項目 | 值 |")
    L.append("|---|---|")
    for k, v in [("站點", meta.get("site_host")), ("帳號", meta.get("account")),
                 ("開始", meta.get("started_at")), ("結束", meta.get("ended_at")),
                 ("viewport", meta.get("viewport")), ("登入態已驗證", meta.get("login_verified")),
                 ("方法版本", meta.get("method_version")), ("resume 次數", meta.get("resume_count")),
                 ("涵蓋品牌數", len(brands)),
                 ("清單總款數", f"{tot_listed}" + (f"（另有 {n_unknown} 個品牌分母未知）" if n_unknown else "")),
                 ("已測款數（不含 SKIPPED）", tot_tested), ("未測（SKIPPED）", tot_skipped)]:
        L.append(f"| {k} | {cell(v)} |")
    L.append("")

    L.append("## 2. 總覽\n")
    L.append("| 狀態 | 款數 | 佔已測 |")
    L.append("|---|---:|---:|")
    for st in [s for s in STATUSES if s != "SKIPPED"] + sorted(
            k for k in agg if k not in STATUSES):
        if agg.get(st):
            L.append(f"| `{st}` | {agg[st]} | {pct(agg[st], tot_tested)} |")
    L.append(f"| **已測合計** | **{tot_tested}** | |")
    if tot_skipped:
        L.append(f"| `SKIPPED`（未測，不計入已測） | {tot_skipped} | — |")
    L.append("")
    L.append(f"**可載入（`LAUNCH_OK`）：{n_ok} / {tot_tested} 款**"
             f"（佔已測 {pct(n_ok, tot_tested)}；佔已知清單總數 {pct(n_ok, tot_listed)}"
             + ("，另有分母未知的品牌未計入" if n_unknown else "") + "）"
             f" — 僅代表前端載入成功，未驗餘額。\n")

    L.append("## 3. 品牌總表\n")
    head = "| 品牌 | 清單 | 已測 | " + " | ".join(s.replace("LAUNCH_", "") for s in STATUSES) + " | 覆蓋率 | 判讀 | 判定信心 |"
    L.append(head)
    L.append("|---|---:|---:|" + "---:|" * len(STATUSES) + "---:|---|---|")
    for b in brands:
        cnt = " | ".join(str(b["counts"].get(s, 0)) for s in STATUSES)
        listed_txt = "—" if b["listed"] is None else str(b["listed"])
        cov_txt = "—" if b["listed"] is None else pct(b["tested"], b["listed"])
        L.append(f"| {b['name']} | {listed_txt} | {b['tested']} | {cnt} | "
                 f"{cov_txt} | {b['verdict']} | {cell(b['confidence'])} |")
    L.append("")

    ok_rows = [r for r in rows if r.get("status") == "LAUNCH_OK"]
    L.append(f"## 4. ★ 可載入清單（{len(ok_rows)} 款）\n")
    if ok_rows:
        L.append("> 「splash」＝畫面出現遊戲內容（可能仍在跑遊戲自帶的載入條）；"
                 "「主畫面」＝載入條跑完、進到可操作畫面。兩者分開記，避免把「還在載入」當成「已可玩」。\n")
        L.append("| 品牌 | # | 代碼 | 遊戲名 | splash 耗時 | 主畫面 | 啟動方式 | 判定時間 |")
        L.append("|---|---:|---|---|---:|---|---|---|")
        for r in ok_rows:
            sp = r.get("reached_splash_ms", r.get("launch_ms"))
            mn = r.get("reached_main_ms")
            chk = r.get("main_check")
            if isinstance(mn, (int, float)):
                main_txt = f"✅ {mn/1000:.0f}s"
            elif chk == "reached":
                # 🔴 到了主畫面但沒記耗時（runner 常見：真人看到荷官影像、電子自動跳過 splash）。
                #    少了這個分支會掉到下面的 cell(chk) 印出生字串「reached」，
                #    而且小計會把它算進「未做主畫面驗證」—— 方向與事實相反（2026-08-14 實測 3 筆）。
                main_txt = "✅ 已達（未記耗時）"
            elif chk == "timeout":
                main_txt = "⏱ 逾時未達"
            elif chk == "start_gate":
                # 電子是「開始」鈕、捕魚是遊戲自帶的「選場」畫面 —— 同一件事：
                # 資源載完了，但還要再點一次遊戲內的東西才會進主畫面，而那一點可能等同下注。
                main_txt = "⏸ 停在遊戲自帶入口（未點）"
            elif chk == "seat_required":
                main_txt = "🚫 需入座（未驗證）"
            elif chk in (None, "not_checked"):
                main_txt = "未驗證"
            else:
                main_txt = cell(chk)
            L.append(f"| {r['_bname']} | {cell(r.get('idx'))} | {cell(r.get('code'))} | "
                     f"{cell(r.get('name'))} | "
                     f"{f'{sp/1000:.1f}s' if isinstance(sp, (int, float)) else '—'} | "
                     f"{main_txt} | {cell(r.get('surface'))} | {cell(r.get('opened_at'))} |")
        # 「已達主畫面」＝有記耗時 或 main_check 明寫 reached（後者是 runner 常見寫法）
        n_main = sum(1 for r in ok_rows
                     if isinstance(r.get("reached_main_ms"), (int, float))
                     or r.get("main_check") == "reached")
        n_to = sum(1 for r in ok_rows if r.get("main_check") == "timeout")
        n_gate = sum(1 for r in ok_rows if r.get("main_check") == "start_gate")
        n_nc = len(ok_rows) - n_main - n_to - n_gate
        L.append(f"\n小計：載入到 splash **{len(ok_rows)} 款**；其中確認進到可操作主畫面 **{n_main} 款**、"
                 f"停在遊戲自帶「開始」鈕前 {n_gate} 款、等到逾時仍未進主畫面 {n_to} 款、未做主畫面驗證 {n_nc} 款。")
        if n_gate:
            L.append("\n> ⏸ **「停在遊戲自帶入口」不是失敗**：資源已完整載入，只是該引擎還需要再點一次"
                     "**遊戲畫面內**的東西才會進主畫面（電子是「開始」鈕、捕魚是選場／選注額房間）。"
                     "**本輪未點** —— 專案鐵則禁止碰投注 UI，而那一點可能等同下注"
                     "（電子部分引擎的「開始」＝旋轉；捕魚進房後畫面任一點擊＝開火）。"
                     "這些款的主畫面可達性**尚未驗證**，需要另行裁示後才能確認。")
    else:
        L.append("_無_")
    L.append("")

    L.append("## 5. 未能載入清單\n")
    any_bad = False
    sub_no = 0
    for st in [s for s in STATUSES if s != "LAUNCH_OK"]:
        sub = [r for r in rows if r.get("status") == st]
        if not sub:
            continue
        any_bad = True
        sub_no += 1
        L.append(f"### 5.{sub_no} `{st}`（{len(sub)} 款）\n")
        if st == "LAUNCH_BLOCKED":
            L.append("| 品牌 | # | 代碼 | 遊戲名 | 警告原文 | 警告來源 | 截圖 |")
            L.append("|---|---:|---|---|---|---|---|")
            for r in sub:
                shots = r.get("screenshots") or []
                L.append(f"| {r['_bname']} | {cell(r.get('idx'))} | {cell(r.get('code'))} | "
                         f"{cell(r.get('name'))} | {cell(r.get('block_text'))} | "
                         f"{cell(r.get('block_kind'))} | {cell(shots[0] if shots else None)} |")
        else:
            L.append("| 品牌 | # | 代碼 | 遊戲名 | 備註 | 截圖 |")
            L.append("|---|---:|---|---|---|---|")
            for r in sub:
                shots = r.get("screenshots") or []
                L.append(f"| {r['_bname']} | {cell(r.get('idx'))} | {cell(r.get('code'))} | "
                         f"{cell(r.get('name'))} | {cell(r.get('note'))} | "
                         f"{cell(shots[0] if shots else None)} |")
        L.append("")
    if not any_bad:
        L.append("_無_\n")

    # 🔴 用 startswith：實際寫入的值帶括號原因（例如 "BRAND_UNAVAILABLE(list: 0 張卡片)"），
    #    精確比對從來不會 match；BRAND_LOBBY_ONLY 有 tested 行，不改就會整個漏出本節。
    bad_brands = [b for b in brands if b["tested"] == 0
                  or str(b["verdict"]).startswith(("BRAND_UNAVAILABLE", "PROBE_FAILED", "BRAND_LOBBY_ONLY"))]
    L.append("## 6. 品牌層級不可用 / 未探測成功\n")
    if bad_brands:
        L.append("| 品牌 | 判讀 | 清單款數 | 未探到的項目 |")
        L.append("|---|---|---:|---|")
        for b in bad_brands:
            L.append(f"| {b['name']} | {b['verdict']} | {'—' if b['listed'] is None else b['listed']} | "
                     f"{cell('、'.join(b['gaps']) if b['gaps'] else None)} |")
    else:
        L.append("_無_")
    L.append("")

    L.append("## 7. 🔴 本報告測不到什麼\n")
    L.append(CANNOT_DETECT + "\n")

    L.append("## 8. 附錄\n")
    n_sup = sum(b["superseded"] for b in brands)
    if n_sup:
        L.append(f"- 收尾重試取代的舊紀錄：{n_sup} 行（同 idx 以最後一行為準；舊行仍留在 games.jsonl 供追溯）")
    L.append(f"- 產物根目錄：`{os.path.abspath(umbrella)}`")
    L.append(f"- 續跑指令：`/smoke-launch --resume {os.path.abspath(umbrella)}`")
    L.append("- 每品牌 probe 參數：`brands/<bslug>/brand-probe.json`；逐款原始紀錄：`brands/<bslug>/games.jsonl`")
    L.append("")
    return "\n".join(L) + "\n"


def build_html(md_text, meta):
    """極簡 HTML：自帶標籤與色碼，不重用 qa-report 版型（那套的標籤寫死成
    「異常款 / 假 PASS」，會把整批冒煙呈現成 0% 紅燈）。"""
    css = """body{font:14px/1.7 system-ui,-apple-system,"Noto Sans TC",sans-serif;max-width:1200px;
margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}
table{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:13px;display:block;overflow-x:auto}
th,td{border:1px solid #ddd;padding:.35rem .5rem;text-align:left}th{background:#f5f5f5}
code{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px}
blockquote{border-left:4px solid #d33;background:#fff5f5;margin:1rem 0;padding:.6rem 1rem}
h1{border-bottom:2px solid #333;padding-bottom:.3rem}h2{margin-top:2rem;border-bottom:1px solid #ccc}
@media(prefers-color-scheme:dark){body{background:#161616;color:#e8e8e8}
th{background:#242424}th,td{border-color:#3a3a3a}code{background:#242424}
blockquote{background:#2a1a1a}h1{border-color:#888}h2{border-color:#444}}"""
    return (f"<title>遊戲載入冒煙檢查 — {html.escape(str(meta.get('site_host') or ''))}</title>"
            f"<style>{css}</style><pre style='white-space:pre-wrap;font:inherit'>"
            f"{html.escape(md_text)}</pre>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("umbrella_dir")
    ap.add_argument("--html", action="store_true")
    a = ap.parse_args()
    um = a.umbrella_dir.rstrip("/")

    if not os.path.isdir(os.path.join(um, "brands")):
        sys.exit(f"ERROR: 找不到 {um}/brands/，請先跑 smoke-launch 的 Phase 1-3。")

    meta = load_json(os.path.join(um, "smoke-meta.json"), {}) or {}
    rows, brands = collect(um)
    if not rows and not brands:
        sys.exit(f"ERROR: {um}/brands/ 底下沒有任何 games.jsonl，無資料可彙整。")

    md = build_md(um, rows, brands, meta)
    md_path = os.path.join(um, "smoke-report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 🔴 `tested` 的定義必須與報告正文一致（不含 SKIPPED）。編排層 agent 讀的是這個 JSON，
    #    用 len(rows) 會把「排定但沒跑」的款算進已測，轉述出去就成了虛報的覆蓋率。
    out = {"out_md": md_path, "brands": len(brands),
           "tested": sum(b["tested"] for b in brands),
           "skipped": sum(b["skipped"] for b in brands),
           "rows": len(rows),
           "by_status": {}, "listed": sum(b["listed"] or 0 for b in brands),
           "listed_unknown_brands": sum(1 for b in brands if b["listed"] is None)}
    for r in rows:
        st = r.get("status") or "?"
        out["by_status"][st] = out["by_status"].get(st, 0) + 1

    if a.html:
        html_path = os.path.join(um, "smoke-report.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(build_html(md, meta))
        out["out_html"] = html_path

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
