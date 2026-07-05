# 歷史驗收基準（acceptance fixtures）

`test-game-brand` / `qa-report` 各 mode 的驗收用例。⚠️ **這裡的品牌、座標、金額都是「當年那台機器、那個站」的歷史實測值，不是預設參數** —— repo 核心不變量是「品牌無預設、站點無預設」，這些值只拿來對照驗收流程，絕不拿去當校準座標或預期站點。

## Test 1 — calibrate mode（2026-06 品牌H 實測）
使用者開一款 品牌H sample → `/test-game-brand calibrate brandh` → 產出 `brands/brandh.yaml`：
- `spin.xy` 接近 **(1283, 857)**（該次滿版 viewport 下的實測值）
- `spin.viewport` 記錄了當下 viewport
- balance 讀法有著落（文字或截圖視覺判讀擇一成立）

## Test 2 — run mode（2026-06 品牌H 實測）
使用者開 品牌H 大廳 → `/test-game-brand run brandh --range 1-5` → 預期：
- `games.jsonl` 5 行、全 `PASS`，每行含 `win` / `before_read_time` / `spin_time` / `after_read_time`（三時間遞增、格式 `YYYY-MM-DD HH:MM:SS`）
- 每款 `delta ≈ -50` 且 `delta ≈ win - bet`（該次 bet=50），5 款總 delta ≈ **-250**
- `screenshots/` 有 g001..g005 的 loaded / bal-before / spin / bal-after 共 20 張
- 產出 `games.csv`，`run-summary.md` 含逐款明細表

## Test 3 — post mode（2026-06 品牌H 實測）
5 款跑完 → 使用者手動開後台篩好 → `/test-game-brand post brandh` → `reconcile.md` 對上 5/5（或誠實標出差異與原因）。

後續更完整的對帳實證：2026-06-26 品牌G 48 筆以 `betid` 精準 join 全數對上（`reports/brandg-2026-06-26/`，本機、未入 repo）。

## qa-report 驗收（2026-06-16 品牌B 實測）
對 `reports/品牌B-fullrerun-20260616-0326/`（本機、未入 repo）跑 `/qa-report` → `qa-report.html` 單檔可離線開、指標與 `run-summary.md` 一致、餘額鏈曲線點數＝款數、明細表列數＝款數。

## 參考的歷史脈絡
品牌H 全量 247 款：**初跑曾 65 款假 PASS（只點 SPIN 不驗餘額，真落單率 72.5%）**；導入「驗餘額才 PASS」鐵則後重驗，247 款全數通過。兩個數字是同一批遊戲**先後兩次**的結果，不矛盾。
