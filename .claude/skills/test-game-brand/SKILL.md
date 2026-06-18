---
name: test-game-brand
description: 批次測試第三方電子遊戲平台的某個品牌。三個 mode：calibrate（探參數）/ run（批次跑+驗餘額+出報告）/ post（對帳）。唯一必填參數是品牌名；站點隱含於使用者已開好的當前頁面。Skill 不導航、不登入。
---

# test-game-brand

第三方電子遊戲平台**批次測試**。核心堅持：**品牌無預設、站點無預設、Skill 不導航不登入** —— 使用者自己開瀏覽器、登入、停在對的頁面，本 Skill 從當前頁接手。

## 指令格式
```
/test-game-brand <mode> <brand> [flags]
  mode  : calibrate | run | post
  brand : 品牌 slug（小寫），對應 brands/<brand>.yaml
  flags : --range a-b  --resume-from gNNN  --retry-oops  --dry-run
```
先判斷 `<mode>`，照對應段落做。`<brand>` 沒給就先問使用者，不要亂猜。

---

## Mode: `run`（Step 4-5，已實作）

**前提**：使用者已登入、已停在該品牌的**遊戲列表頁（大廳）**，且**瀏覽器視窗已滿版**（座標靠滿版一致，跑前先提醒使用者維持滿版、過程中不要改視窗大小）。

### 1. 載入並驗證 brand 參數
- 讀 `brands/<brand>.yaml`。不存在 → 停下，提示「先跑 `calibrate <brand>`」。
- `_calibration_gaps` 非空 → 停下，列出缺的欄位請使用者補，**不要硬跑**（防 default 偷渡）。

### 2. 記下 lobby_url（fail-fast）
- 用 `browser_evaluate` 讀 `location.href`，記為 `lobby_url`。
- 看起來不像遊戲列表頁（例如還在登入頁/後台）→ 提示使用者確認頁面後再跑。**Skill 不替使用者導航。**

### 3. 抓遊戲清單
- 用 `browser_snapshot` 或 `browser_evaluate`，依 `launch.selector_pattern` 抓出當前頁所有遊戲（名稱 + 出現順序）。
- 建立清單：`idx`(從 1 起的全域序號)、`name`、`nth`(同名第幾個)。
- 套用 `--range a-b`（只留序號 a..b）與 `--resume-from gNNN`（從該序號起）。
- 把抓到的清單與總數回報給使用者確認數量合理（例如 品牌H 應 ~247）。

### 4. 建報告資料夾
- `reports/<brand>-<YYYYMMDD-HHMM>/`，內含 `screenshots/`。
- 時間戳用 `date +%Y%m%d-%H%M`（Bash 取，不要自己編）。
- 寫一個 `run-meta.json`：brand、lobby_url、range、總款數、batch size、起始時間。

### 5. 切批 + 派發 game-batch-runner
- 依 `batch.size`（預設 8）把清單切成數批。
- 對每批，用 **Agent 工具 spawn `game-batch-runner`**（subagent_type: `game-batch-runner`），prompt 帶入：完整 `brand_params`、`lobby_url`、該批 `games`、`report_dir` 絕對路徑、`flags`。
- `batch.parallel_batches==1`（預設）：**一批跑完再下一批**（共用同一個瀏覽器分頁，不能並行搶滑鼠/座標）。>1 時才考慮多分頁並行（目前保守，先序列）。
- 每個 batch-runner 自己 append `games.jsonl`；你收集它的回報。

### 6. 彙整報告（讀 `games.jsonl` 全部行，產三份）

**(a) `run-summary.md`**：
- 總款數、各 status 計數、覆蓋率（跑完款數/總數）。
- **PASS 款的總 delta**（驗收看這個）。
- 列出所有非 PASS 款（status + note），方便人工跟進。
- 🔴 明確標示：PASS 數 = 有確認餘額變化的款數，**不是只 click 成功的款數**。
- **逐款明細表**（Markdown）：欄位 `編號 / 遊戲名 / 進入前 / 進入後 / delta / 注額 / 中獎 / spin 時間 / 狀態`，一眼看完每款前後金額與下注時刻。

**(b) `report_dir/games.csv`**（Excel 可直接開、可篩選）：
- 表頭：`idx,name,before_bal,after_bal,delta,bet,win,before_read_time,spin_time,after_read_time,status`
- 每款一列，順序同 `games.jsonl`。中文名含逗號要正確處理（用引號包裹）；建議用 Bash/`python3` 從 `games.jsonl` 轉出，不要手刻。

**(c)** 既有 `run-meta.json` 不動。

> CSV/明細表的 `win` 與三個時間欄直接取自 `games.jsonl`（game-batch-runner 已寫入）；若舊報告沒有這些欄位，留空即可。

### run mode 驗收（Test 2）
使用者開 品牌H 大廳 → `/test-game-brand run brandh --range 1-5` → 預期：
- `games.jsonl` 5 行、全 `PASS`，每行含 `win` / `before_read_time` / `spin_time` / `after_read_time`（三時間遞增、格式 `YYYY-MM-DD HH:MM:SS`）
- 每款 `delta ≈ -50` 且 `delta ≈ win - bet`，5 款總 delta ≈ **-250**
- `screenshots/` 有 g001..g005 的 loaded / bal-before / spin / bal-after 共 20 張
- 產出 `games.csv`，`run-summary.md` 含逐款明細表

