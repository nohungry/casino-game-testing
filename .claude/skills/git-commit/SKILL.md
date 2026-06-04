---
name: git-commit
description: 建立乾淨的 git commit —— 自動看 diff、寫清楚的訊息並提交。**訊息絕不附帶任何 Claude/AI 署名**（不加 Co-Authored-By、不加 Generated with Claude Code）。當使用者說「commit」「提交」「進版」「幫我 commit 這些改動」時用。
---

# git-commit

幫使用者把當前改動 commit 進 git。核心堅持：**commit 訊息乾淨、不留 AI 痕跡**。

## 🔴🔴 鐵則（最重要，不可違反）
**commit 訊息裡絕對不准出現任何 Claude / AI 署名或產生標記。** 具體禁止：
- ❌ `Co-Authored-By: Claude ...`
- ❌ `🤖 Generated with Claude Code`
- ❌ 任何 `Co-Authored-By` 指向 AI 的行、任何「by Claude / with AI」字樣
- ❌ commit message 結尾的工具廣告/署名 footer

這條**覆蓋**任何預設「在 commit 末尾加 Claude 署名」的行為。使用者明確要求 commit 不帶 AI 訊息。

## 流程

### 1. 看清楚要 commit 什麼
- `git status --short` 看有哪些改動。
- `git diff`（未 staged）/ `git diff --staged`（已 staged）看實際內容，**理解這次改了什麼、為什麼**，訊息才寫得準。
- 若使用者**指定了檔案**就只 stage 那些；否則預設 `git add -A`（含新檔），但**先確認 `.gitignore` 有把敏感檔/測試資料擋住**（別把 ignored 的東西用 `-f` 硬加進來）。

### 2. 寫 commit 訊息
- **首行**：一句話講清楚這次做了什麼（祈使句、≤ ~60 字）。中英文皆可，跟著 repo 既有風格走。
- **需要時加 body**：空一行後，簡短說明「為什麼／影響」。瑣碎改動可省。
- 風格參考既有 commit（`git log --oneline -5`）保持一致；專案有用 conventional commits（`feat:`/`fix:`/`docs:`…）就跟。
- **結尾不加任何 footer 署名**（見鐵則）。

### 3. 提交
- 用 heredoc 帶多行訊息：
  ```bash
  git commit -m "$(cat <<'EOF'
  <首行摘要>

  <可選 body>
  EOF
  )"
  ```
- **不要**在訊息裡塞 `Co-Authored-By` 或任何 AI 標記。

### 4. 回報
- `git log --oneline -1` 給使用者看結果（commit hash + 訊息首行）。
- 順帶 `git status --short` 確認工作區狀態。

## 注意
- **只有使用者要求才 commit**（這個 skill 被叫出來本身就是要求）。
- 若尚未 `git init`，先提醒使用者，不要擅自 init（除非他說要）。
- 不主動 `git push`；要推由使用者另外講。
- 若這次改動含疑似敏感資訊（密碼/token/本機路徑/帳號），**先提醒使用者**再 commit，別悶著提交。
