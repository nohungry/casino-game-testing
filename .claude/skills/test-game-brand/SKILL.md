---
name: test-game-brand
description: 批次測試第三方電子遊戲平台的某個品牌。三個 mode：calibrate（探參數）/ run（批次跑+驗餘額+出報告）/ post（對帳）。唯一必填參數是品牌名；站點隱含於當前頁面。瀏覽器由 AI 啟動；視窗尺寸有人在場由使用者調、無人值守由 config 釘死；導航與登入在 `.env` 白名單內可代勞、白名單外由使用者自己做；品牌內選款/進入遊戲由 AI 操作。
---

# test-game-brand

第三方電子遊戲平台**批次測試**。核心堅持：**品牌無預設、站點無預設** —— **瀏覽器由 AI 啟動**（見下方「啟動瀏覽器」）；**導航與登入：`.env` 白名單內的站可代勞、白名單外由使用者自己做**（見「導航與登入：先查白名單」），**建議停在該品牌遊戲大廳**，本 Skill 從當前頁接手；**品牌內選款/進入/退出遊戲由 AI 自行操作**（使用者不必自己開遊戲）。**同站內品牌切換可代勞**：當前分頁已是目標站點、只是停在別的品牌分類 → 先宣告「目前停在 X，我切到 <brand>」再點品牌頁籤切換；**不在目標站點／未登入／多個站點分頁分不清哪個是目標 → 停下請使用者放到對的頁面**，不要猜。

## 指令格式
```
/test-game-brand <mode> <brand> [flags]
  mode  : calibrate | run | post
  brand : 品牌 slug（小寫），對應 brands/<brand>.yaml
  flags : --range a-b  --resume-from gNNN  --dry-run
```
先判斷 `<mode>`，照對應段落做。`<brand>` 沒給就先問使用者，不要亂猜。

## 啟動瀏覽器（AI 負責，所有 mode 共用）
**瀏覽器由 AI 開。** 任一 mode 起手先確認瀏覽器在不在：
1. `browser_tabs list`（或任一 browser 工具）試探；報錯／沒有任何分頁 → 瀏覽器還沒起來。
2. 用 `browser_navigate` 到 `about:blank` 觸發啟動。config 一律 `viewport: null`（頁面 viewport 跟著真實視窗走）。

### 🔴 視窗尺寸有兩種模式，先確認自己在哪一種

用 `browser_evaluate` 讀 `window.innerWidth/innerHeight`，跟 `.env` 的 `WINDOW_SIZE`（若有設）比對：

| 模式 | 設定 | viewport 誰決定 | 起手行為 |
|---|---|---|---|
| **有人在場**（預設） | `playwright-mcp.config.json`（`viewport: null`） | **跟著使用者手動調的視窗走** | 停下請使用者調視窗＋導航＋登入，**等回覆再往下** |
| **無人值守** | `playwright-mcp.unattended.json`（`contextOptions.viewport: {W,H}`） | **建立 context 當下釘死** | 尺寸已確定，**不停等**，直接往下 |

- 有人在場模式：告訴使用者「瀏覽器已開好，請你 (a) 把視窗放到要用的螢幕並調成滿版、(b) 導航到站點並登入、(c) 停在 `<brand>` 大廳（另開後台投注報表分頁）」，然後**等使用者回覆再往下**。多螢幕環境解析度不同，AI 不替使用者選螢幕。
- 無人值守模式：viewport 在**建立 context 的那一刻**就釘死了，不需要也不可以在執行期調整（`browser_resize` 被 hook 硬擋，那是對的）。讀到的 viewport 與 `.env` 的 `WINDOW_SIZE` 不符 → **fail-fast 回報**（多半是 `.mcp.json` 的 `--config` 沒指到 unattended 那份、或改完沒重啟 Claude Code），**不要自己想辦法喬**。

> 為什麼要兩種：2026-08-08 拿掉 `--start-maximized` 的理由是「多螢幕 AI 選錯反而卡人」—— 這個理由只在**有人在場**時成立。無人值守時沒有人可以調視窗，少了確定性尺寸就會卡在第一步（viewport 不符 → fail-fast），而 resize 又被擋死，等於沒有出口。
>
> 🔴 **不要改用 `--window-size`**：那設的是 OS 視窗大小，viewport 會被分頁列/網址列吃掉一截。
> 實測 `--window-size=1920,1080` + `viewport:null` → 實際 viewport 是 **1919×992**（寬少 1px、高少 88px），
> 拿它跟 `WINDOW_SIZE` 做相等比對會**每次都 fail**。`contextOptions.viewport` 才是完全相等、跨機器可重現的。

