---
name: test-game-brand
description: 批次測試第三方電子遊戲平台的某個品牌。三個 mode：calibrate（探參數）/ run（批次跑+驗餘額+出報告）/ post（對帳）。唯一必填參數是品牌名；站點隱含於使用者已開好的當前頁面。使用者停在品牌大廳即可，品牌內選款/進入遊戲由 AI 操作；Skill 不跨站、不登入、不換品牌。
---

# test-game-brand

第三方電子遊戲平台**批次測試**。核心堅持：**品牌無預設、站點無預設、Skill 不跨站不登入不換品牌** —— 使用者自己開瀏覽器、登入、滿版、停在**該品牌遊戲大廳**，本 Skill 從當前頁接手；**品牌內選款/進入/退出遊戲由 AI 自行操作**（使用者不必自己開遊戲）。

## 指令格式
```
/test-game-brand <mode> <brand> [flags]
  mode  : calibrate | run | post
  brand : 品牌 slug（小寫），對應 brands/<brand>.yaml
  flags : --range a-b  --resume-from gNNN  --dry-run
```
先判斷 `<mode>`，照對應段落做。`<brand>` 沒給就先問使用者，不要亂猜。

---

## Mode: `run`（Step 4-5，已實作）

**前提**：使用者已登入、已停在該品牌的**遊戲列表頁（大廳）**，且**瀏覽器視窗已滿版**（座標靠滿版一致，跑前先提醒使用者維持滿版、過程中不要改視窗大小）。
- 🔴 **雙分頁 pre-flight**：開跑前用 `browser_tabs list` 確認**同時存在**「站點品牌大廳分頁」與「後台投注報表分頁」。缺後台 → 提醒使用者先開好（提醒不硬擋 run，但講明之後 post 對帳一定要有）；兩分頁都在就記下各自 index，**跑批全程不碰後台分頁**。
- 🔴 **確認該品牌遊戲錢包已有餘額**（不只是登入）：很多第三方電子品牌有**獨立遊戲錢包**，要先從主錢包轉帳進去才能下注。沒轉錢的症狀＝遊戲內餘額 0／下注點了不登錄／後台 0 筆。餘額為 0 就停下請使用者先儲值，不要硬跑（會整批 BET_NOT_PLACED）。實際驗證由下方「canary 先行」步驟做，不必只憑口頭提醒。

### 1. 載入並驗證 brand 參數
- 讀 `brands/<brand>.yaml`。不存在 → 停下，提示「先跑 `calibrate <brand>`」。
- `_calibration_gaps` 非空 → 停下，列出缺的欄位請使用者補，**不要硬跑**（防 default 偷渡）。

### 2. 記下 lobby_url（fail-fast）
- 用 `browser_evaluate` 讀 `location.href`，記為 `lobby_url`。
- 看起來不像遊戲列表頁（例如還在登入頁/後台）→ 提示使用者確認頁面後再跑。**Skill 不替使用者導航。**

### 3. 抓遊戲清單
- 用 `browser_snapshot` 或 `browser_evaluate`，依 `launch.selector_pattern` 抓出當前頁所有遊戲（名稱 + 出現順序）。
- 建立清單：`idx`(從 1 起的全域序號)、`name`、`nth`(同名第幾個)、`code`(遊戲代碼，能從卡片圖檔路徑/啟動參數抓到就記——它是對帳與報告的可靠 join 鍵；抓不到留 null)。
- 套用 `--range a-b`（只留序號 a..b）與 `--resume-from gNNN`（從該序號起）。
- 把抓到的清單與總數回報給使用者確認數量合理。

### 4. 建報告資料夾
- `reports/<brand>-<YYYYMMDD-HHMM>/`，內含 `screenshots/`。
- 時間戳用 `date +%Y%m%d-%H%M`（Bash 取，不要自己編）。
- 寫一個 `run-meta.json`：brand、lobby_url、range、總款數、batch size、起始時間。
- 🔴 **把 step 3 抓到的完整清單（含 range 外的全部）寫成 `report_dir/full-game-list.json`**：`{"games":[{"idx":1,"name":"…","nth":0,"code":"…"},…]}`。qa-report 的「代碼」欄與對帳的 join 都靠它；不寫這檔，代碼欄會退化成純序號。
- 🕒 **嵌校準時間（供 qa-report 呈現「校準 vs 執行」）**：找該品牌最近一個 `reports/<brand>-calib-*/calib-meta.json`，把它整包塞進 run-meta 的 `calibration` 欄（保留 `source`）。找不到就略過此欄（報告會顯示「—」，不阻擋）。範例：
  `run-meta.json` 內 `"calibration": {"started_at":...,"ended_at":...,"seconds":...,"viewport":[W,H],"source":"measured"}`。

