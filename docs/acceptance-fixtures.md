# 歷史驗收基準（acceptance fixtures）

`test-game-brand` / `qa-report` 各 mode 的驗收用例。⚠️ **這裡的品牌、座標、金額都是「當年那台機器、那個站」的歷史實測值，不是預設參數** —— repo 核心不變量是「品牌無預設、站點無預設」，這些值只拿來對照驗收流程，絕不拿去當校準座標或預期站點。

## Test 1 — calibrate mode（2026-06 品牌H 實測）
使用者停在品牌H 大廳 → `/test-game-brand calibrate <brand>` → 產出 `brands/<brand>.yaml`：
- `spin.xy` 接近 **(1283, 857)**（該次滿版 viewport 下的實測值）
- `spin.viewport` 記錄了當下 viewport
- balance 讀法有著落（文字或截圖視覺判讀擇一成立）

## Test 2 — run mode（2026-06 品牌H 實測）
使用者停在品牌H 大廳 → `/test-game-brand run <brand> --range 1-5` → 預期：
- `games.jsonl` 5 行、全 `PASS`，每行含 `win` / `before_read_time` / `spin_time` / `after_read_time`（三時間遞增、格式 `YYYY-MM-DD HH:MM:SS`）
- 每款 `delta ≈ -50` 且 `delta ≈ win - bet`（該次 bet=50），5 款總 delta ≈ **-250**
- `screenshots/` 有 g001..g005 的 loaded / bal-before / spin / bal-after 共 20 張
- 產出 `games.csv`，`run-summary.md` 含逐款明細表

## Test 3 — post mode（2026-06 品牌H 實測）
5 款跑完 → 使用者手動開後台篩好 → `/test-game-brand post <brand>` → `reconcile.md` 對上 5/5（或誠實標出差異與原因）。

後續更完整的對帳實證：2026-06-26 品牌G 48 筆以 `betid` 精準 join 全數對上（本機 reports/，未入 repo）。

## qa-report 驗收（2026-06-16 品牌B 實測）
對品牌B 全量 rerun 的 report_dir（本機 reports/，未入 repo）跑 `/qa-report` → `qa-report.html` 單檔可離線開、指標與 `run-summary.md` 一致、餘額鏈曲線點數＝款數、明細表列數＝款數。

## Test 2/3 — run + post 全流程（2026-07-07 品牌G 實測，最新基準）
使用者停在品牌G 大廳（52 款異質玩法：crash/keno/dice/mines/slot/揭示…，座標逐款現場判斷、無 brand yaml）→ run 全量 → post 對帳：
- **run**：`games.jsonl` 52 行＝**48 PASS / 3 BET_NOT_PLACED / 1 LOAD_FAIL**，PASS 總 delta **−80.8**（低籌碼 3~3.8）；4 款非 PASS 皆「staging 未開放下注/未部署」樣態（動畫跑但餘額凍結、或卡 launchLoading），**零假 PASS**。
- **post**：matched **48/48**、missing_in_bo **0**、extra 5（2 canary + 3 ×1 保本重注，皆預期）；逐筆 delta==後台輸贏 47/48（1 筆中獎晚結算，與次款餘額跳點 +3.99 自我印證）；**詳情彈窗 GameName 53/53 全掃、零配錯**；betid + bo_gamename 全數釘回。
- 產物：本機 reports/（未入 repo）。

## qa-report 非拉霸 schema 回歸（2026-08-06 品牌K／品牌F 實測，本機 reports/ 以日期識別，未入 repo）
兩個 run 的 games.jsonl 欄名/時間格式偏離 canonical，是 `report_common.py` alias + `norm_ts` 的回歸用例：
- **品牌K run**（拉霸、`balance_before/after` + `spin_at` ISO 時間）：**不帶 `--input`** 跑 `gen_qa_report.py` → 測試時段須顯示 `11:43 – 11:52` 而非 `2026- – 2026-`（ISO 打穿 `_hhmm` 的回歸），執行時長算得出、明細表時間顯示 canonical 格式。
- **品牌F run**（捕魚、`total_bet`/`bet_per_shot`/`fire_start_at`/`est_win`）：投注/進入前後/SPIN 時間/中獎四欄皆非空；表頭「投注（總額）」、中獎值帶「（推估）」標記；total/PASS/net_delta 與 run-summary 一致（2 款、PASS 2、net −1.4）。

## 無人值守 + 白名單導航登入 + 後台代理憑證（2026-08-19 站點R 實測，三項首次 live 驗收）

`.mcp.json` 的 `--config` 指向 `playwright-mcp.unattended.json` 後重啟，全程無人調整視窗：
- **viewport**：`about:blank` 讀到 `1908×912`，與 `.env` 的 `WINDOW_SIZE` 及 unattended config 三處一致；
  `outerWidth/Height` 為 `1916×1043`（OS 視窗含分頁列）——正是不可改用 `--window-size` 的實證。
- **白名單導航**：目標 host 比對到 `SITEn_HOST` 後自行 `browser_navigate`，登入頁填 `SITEn_USER`/`SITEn_PASS`
  → 出現「用戶協議」需按確定 → 登入態實測通過（「登入」鈕消失、顯示帳號與餘額、線上人數）。
- **後台代理憑證**：另開分頁用 `SITEn_ADMIN_USER`/`SITEn_ADMIN_PASS` 登入後台（代理層帳號），
  停在 bet-report。**前後台兩套憑證分別使用、未混用**，兩邊都一次登入成功。
- 憑證讀取用「暫時分頁載 `file://` 讀 `.env` → 同一 snippet 內填入 → 只回傳布林狀態」，
  transcript 全程未出現任何憑證值。

## 狀態三級分類回歸（2026-08-19 修復後實測）

`PASS_PARTIAL` / `PASS_WITH_ANOMALY` / `PASS_PENDING_BO` 不再被算成「異常／假 PASS」：
- 合成 fixture（PASS / PASS_PARTIAL 9-10 / 缺 `rounds_count` / LOAD_FAIL）→ `pass=1, partial=2, abnormal=1`。
- 歷史 run 回歸 4 份，其中一份含 1 筆 `PASS_PARTIAL`：修前 `abnormal=1`、修後 `partial=1, abnormal=0`。
- `gen_run_artifacts._rounds_cell` 在 `rounds_attempted` 有值而 `rounds_count` 缺時，
  輸出 `🔴 ?/10（成立輪數未記）`，**不再輸出字面 `None/10`**。

## 供應商斷線的正確處置（2026-08-19 站點R 實測）

外部第三方供應商全數 `400 ThirdPartyError`、自營品牌 `200 OK` 時的預期行為：
- 先跑**對照組**（另一品牌、另一分類）再下結論，不因單品牌失敗就歸咎登入或環境。
- 進不去的品牌照實記 `LOAD_FAIL` 並產出 run 產物，**不刪除、不當作沒跑過**。
- 改用可載入的品牌補足該分類時，在 `run-meta.json` 記 `substitute_for` 與 `substitute_reason`。
- 盤點結果落成 `launch-inventory.json` 附在 report_dir。

## 參考的歷史脈絡
品牌H 全量 247 款：**初跑曾 65 款假 PASS（只點 SPIN 不驗餘額，真落單率 72.5%）**；導入「驗餘額才 PASS」鐵則後重驗，247 款全數通過。兩個數字是同一批遊戲**先後兩次**的結果，不矛盾。