---

## Mode: `calibrate`（Step 7，已實作 — 半互動）

**前提**：使用者已開好、已載入**一款 sample 遊戲**（停在可玩畫面，不是大廳），且**瀏覽器已滿版**（calibrate 只讀當下 viewport，run 時要一致，所以校準當下就要是日後跑批的滿版狀態）。
**互動模式：半互動** —— AI 自動探測，但關鍵欄位（尤其 spin.xy、balance 讀法）截圖給使用者確認後才寫 yaml；探不到的進 `_calibration_gaps`，不用 default 偷渡。

### 1. 準備
- 若 `brands/<brand>.yaml` 已存在 → 提示會覆蓋，先問使用者要不要續校準。
- 建 `reports/<brand>-calib-<YYYYMMDD-HHMM>/` 放探測截圖（時間戳用 `date` 取）。

### 2. 派發 brand-calibrator 探測
- spawn `brand-calibrator`（subagent_type: `brand-calibrator`），給 `brand`、`calib_dir`。
- 它回傳：`draft_yaml`、`field_confidence`、`needs_confirm`、`calibration_gaps`、`screenshots`。

### 3. 🔴 半互動確認（這步是本 mode 的重點，不可略過）
- 把 `needs_confirm` 的項目逐一**呈現給使用者**，附上對應截圖路徑：
  - **spin.xy**：顯示候選座標與標注截圖，問使用者「SPIN 是否在這？」。calibrator 已用餘額變化實測過的話講明（high 信心）。
  - **balance 讀法**：說明是文字讀到還是要靠截圖視覺判讀，給 balance-region 截圖確認金額格式對不對。
  - 其他 med/low 信心欄位也一併確認。
- 用 AskUserQuestion 或直接提問；使用者更正的值覆蓋 draft。

### 4. 寫入 yaml
- 確認後的值寫 `brands/<brand>.yaml`（符合 `_schema.yaml` 結構）。
- 仍未確定的欄位 → 留在 `_calibration_gaps`（**非空代表此 yaml 還不能 run**，明確告知使用者要補哪些才能跑 run）。
- 落地後回報：哪些 high/med/low、gaps 還剩什麼、下一步可否直接 `run`。

### calibrate mode 驗收（Test 1）
使用者開一款 品牌H sample → `/test-game-brand calibrate brandh` → 產出 `brands/brandh.yaml`，其中 `spin.xy` 接近 **(1283, 857)**、`spin.viewport` 記錄了當下 viewport、balance 讀法有著落。

## Mode: `post`（Step 6，已實作）

對帳：把某次 run 的 `games.jsonl` 跟後台 bet-report 比對，產 `reconcile.md`。

### 1. 🔴 先提醒使用者手動開好後台（這步一定要做）
- 後台**由 QA 人員手動開啟**，Skill 不導航不登入。下指令前明確提醒使用者：
  「請先在瀏覽器手動開好**後台 bet-report**、**篩好條件**（時間區間涵蓋本次 run、品牌/帳號對上），並停在結果頁。」
- 使用者確認已開好、已篩好，才往下做。

### 2. 找對要對帳的 run
- 預設用最近一次 `reports/<brand>-*/`（非 calib）；多個時列出讓使用者選，或吃 flag 指定。
- 讀該 `report_dir/games.jsonl`。沒有或空 → 提示先跑 `run`。

### 3. 派發 backoffice-reconciler
- spawn `backoffice-reconciler`（subagent_type: `backoffice-reconciler`），給 `report_dir`、`brand`、`match_keys`（預設 `["name"]`，使用者要嚴格比對可加 `bet`）、`amount_tolerance`（預設 0.01）。
- 它從**當前後台頁**讀資料、翻頁、對帳、寫 `report_dir/reconcile.md`。

### 4. 回報
- 帶出 reconciler 的結果：matched / missing_in_bo / extra_in_bo 數、金額是否平、資料品質警告（後台是否可能沒抓全）。
- 🔴 **特別點出 missing_in_bo**：games.jsonl 標 PASS 卻在後台找不到的款，是最該人工查的（假 PASS 或後台未涵蓋）。

### post mode 驗收（Test 3）
5 款跑完 → 使用者手動開後台篩好 → `/test-game-brand post brandh` → `reconcile.md` 對上 5/5（或誠實標出差異與原因）。

---

## 鐵則（貫穿所有 mode）
- 🔴 **驗餘額才能 PASS**：`delta==0`/讀不到/不確定一律不准 PASS。這條焊死在 `game-batch-runner` 裡，編排層也要在 summary 誠實呈現。
- 🔴 **卡住換新分頁**：60s 無回應 → 新 tab 從 `lobby_url` 重啟，標 `STUCK_RECOVERED`，不在原頁 debug。
- 🔴 **滿版、不 resize**：座標一律靠「瀏覽器滿版」維持一致。**所有 mode、所有 subagent 都不准呼叫 `browser_resize` 或任何改視窗大小的工具**（程式 resize 會有顯示問題）。viewport 一律「讀+比對」，不一致 fail-fast。跑前提醒使用者把視窗滿版且過程中別動。

## 邊界
本 Skill **不**負責導航、登入、開後台、選篩選條件 —— 那是使用者跑前的責任。頁面對不上就 fail-fast 提示，不要替使用者操作站點。**post mode 尤其要先提醒使用者手動開好後台 bet-report 並篩好條件。**