### 5. 🐤 canary 先行（切批前，編排層自己跑第一款）
- 派批前，編排層先自己開**大廳第一款**（低籌碼 1 注）驗四件事：**遊戲錢包有錢**（餘額非 0）、**遊戲開啟方式**（新分頁或同頁 iframe）、**餘額讀法**（DOM 文字或 canvas 截圖判讀、在畫面哪個位置）、**delta 可驗**（下注成立、餘額實變）。
- canary 失敗＝錢包 0 → 停下請使用者儲值/轉帳，**不派批**。其餘三項的觀察寫進派批 prompt，讓每個 batch-runner 起跑就有現場情報。
- canary 產生的注單，post 對帳時會多出現在後台 → 列 `extra_in_bo` 並註明「canary」，不是漏帳。
- 測完關閉 canary 遊戲分頁回大廳，再開始切批。

### 6. 切批 + 派發 game-batch-runner
- 依 `batch.size`（預設 8）把清單切成數批。
- 對每批，用 **Agent 工具 spawn `game-batch-runner`**（subagent_type: `game-batch-runner`），prompt 帶入：完整 `brand_params`、`lobby_url`、該批 `games`、`report_dir` 絕對路徑、`flags`。
- `batch.parallel_batches==1`（預設）：**一批跑完再下一批**（共用同一個瀏覽器分頁，不能並行搶滑鼠/座標）。>1 時才考慮多分頁並行（目前保守，先序列）。
- 每個 batch-runner 自己 append `games.jsonl`；你收集它的回報。

### 7. 彙整報告（讀 `games.jsonl` 全部行，產三份）

**(a) `run-summary.md`**：
- 總款數、各 status 計數、覆蓋率（跑完款數/總數）。
- **PASS 款的總 delta**（驗收看這個）。
- 列出所有非 PASS 款（status + note），方便人工跟進。
- 🔴 明確標示：PASS 數 = 有確認餘額變化的款數，**不是只 click 成功的款數**。
- **逐款明細表**（Markdown）：欄位 `編號 / 代碼 / 遊戲名 / 進入前 / 進入後 / delta / 注額 / 中獎 / spin 時間 / 注單號 / 狀態`（與 qa-report 明細表同欄位；注單號 run 完通常空白，post 對帳釘回後重產才有值）。

**(b) `report_dir/games.csv`**（Excel 可直接開、可篩選）：
- 表頭：`idx,code,name,before_bal,after_bal,delta,bet,win,before_read_time,spin_time,after_read_time,betid,status`
- 每款一列，順序同 `games.jsonl`。中文名含逗號要正確處理（用引號包裹）；建議用 Bash/`python3` 從 `games.jsonl` 轉出，不要手刻。

**(c)** 既有 `run-meta.json` 不動。

> CSV/明細表的 `win` 與三個時間欄直接取自 `games.jsonl`（game-batch-runner 已寫入）；若舊報告沒有這些欄位，留空即可。

### run mode 驗收（Test 2）
歷史驗收基準（含具體品牌/數值）見 `docs/acceptance-fixtures.md`——具體值屬歷史紀錄、非預設，勿當校準參數用。

---

## Mode: `calibrate`（Step 7，已實作 — 半互動）

**前提**：使用者已登入、已停在該品牌的**遊戲列表頁（大廳）**，且**瀏覽器已滿版**（calibrate 只讀當下 viewport，run 時要一致，所以校準當下就要是日後跑批的滿版狀態）。**sample 遊戲由 AI 自行挑選進入**：預設挑**大廳第一款**，點開等載入完成；載入失敗（卡 loading 超過 ~60s）自動換下一款，並把換款原因記進 calib-meta。使用者不必自己開遊戲。
**互動模式：半互動** —— AI 自動探測，但關鍵欄位（尤其 spin.xy、balance 讀法）截圖給使用者確認後才寫 yaml；探不到的進 `_calibration_gaps`，不用 default 偷渡。