### 導航與登入：先查白名單

4. 讀 `.env`，看目標站是否有對應的 `SITEn_HOST` 與 `SITEn_USER`/`SITEn_PASS`：

   **(a) 在白名單內且有憑證** → AI 可自行完成，**先宣告要導到哪個 host**，然後：
   - `browser_navigate` 到 `SITEn_LOGIN_URL`（留空則用 `SITEn_HOST` 首頁的登入入口）
   - 填憑證送出：**前台**用 `SITEn_USER`/`SITEn_PASS`；**後台**（post 對帳要用）用 `SITEn_ADMIN_USER`/`SITEn_ADMIN_PASS`。
     🔴 兩套是不同帳號（前台會員 vs 後台代理），**欄位不可混用**。
   - 🔴 **登入後實際驗登入態**（頁面還有「登入/註冊」鈕＝未登入；找會員/錢包元素佐證）。
     代填成功 ≠ 登入成功；驗不過就 fail-fast 回報，**不要重試第二組憑證、不要猜密碼**。
   - 若持久 profile 已是登入態，直接沿用，不必重登。

   **(b) 不在白名單內** → 🔴 **停下請使用者處理**，不代勞導航、不代填帳密。
   **不要**從歷史紀錄、書籤、或使用者隨口提到的網址猜站點 —— 白名單是硬判準，比對 host 不在 `.env` 就 fail-fast。

   🔴 **憑證只進輸入框**：不回顯在對話、不寫進報告/`note`/截圖/`games.jsonl`。
   截圖若可能拍到已填入的密碼欄，先關閉該畫面再截，或裁掉該區域。

🔴 **viewport 基準以 calibrate 當下讀到的為準**（不是假設滿版）：calibrate 讀 viewport 寫進 yaml，run 時比對，不一致 fail-fast。**座標是 viewport-specific**，所以要提醒使用者：決定螢幕與視窗大小後，整個 calibrate → run 週期**不要搬動視窗或換螢幕**（雙螢幕解析度不同，搬過去座標即失效）。AI 一律不呼叫 `browser_resize`（hook 硬擋）；使用者手動調整視窗不受影響。

補充：MCP 用**持久 profile**（`~/.cache/ms-playwright-mcp/`），先前的登入 session 與分頁常還在，使用者導航過去可能已是登入態；但**仍要按既有規則實際驗登入態**（頁面還有「登入」鈕＝未登入），不可假設。

---

## Mode: `run`（Step 4-5，已實作）

**前提**：使用者已登入、已停在該品牌的**遊戲列表頁（大廳）**，且**瀏覽器視窗已由使用者調成滿版**（座標靠滿版一致；跑前提醒使用者過程中不要改視窗大小或換螢幕）。**瀏覽器沒開就先由 AI 啟動**（見上方「啟動瀏覽器」）。白名單內的站 AI 可自行導航與登入；白名單外才請使用者處理。
- 🔴 **雙分頁 pre-flight**：開跑前用 `browser_tabs list` 確認**同時存在**「站點品牌大廳分頁」與「後台投注報表分頁」。缺後台 → 提醒使用者先開好（提醒不硬擋 run，但講明之後 post 對帳一定要有）；兩分頁都在就記下各自 index，**跑批全程不碰後台分頁**。
- 🔴 **確認該品牌遊戲錢包已有餘額**（不只是登入）：很多第三方電子品牌有**獨立遊戲錢包**，要先從主錢包轉帳進去才能下注。沒轉錢的症狀＝遊戲內餘額 0／下注點了不登錄／後台 0 筆。餘額為 0 就停下請使用者先儲值，不要硬跑（會整批 BET_NOT_PLACED）。實際驗證由下方「canary 先行」步驟做，不必只憑口頭提醒。

### 1. 載入並驗證 brand 參數
- 讀 `brands/<brand>.yaml`。不存在 → 停下，提示「先跑 `calibrate <brand>`」。
- `_calibration_gaps` 非空 → 停下，列出缺的欄位請使用者補，**不要硬跑**（防 default 偷渡）。

### 2. 確認品牌頁 + 記下 lobby_url
- 用 `browser_evaluate` 讀 `location.href` 與頁面現況。
- **同站停錯品牌 → 自行修正**：當前頁是目標站點的遊戲列表、只是選著別的品牌分類 → 宣告「目前停在 X，我切到 <brand>」，點站內品牌頁籤切過去，再記 `lobby_url`。
- **跨線問題**：還在登入頁/後台/不是目標站點/多站分頁分不清 → 目標站在 `.env` 白名單內就自行導航（先宣告；未登入則代填憑證），**白名單外一律停下**請使用者放到對的頁面後再跑。
- 確認停在目標品牌列表頁後，記當前 URL 為 `lobby_url`。

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

