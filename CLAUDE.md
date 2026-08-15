# CLAUDE.md

給在這個 repo 工作的 Claude Code 的專案指引。團隊共用，會被 commit。
細節文件：使用說明見 [`README.md`](README.md)，完整架構見 [`docs/architecture-plan.md`](docs/architecture-plan.md)。

## 這個專案是什麼
第三方電子遊戲平台的**批次測試自動化**：Skill `/test-game-brand`（calibrate 探參數 / run 批次跑+驗餘額 / post 對帳）+ Skill `/qa-report`（產 HTML 報告，`--simple` 精簡版）+ 四個 subagent（game-batch-runner、brand-calibrator、backoffice-reconciler、qa-report-writer）。

## 核心不變量（不可違反）
- **品牌無預設、站點無預設** — **repo 不 track** 任何品牌參數、帳號、網址、憑證。它們都在**本機 gitignored 檔**：品牌參數在 `brands/<brand>.yaml`（calibrate 產出），站點參數與帳密在 `.env`（範本 `.env.example`）。防線是 `.gitignore` ＋ pre-commit 的 secret-scan ＋ 本機敏感詞表 —— 三道都不要繞過。
- **導航與登入：預設由使用者，`.env` 列名的站可代勞** — **瀏覽器由 AI 啟動**（playwright MCP 開空白頁；持久 profile 常保留既有登入 session）；**品牌內選款、進入/退出遊戲由 AI 自行操作**（calibrate 自挑大廳第一款當 sample、run 逐款自開）；**同站內品牌切換 AI 可代勞**（先宣告再切）。導航與登入分兩種情況：

  | 情況 | 導航 | 登入 |
  |---|---|---|
  | **站點在 `.env` 白名單內且有憑證** | ✅ AI 可自行導航（先宣告） | ✅ AI 可用 `SITEn_USER`/`SITEn_PASS` 代填 |
  | **其他任何站點** | 🔴 **不代勞**，停下請使用者處理 | 🔴 **絕不代填帳密** |

  🔴 **白名單是硬判準**：導航前先比對目標 host 是否出現在 `.env` 的 `SITEn_HOST` / `SITEn_ADMIN`，**不在清單內一律 fail-fast**，不要從歷史紀錄、書籤或使用者隨口提到的網址猜站點。
  🔴 **憑證只進輸入框，不進任何其他地方** —— 不回顯在對話、不寫進報告/`note`/截圖、不寫進 `games.jsonl`。`.env` 只放測試站帳號。
  🔴 **登入後仍要實際驗登入態**（頁面還有「登入」鈕＝未登入）—— 代填成功不等於登入成功，這一步不因自動化而省略。
  🔴 **只有編排層（skill）能導航與登入；六個 subagent 一律不行**（batch-runner／launch-runner／scout／calibrator／reconciler／report-writer 都從編排層準備好的當前頁接手）。這條不因白名單而鬆動 —— 把導航收斂在一處，走錯站時只有一個地方要查。
- **驗餘額才能 PASS** — 只 click SPIN 不驗餘額變化＝假 PASS。`delta==0` / 讀不到 / 不確定一律不准 PASS（先前 65 款翻車根因）。
- **視窗尺寸固定、不 resize** — 座標是 viewport-specific，尺寸一變座標全失效；**一律不呼叫 `browser_resize`**，viewport 只「讀+比對」，不一致 fail-fast。尺寸怎麼來的分兩種：**有人在場**＝使用者手動調滿版（預設 config，`args: []`）；**無人值守**＝`contextOptions.viewport: {W,H}` 在建立 context 當下釘死（`playwright-mcp.unattended.json`，gitignored）。兩者都不經過 resize。
- **卡住換新分頁** — 60s 無回應 → 開新 tab 從 lobby URL 重啟，標 `STUCK_RECOVERED`，不在原頁 debug。

（「不 resize」與「截圖歸位」兩條已由 `.claude/settings.json` 的 PreToolUse hook **機器強制**：`browser_resize` 一律 deny、裸檔名截圖一律 deny。被擋到就照提示改，不要繞。）

## Git commit 規範
- 🔴 **commit 訊息絕不加任何 Claude / AI 署名**（不加 `Co-Authored-By: Claude`、不加 `🤖 Generated with Claude Code`）。用 `/git-commit` skill 會自動遵守。
- **絕不 commit**：`reports/`、截圖、token、`.mcp.json`（含本機路徑）、`brands/<brand>.yaml`、`settings.local.json` — `.gitignore` 已擋，別用 `-f` 硬加。
- 含疑似密碼 / token / 本機路徑 / 帳號的改動，commit 前先提醒使用者。

## 環境安裝（重點坑）
完整跨平台步驟見 README「跨平台安裝」。最常踩的：
- **別 `sudo npx`** — 若 Node 用 nvm 裝，sudo 會重設 PATH 導致 `npx: command not found`。npx 用自己身分跑，讓工具自己跳 sudo 裝 apt。
- 中文站點要裝 **CJK 字型**（Debian/Ubuntu：`fonts-noto-cjk`），否則繁中變方塊。
- 改 `.mcp.json` 後要**重啟 Claude Code**。

## 操作慣例
- 開跑測試前**先確認已登入**（頁面還有「登入」鈕＝未登入，讀不到餘額就不能驗 PASS）。
- SPIN 後要**等中獎動畫結算完**再讀餘額（讀兩次一致才算）；大廳錢包是快取，delta 以**遊戲內餘額**為準。
- canvas/iframe 遊戲沒有可選元素，SPIN 等按鈕用座標點 `page.mouse.click(x,y)`（`browser_run_code_unsafe`），`browser_click` 對 canvas 無效。
- 🔴 **測試產物一律歸位到 `report_dir/`，不准落在 repo 根**：`browser_take_screenshot` 的 `filename` 一律給**完整路徑** `report_dir/screenshots/<名稱>.png`（對帳頁截圖給 `report_dir/backoffice/`）。**裸檔名（如 `x.png`）會被寫到 MCP 的 cwd＝repo 根、到處散落**。無 report_dir 的一次性探測，截到暫存目錄或 calib_dir，也**不要落在 repo 根**。截圖、CSV、TSV、暫存 HTML 等所有中繼檔同理。（`reports/` 與根層影像已 gitignore，但仍要主動歸位，別靠 ignore 兜底。）
