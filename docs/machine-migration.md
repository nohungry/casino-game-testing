# 換機器：記憶能不能直接複製？（2026-08-28）

**結論：能，記憶（`~/.claude/projects/<slug>/memory/*.md`）是純文字，整包複製即可 —— 但有一個路徑條件、四則內容要改、六個本機檔 git 帶不過去。**

> 本文的「舊機器現況」是在原機器實跑 `scripts/verify-env.sh` 驗證過的；
> 「新機器步驟」是**待跑的檢查清單**，不是已驗證的結論 —— 請在新機器上實際跑一次再回填結果。

---

## 1. 記憶怎麼搬

記憶目錄名 = **專案絕對路徑，把 `/` 換成 `-`**。舊機器是：

```
~/.claude/projects/-home-<使用者>-<專案路徑用-連接>/memory/   # 目前 78 個 .md
```

🔴 **新機器如果專案放在不同路徑，目錄名就不一樣，直接複製會載入不到。**

```bash
# 在新機器上先算出正確的目錄名（在專案根執行）
NEW_SLUG=$(pwd | sed 's#/#-#g')
mkdir -p ~/.claude/projects/"$NEW_SLUG"
# 從舊機器把整包 memory/ 複製到 ~/.claude/projects/$NEW_SLUG/memory/
```

`MEMORY.md` 是索引，一定要一起搬（少了它，個別記憶不會被載入）。

---

## 2. 搬過去後**必須改**的四則記憶（它們寫的是「這台機器」）

| 記憶 | 寫了什麼機器綁定的東西 | 新機器要做的事 |
|---|---|---|
| `project_baseline_viewport` | 基準 viewport **1908×912**（該機螢幕 1920×1080） | 見下面第 4 節，**先決定要不要沿用這個尺寸** |
| `project_wsl_browser_mcp_setup` | Chromium 路徑寫死 `chromium-1208`（現機實際是 **1228**） | 用 `ls ~/.cache/ms-playwright/` 查新版本號，改 `.mcp.json` 與這則記憶 |
| `project_casino_game_testing_overview` | 寫死了舊機器的專案絕對路徑 | 改成新機器路徑 |
| `project_wip_branch_uv_and_guardrail` | 換機器一次性設定（uv PATH／`core.hooksPath`／**重建 secret-scan 詞表**） | 照做一次；詞表是 gitignored，要自己重建 |

其餘 74 則（站點機制、對帳坑、下注判準、輪替紀錄…）與機器無關，可直接沿用。

---

## 3. git clone 帶不過來的本機檔（**全部 gitignored**）

| 檔案 | 內容 | 怎麼處理 |
|---|---|---|
| `.env` | 三站網址／前台後台帳密／機制參數／`WINDOW_SIZE` | **從舊機器複製**（範本 `.env.example` 只有鍵名）。用安全管道傳，別走聊天視窗 |
| `.mcp.json` | 含本機 Chromium 路徑 | `cp .mcp.json.example .mcp.json` 後**改路徑**（版本號會不同） |
| `playwright-mcp.unattended.json` | `contextOptions.viewport` | `cp *.example` 後填尺寸（見第 4 節） |
| `brands/*.yaml` | 校準座標（目前 1 份） | 沿用同尺寸才有效，否則重新 calibrate |
| `scripts/secret-scan.local-patterns` | pre-commit 敏感詞表 | **重建**（不入 repo 是刻意的） |
| `.venv/` | Python 3.13 環境 | 不要複製，`uv sync` 重建 |

`reports/` 也沒進 repo；要保留歷史報告就一起複製，不需要的話新機器從空的開始。

---

## 4. 最關鍵的一題：viewport 要不要沿用 1908×912

記憶裡有 **8 則帶座標**（真人窗口訊號、每日 SOP、各站機制與各型態的校準紀錄），
內容是下注區座標、SPIN 位置、籌碼列 clip、餘額截圖裁切框 —— **全部只在 1908×912 成立**。
要在本機列出是哪幾則：

```bash
grep -lE '\([0-9]{3,4},[0-9]{3,4}\)|clip ?\{' ~/.claude/projects/<slug>/memory/*.md
```

| 路線 | 做法 | 代價 |
|---|---|---|
| **A（建議）沿用 1908×912** | 用 `playwright-mcp.unattended.json` 的 `contextOptions.viewport` 把尺寸釘死，`.env` 的 `WINDOW_SIZE` 同步 | 只要新機器螢幕**不小於 1908×912** 就能完全重現，8 則座標記憶全部繼續有效 |
| **B 改用新尺寸** | 改 config＋`.env`＋`brands/*.yaml` 三處 | 上述 8 則記憶的座標**全部作廢**，真人窗口訊號要逐桌重新校準（每桌約 1 分鐘取樣） |

🔴 不論走哪條，**尺寸只能在建立 context 當下釘死，不准用 `browser_resize`**（hook 會擋）。

---

## 5. 新機器開工前跑這支

```bash
bash scripts/verify-env.sh
```

十個項目：Node/npx、Chromium 本體、`.mcp.json`（含 executable-path 是否真的存在）、
尺寸三處一致性、六個本機檔、`.env` 必要鍵（**只檢查鍵名，不印任何值**）、
uv/.venv/報告產生器、git hook 防線、中文字型、記憶目錄與 slug。

舊機器實跑結果：**FAIL 0、WARN 2**（WARN 是「node 來自 nvm，別 sudo npx」與環境無關的提醒）。

### 這支檢查不了、必須在 Claude Code 裡實測的兩件事
1. **viewport 實讀**：開 `about:blank` 讀 `window.innerWidth/innerHeight`，必須與 `.env` 的 `WINDOW_SIZE` **逐字相同**。
2. **三站登入態**：各登一次，確認頁面不再出現「登入」鈕（`.env` 白名單內的站可代勞）。

---

## 6. 建議順序

1. 新機器 `git clone` → `cp` 三份 example → 填路徑
2. `npx playwright install chromium`（Linux/WSL 加 `--with-deps`）＋中文字型
3. 從舊機器複製 `.env`、`brands/*.yaml`、（可選）`reports/`
4. `uv sync`、`git config core.hooksPath hooks`、重建 `secret-scan.local-patterns`
5. 複製 `memory/` 到**新 slug** 目錄；改第 2 節那四則
6. `bash scripts/verify-env.sh` → 全綠再進 Claude Code 實測 viewport 與登入
7. 先跑**一段**（挑目前最穩的那站電子）當煙霧測試，再恢復每日七段