#### ⚡ 快路徑：用平台 API 讀餘額取代逐輪截圖（**seamless 共用錢包的站才適用**）
遊戲多半是跨域 iframe／canvas，餘額只能裁切截圖判讀，10 輪下來很貴又容易誤讀。
若該站是 **seamless 共用錢包**（無獨立遊戲錢包、不需轉帳），可改用站台自己的餘額 API
（從 network 面板找，通常是 `MemberWallet/getBalance` 之類），在 `browser_evaluate` 裡帶站方真實 header 呼叫。
2026-08-14 實測：10 輪下注從「逐輪裁切截圖判讀」變成純數值比對，整段只花約 2 分鐘，且 API 多 2 位小數精度。

🔴 **啟用前必須先驗等價性，不可假設**：canary 那一注前後各比一次
「**API 讀到的餘額 == 遊戲內顯示的餘額**」（實測 API `6874.7335` / 遊戲內 `6874.73`，只差顯示截斷）。
**兩者不一致就退回截圖判讀** —— 有獨立遊戲錢包的站（手動轉帳或進場自動掃入）**一律不適用**，
那些站的主錢包是快取，delta 必須以遊戲內餘額為準。

⚠️ 快路徑只換掉「讀餘額」這一件事，**不改變任何判準**：PASS 仍要驗扣款、`delta==0` 仍不准 PASS、
成立與否的最終閘門仍是後台注單筆數。

### 6. 切批 + 派發 game-batch-runner
- 依 `batch.size`（預設 8）把清單切成數批。
- 對每批，用 **Agent 工具 spawn `game-batch-runner`**（subagent_type: `game-batch-runner`），prompt 帶入：完整 `brand_params`、`lobby_url`、該批 `games`、`report_dir` 絕對路徑、`flags`、**`expected_start_balance`**（上一批回報的結束餘額；首批＝canary 後餘額）——runner 開批第一款讀到的 before 若明顯偏離（>1 個注額），note 記「疑前批晚結算入帳/錢包同步」供對帳留意，不擋跑。
- `batch.parallel_batches==1`（預設）：**一批跑完再下一批**（共用同一個瀏覽器分頁，不能並行搶滑鼠/座標）。>1 時才考慮多分頁並行（目前保守，先序列）。
- 每個 batch-runner 自己 append `games.jsonl`；你收集它的回報。

### 6.5 收尾重試一輪（LOAD_FAIL / STUCK）
- 全批跑完後，收集 status 為 `LOAD_FAIL` / `STUCK_RECOVERED`（未完成驗證）的款，**重試一次**（款數少編排層自跑、多就再派一小批）。
- 重試成功 → 該款在 games.jsonl **補一行新紀錄**（note 記「重試後成功」，彙整時以新行為準）；仍失敗 → 維持原狀態，summary 註明「已重試 1 次」。
- `BET_NOT_PLACED` **不自動重試**（多半是環境未開放下注、重試昂貴），summary 建議人工/開發確認即可。

### 7. 彙整報告（腳本產出，不手刻）
- 🕒 先用 Bash `date '+%Y-%m-%d %H:%M:%S'` 把 **`ended_at`** 寫回 `run-meta.json`（qa-report 執行耗時的 fallback 來源）。
- 跑 **`uv run .claude/skills/test-game-brand/gen_run_artifacts.py <report_dir>`**（無 uv 退 `python3`）：從 `games.jsonl` 確定性產出 `run-summary.md` + `games.csv`（含注單號/後台遊戲名欄；run 完 betid 空白屬正常，post 釘回後重跑即帶入）。**不要手刻這兩份**——數字要可被人工核對。
- 腳本輸出的 JSON（各 status 計數、PASS 總 delta）拿來回報使用者；🔴 明確標示 PASS 數 = 有確認餘額變化的款數，**不是只 click 成功的款數**。既有 `run-meta.json` 其他欄不動。

### run mode 驗收（Test 2）
歷史驗收基準（含具體品牌/數值）見 `docs/acceptance-fixtures.md`——具體值屬歷史紀錄、非預設，勿當校準參數用。

---

## Mode: `calibrate`（Step 7，已實作 — 半互動）