### 1. 準備
- 若 `brands/<brand>.yaml` 已存在 → 提示會覆蓋，先問使用者要不要續校準。
- 建 `reports/<brand>-calib-<YYYYMMDD-HHMM>/` 放探測截圖（時間戳用 `date` 取）。
- 🕒 **記校準起點（fallback 用）**：用 Bash `date '+%Y-%m-%d %H:%M:%S'` 取 `calib_started_at`。校準時間的**主真源是 calibrator 回傳的 `timing`**（步驟 4），這份自記值只在它缺漏時當備援。

### 2. 派發 brand-calibrator 探測
- spawn `brand-calibrator`（subagent_type: `brand-calibrator`），給 `brand`、`calib_dir`、**大廳現況**（lobby_url、大廳分頁 index）。
- calibrator **自行從大廳挑第一款遊戲點開當 sample**（開新分頁或同頁 iframe 依站點現場判斷），載入失敗自動換下一款並記錄。
- 它回傳：`draft_yaml`、`field_confidence`、`needs_confirm`、`calibration_gaps`、`screenshots`、`sample_game`（實際用了哪款、是否換過款）。

### 3. 🔴 半互動確認（這步是本 mode 的重點，不可略過）
- 把 `needs_confirm` 的項目逐一**呈現給使用者**，附上對應截圖路徑：
  - **spin.xy**：顯示候選座標與標注截圖，問使用者「SPIN 是否在這？」。calibrator 已用餘額變化實測過的話講明（high 信心）。
  - **balance 讀法**：說明是文字讀到還是要靠截圖視覺判讀，給 balance-region 截圖確認金額格式對不對。
  - 其他 med/low 信心欄位也一併確認。
- 用 AskUserQuestion 或直接提問；使用者更正的值覆蓋 draft。

### 4. 寫入 yaml
- 確認後的值寫 `brands/<brand>.yaml`（符合 `_schema.yaml` 結構）。
- 仍未確定的欄位 → 留在 `_calibration_gaps`（**非空代表此 yaml 還不能 run**，明確告知使用者要補哪些才能跑 run）。
- 🕒 **產 calib-meta.json（時間單一真源＝calibrator 回傳的 `timing`）**：起訖優先取 calibrator 回傳的 `timing.started_at/ended_at`；calibrator 沒回傳才用步驟 1 自記的 `calib_started_at` ＋ 當下 `date` 當備援。在 `calib_dir/` 產：
  ```json
  {"brand":"<brand>","viewport":[W,H],"started_at":"<started_at>","ended_at":"<ended_at>","seconds":<差秒數>,"source":"measured","sample_game":"<sample 名(code)>"}
  ```
  （`source:"measured"` 代表當場實記；秒數用 Bash/python 由起訖相減，不要心算。這份供 `run`／`qa-report` 呈現「座標校準·判定耗時」。）
- 落地後回報：哪些 high/med/low、gaps 還剩什麼、校準耗時、下一步可否直接 `run`。

### calibrate mode 驗收（Test 1）
歷史驗收基準見 `docs/acceptance-fixtures.md`——內含的座標是**當年那台機器的實測值，絕非預設座標**，勿拿來校準。

## Mode: `post`（Step 6，已實作）

對帳：把某次 run 的 `games.jsonl` 跟後台 bet-report 比對，產 `reconcile.md`。

### 1. 🔴 先提醒使用者手動開好後台（這步一定要做）
- 後台**由 QA 人員手動開啟**，Skill 不導航不登入。下指令前明確提醒使用者：
  「請先在瀏覽器手動開好**後台 bet-report**、**篩好條件**（時間區間涵蓋本次 run、品牌對上、**並用測試帳號篩會員**——全平台當日注量常上千筆，沒用帳號篩會找不到自己的注），並停在結果頁。」
- 使用者確認已開好、已篩好，才往下做。並用 `browser_tabs list` **實際檢查後台分頁存在**（分頁標題/URL 像後台管理系統）再往下，不只憑口頭確認。
- 提醒：第三方注單**回報後台可能延遲數分鐘**（有的站點 5-10 分），剛跑完就對帳可能還沒進，`backoffice-reconciler` 會 poll 等候。

### 2. 找對要對帳的 run
- 預設用最近一次 `reports/<brand>-*/`（非 calib）；多個時列出讓使用者選，或吃 flag 指定。
- 讀該 `report_dir/games.jsonl`。沒有或空 → 提示先跑 `run`。

