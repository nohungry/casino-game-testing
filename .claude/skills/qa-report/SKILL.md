---
name: qa-report
description: 把一次 run 的測試結果產成「QA Manager 視角」的單檔 HTML 報告（裁決 + 關鍵指標 + 餘額鏈曲線 + 逐款明細表 + 建議）。逐款明細表含每款進入前/後金額、win、SPIN 時間，供人工逐筆核對。當使用者說「產 QA 報告」「出 HTML 報告」「qa-report」時用。讀現成 report_dir，不跑遊戲、不導航、不登入。
---

# qa-report

把某次 `run` 的產物（`games.jsonl` 等）整理成一份 **QA Manager 角度、可直接交付/呈現的單檔 HTML**（`qa-report.html`）。純 HTML+CSS、可離線開。**所有數字、餘額鏈曲線、逐款明細表都由產生器腳本從資料算出**（可被人工逐筆核對），只有裁決與建議文字是 AI 草擬。

## 指令格式
```
/qa-report [brand | report_dir] [--reviewer 名]
```
- 給 **brand**（如 `品牌B`）：取該品牌最近一次**非 calib** 的 `reports/<brand>-*/`（多個時列出讓使用者選）。
- 給 **report_dir 路徑**：直接用該資料夾。
- 都沒給：列出 `reports/` 下可用的 run 讓使用者選，不亂猜。
- `--reviewer`：報告署名，預設 `QA`。

## 步驟
1. **定位 report_dir**：
   - 確認資料夾存在且有 `games.jsonl`；沒有 → 停下提示「該 run 沒有 games.jsonl，請先 `/test-game-brand run`」。
   - brand 對到多個資料夾時，列出（含時戳）讓使用者挑，不要自己選最新就跑。
2. **派發 `qa-report-writer`**（subagent_type: `qa-report-writer`），prompt 帶入 `report_dir` 絕對路徑、`reviewer`。
   - 它讀資料 → 草擬裁決/建議寫 `qa-report-input.json` → 跑 `.claude/skills/qa-report/gen_qa_report.py` → 產 `report_dir/qa-report.html`。
3. **回報**：
   - 產出路徑 `report_dir/qa-report.html`。
   - 關鍵數字（總款數 / PASS / 異常款 / 餘額鏈斷點 / 截圖數 / 淨 delta）—— 以腳本輸出為準。
   - 資料品質提醒（例：此 run 無 `spin_time`/`win` → 明細表該兩欄空白屬正常）。
   - 若有非 PASS 款或餘額鏈斷點，**特別點出**，並說明已在報告 verdict／建議中標示。

## 產出內容（qa-report.html 區塊）
標題列(meta) → 測試結論裁決 → 01 關鍵指標 → 02 餘額鏈 SVG 曲線 → 03 方法與覆蓋 → 04 輸贏摘要 → **05 逐款明細表（編號/代碼/遊戲名/進入前/進入後/delta/win/SPIN時間/狀態，順序同遊戲序列表，供人工逐筆核對）** → 06 證據完整性 → 07 建議 → footer 來源檔。

## 鐵則
- **不跑遊戲、不導航、不登入、不對帳**：只讀現成 report_dir 產報告。
- **數字一律由 `gen_qa_report.py` 算**，編排層與 subagent 都不自行心算或竄改；報告的可信度來自「表是死的、可被人工核對」。
- 不嵌入實際截圖（裁決摘要型）；截圖證據另存在 `report_dir/screenshots/`，報告只描述其完整性。

## 相依檔案（本 skill 自帶）
- `.claude/skills/qa-report/gen_qa_report.py`：確定性產生器（讀 games.jsonl + run-meta + full-game-list + input.json，算指標/SVG/明細表，套模板輸出 HTML）。
- `.claude/skills/qa-report/qa-report-template.html`：HTML 模板（CSS + 區塊骨架 + 佔位符）。
- subagent `qa-report-writer`：編排「讀資料 → 寫 input.json → 跑腳本」。

## 驗收
對一個既有 run（如 `reports/品牌B-fullrerun-20260616-0326/`）跑 `/qa-report` → 產 `qa-report.html`：單檔可離線開、指標與 `run-summary.md` 一致、餘額鏈曲線點數＝款數、逐款明細表列數＝款數且可逐筆對照遊戲序列表。