**前提**：使用者已登入、已停在該品牌的**遊戲列表頁（大廳）**（同站停錯品牌時 AI 宣告後自行切換，同 run mode 規則），且**瀏覽器已由使用者調成滿版**（calibrate 只讀當下 viewport 並記為基準，run 時要一致，所以校準當下就要是日後跑批的視窗狀態／同一台螢幕）。**sample 遊戲由 AI 自行挑選進入**：預設挑**大廳第一款**，點開等載入完成；載入失敗（卡 loading 超過 ~60s）自動換下一款，並把換款原因記進 calib-meta。使用者不必自己開遊戲。
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
- 🔴 **自動重產最終報告**：betid/bo_gamename 釘回後，重跑 `gen_run_artifacts.py`（run-summary/CSV 帶入注單號），並重產 qa-report（report_dir 裡既有哪個版型就重產哪個；預設 full+simple 都產），最後向使用者宣告最終版路徑（沿用 qa-report 完成宣告規則）。

### post mode 驗收（Test 3）
歷史驗收基準見 `docs/acceptance-fixtures.md`。通則：`reconcile.md` 全數對上、或誠實標出差異與原因。

---

## 鐵則（貫穿所有 mode）
- 🔴 **驗餘額才能 PASS**：`delta==0`/讀不到/不確定一律不准 PASS。這條焊死在 `game-batch-runner` 裡，編排層也要在 summary 誠實呈現。delta 對所有遊戲類型通用（拉霸/crash/keno…）：未中＝−bet、中獎＝+淨額。
- 🔴 **下注前先確認下注成立**：下注鈕點了≠成立（crash 要在倒數窗口、keno 要先選號）。確認鈕狀態變/有「已下注」提示/餘額已扣，才讀 delta；否則重點，連續失敗記 `BET_NOT_PLACED`，不可標 PASS。
- 🔴 **投注額 > 20 一律先請示使用者**：預設用低籌碼（如 3）跑。要調高 BET 前先算單注金額，>20 就停下問使用者（crash「兩注面板」同回合兩注合計也要算）。捕魚等連續投注型態判準為**單發砲倍**（`bet_per_shot`）——報告「投注」欄是該款總額（發數×砲倍），不可直接拿來判 >20。**絕不點「全押/all-in」**（會押整個餘額）。
- 🔴 **遊戲品牌錢包要先有錢**：第三方品牌常有獨立遊戲錢包，需先轉帳；餘額 0 就停下請使用者儲值（見 run 前提）。
- 🔴 **注單單號（betid）是對帳的唯一可靠鍵**：前台常看不到注單單號，對帳時由 `backoffice-reconciler` 從後台擷取每筆注單號釘回 games.jsonl（`betid`/`bo_winlose`），並交叉驗證「遊戲內 delta == 後台輸贏」。
- 🔴 **卡住換新分頁**（CLAUDE.md 鐵則）：60s 無回應 → 新 tab 從 `lobby_url` 重啟，標 `STUCK_RECOVERED`，不在原頁 debug。
- 🔴 **滿版、不 resize**（CLAUDE.md 鐵則；`browser_resize` 已被 PreToolUse hook 硬擋）：viewport 一律「讀+比對」，不一致 fail-fast。**AI 只啟動瀏覽器、不決定視窗大小**；滿版由使用者自己調（多螢幕要固定同一台），跑前提醒過程中別動視窗。
- 🔴 **測試產物一律歸位 `report_dir/`**（CLAUDE.md 鐵則；裸檔名截圖已被 hook 硬擋）：截圖 `filename` 給完整路徑（一般 `report_dir/screenshots/`、對帳頁 `report_dir/backoffice/`、校準圖 `calib_dir/`）。編排層 spawn subagent 時務必傳入 `report_dir` **絕對路徑**，並要求「所有截圖/中繼檔用該路徑為前綴」。

## 邊界
本 Skill **負責啟動瀏覽器**（視窗尺寸見「啟動瀏覽器」的兩種模式）。導航與登入：**`.env` 白名單內的站可自行完成**（前台用 `SITEn_USER`/`SITEn_PASS`、後台用 `SITEn_ADMIN_USER`/`SITEn_ADMIN_PASS`），**白名單外不代勞**；**品牌內選款/進入/退出遊戲、同站內品牌切換則由 AI 操作**（切品牌前先宣告），使用者建議停在品牌大廳。頁面對不上（還在登入頁/不是目標站點/後台當前頁/多站分不清目標）就 fail-fast 提示，不要替使用者跨站操作。**post mode 的後台篩選條件（時間區間／品牌／會員帳號）目前仍由使用者設定** —— 白名單制解掉的是「登入」，不是「篩選」。後台已登入但沒篩好，仍要停下請使用者處理。