### 3. 派發 backoffice-reconciler
- spawn `backoffice-reconciler`（subagent_type: `backoffice-reconciler`），給 `report_dir`、`brand`、`amount_tolerance`（預設 0.01）。
- 配對鍵由 reconciler 依優先序自行選用（`betid` 精準 join ＞ `code`/slug ＞ 名稱/語義佐證 ＞ 時間窗最後手段），games.jsonl 記了什麼就用最可靠的，不用在這裡指定。
- 它從**當前後台頁**讀資料、翻頁、對帳、寫 `report_dir/reconcile.md`。
- 對帳後 reconciler 會**預設逐筆開「詳情」彈窗讀遊戲名（GameName）做正面確認**（量大降抽查並註明覆蓋率），把配對可信度從時間窗推論升級為遊戲名確認。

### 4. 回報
- 帶出 reconciler 的結果：matched（含每筆**後台注單單號已釘回 games.jsonl 的 `betid` 欄**）/ missing_in_bo / extra_in_bo 數、金額是否平、「遊戲內 delta == 後台輸贏」是否逐筆吻合、**遊戲名確認覆蓋率**（詳情彈窗掃了幾筆/全部幾筆）、資料品質警告（後台是否可能沒抓全/疑延遲未回報）。
- 🔴 **特別點出 missing_in_bo**：games.jsonl 標 PASS 卻在後台找不到的款，是最該人工查的（假 PASS 或後台未涵蓋）；但要區分「真缺」與「後台延遲未回報」（後者 poll 後仍無才算缺）。

### post mode 驗收（Test 3）
歷史驗收基準見 `docs/acceptance-fixtures.md`。通則：`reconcile.md` 全數對上、或誠實標出差異與原因。

---

## 鐵則（貫穿所有 mode）
- 🔴 **驗餘額才能 PASS**：`delta==0`/讀不到/不確定一律不准 PASS。這條焊死在 `game-batch-runner` 裡，編排層也要在 summary 誠實呈現。delta 對所有遊戲類型通用（拉霸/crash/keno…）：未中＝−bet、中獎＝+淨額。
- 🔴 **下注前先確認下注成立**：下注鈕點了≠成立（crash 要在倒數窗口、keno 要先選號）。確認鈕狀態變/有「已下注」提示/餘額已扣，才讀 delta；否則重點，連續失敗記 `BET_NOT_PLACED`，不可標 PASS。
- 🔴 **投注額 > 20 一律先請示使用者**：預設用低籌碼（如 3）跑。要調高 BET 前先算單注金額，>20 就停下問使用者（crash「兩注面板」同回合兩注合計也要算）。**絕不點「全押/all-in」**（會押整個餘額）。
- 🔴 **遊戲品牌錢包要先有錢**：第三方品牌常有獨立遊戲錢包，需先轉帳；餘額 0 就停下請使用者儲值（見 run 前提）。
- 🔴 **注單單號（betid）是對帳的唯一可靠鍵**：前台常看不到注單單號，對帳時由 `backoffice-reconciler` 從後台擷取每筆注單號釘回 games.jsonl（`betid`/`bo_winlose`），並交叉驗證「遊戲內 delta == 後台輸贏」。
- 🔴 **卡住換新分頁**（CLAUDE.md 鐵則）：60s 無回應 → 新 tab 從 `lobby_url` 重啟，標 `STUCK_RECOVERED`，不在原頁 debug。
- 🔴 **滿版、不 resize**（CLAUDE.md 鐵則；`browser_resize` 已被 PreToolUse hook 硬擋）：viewport 一律「讀+比對」，不一致 fail-fast。跑前提醒使用者把視窗滿版且過程中別動。
- 🔴 **測試產物一律歸位 `report_dir/`**（CLAUDE.md 鐵則；裸檔名截圖已被 hook 硬擋）：截圖 `filename` 給完整路徑（一般 `report_dir/screenshots/`、對帳頁 `report_dir/backoffice/`、校準圖 `calib_dir/`）。編排層 spawn subagent 時務必傳入 `report_dir` **絕對路徑**，並要求「所有截圖/中繼檔用該路徑為前綴」。

## 邊界
本 Skill **不**負責跨站導航、登入、開後台、選後台篩選條件 —— 那是使用者跑前的責任；**品牌內選款/進入/退出遊戲則由 AI 操作**，使用者停在品牌大廳即可。頁面對不上（還在登入頁/別的品牌/後台當前頁）就 fail-fast 提示，不要替使用者跨站操作。**post mode 尤其要先提醒使用者手動開好後台 bet-report 並篩好條件。**