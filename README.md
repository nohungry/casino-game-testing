# casino-game-testing

面向第三方電子遊戲平台的**批次測試自動化**。把先前手做的測試流程抽象成可重用的 Skill + Subagent，整組 QA（Win/Mac/Linux/WSL）共用同一份 repo。

兩個核心堅持：

- **品牌無預設** — repo 不存任何品牌參數；每個品牌的 SPIN 座標等由 AI 在 `calibrate` 模式自己探出，寫到本機 `brands/<brand>.yaml`（gitignored）。
- **站點無預設** — repo 不存帳號/網址；**使用者自己開瀏覽器、登入、建議停在該品牌遊戲大廳**（另開好後台投注報表分頁），Skill 從當前頁接手。**Skill 不跨站、不登入**；品牌內選款/進入/退出遊戲由 AI 操作，同站停錯品牌 AI 會宣告後自行切換，做「批次驅動 + 餘額驗證 + 報告產出」。

---

## QA 上手 5 步

1. `git clone` 此專案，然後 `cp .mcp.json.example .mcp.json`（`.mcp.json` 是本機檔、不入 repo）。
2. 在專案資料夾啟動 Claude Code → MCP 自動裝/跑 → **Chromium 視窗自動跳出**。
   - ⚠️ **不同 OS 可能要改 `.mcp.json`**，見下方「跨平台注意」。
3. **你自己**：把 Chromium 視窗**拉到滿版**（座標靠滿版維持一致，過程中別改視窗大小），登入站點、進到對應品牌的遊戲列表頁（大廳）；**建議同時開好後台投注報表分頁**（run 前會檢查，缺了會提醒）。之後選款/進遊戲都由 AI 操作，你不用自己開遊戲；同站內停錯品牌也沒關係，AI 會宣告後自行切到目標品牌（跨站/登入仍是你的責任）。
4. 在 Claude Code 輸入：
   - 首次跑某品牌 → `/test-game-brand calibrate <brand>`（先校準參數；AI 自挑大廳第一款當 sample）
   - 已有參數 → `/test-game-brand run <brand>`（批次跑）
5. 跑完，後台 bet-report 篩好條件 → `/test-game-brand post <brand>`（對帳；含詳情彈窗遊戲名正面確認）。

---

## ⚠️ 跨平台安裝（不同 OS 的 QA 必讀）

repo 只 track 一份通用範本 `.mcp.json.example`（不寫死任何路徑）。實際用的 `.mcp.json` 是**本機檔、已 gitignore**，所以每個人的本機路徑（含使用者名稱）都不會被 commit。clone 後：

```bash
cp .mcp.json.example .mcp.json   # 之後只改這份本機檔
```

### 前置：Node.js（必裝）
整套 MCP 是用 `npx` 啟動的（見 `.mcp.json`），所以**一定要有 Node.js**。沒有就先裝（建議用 nvm，或各 OS 官方安裝包）。裝完確認：
```bash
node -v && npx -v      # 兩個都印得出版本才算 OK
```

> 🔴 **千萬別 `sudo npx ...`**：若 Node 是用 **nvm** 裝的，它在你家目錄、只在「你自己的 shell」進 PATH。一加 `sudo`，PATH 被重設、nvm 不見 → 報 `npx: command not found`。
> 正解：**npx 用你自己的身分跑**，需要動 apt 時讓工具**自己跳 sudo 密碼**。真的非 sudo 跑 npx 不可，用 `sudo env "PATH=$PATH" npx ...` 把 PATH 帶進去。

### 裝 Chromium（瀏覽器本體，免 sudo）
```bash
npx playwright install chromium      # 下載到 ~/.cache/ms-playwright/（不要加 sudo）
```

### 裝系統依賴（只有 Linux / WSL 需要）
macOS、原生 Windows **跳過這步**。Linux/WSL 上 Chromium 缺 shared library 會「視窗跳不出來」：

| 發行版 | 指令 |
|--------|------|
| **Debian / Ubuntu / WSL** | `npx playwright install --with-deps chromium`（不加 sudo 前綴，工具會自己跳 sudo 裝 apt）<br>或手動：`sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgbm1 libasound2 libxkbcommon0 libatk-bridge2.0-0 libatspi2.0-0 libcups2 libnss3 libnspr4` |
| **Fedora / RHEL** | `--with-deps` 不支援；用 `sudo dnf install` 對應 lib（`nss atk at-spi2-atk cups-libs libdrm libxkbcommon mesa-libgbm pango alsa-lib`） |
| **Arch** | `sudo pacman -S nss atk at-spi2-atk libcups libdrm libxkbcommon mesa pango alsa-lib` |

> 套件**版本號不重要**，有裝就好；名稱會隨發行版不同。

### 中文站點字型（繁中/簡中站必裝，否則文字變方塊 □）
| 發行版 | 指令 |
|--------|------|
| **Debian / Ubuntu / WSL** | `sudo apt-get install -y fonts-noto-cjk fonts-noto-cjk-extra && fc-cache -f` |
| **Fedora** | `sudo dnf install google-noto-sans-cjk-fonts google-noto-serif-cjk-fonts` |
| **Arch** | `sudo pacman -S noto-fonts-cjk` |
| **macOS / Windows** | 系統內建中文字型，通常免裝 |

### WSL 補一步：在 `.mcp.json` 指定 Chromium 路徑
WSL 上 playwright MCP 預設會去找系統 chrome（沒裝），要明確指向剛剛 `npx playwright install` 下載的 binary：

```jsonc
"args": ["-y", "@playwright/mcp@latest", "--browser", "chromium",
         "--config", "./playwright-mcp.config.json",
         "--executable-path", "<你的本機 chromium 路徑>"]
//                              ↑ 範例：$HOME/.cache/ms-playwright/chromium-<版本>/chrome-linux64/chrome
//                                版本號用  ls ~/.cache/ms-playwright/  查自己機器的
```
macOS / Windows / 一般 Linux 桌面通常**不用加** `--executable-path`，範本原樣即可。

> 改完 `.mcp.json` 要**重啟 Claude Code** 才生效。`.mcp.json` 已 gitignore，是各人本機檔，改它不會影響別人。

### Python 環境（uv）— 報告產生器用
QA 報告產生器（`.claude/skills/qa-report/gen_qa_report.py`、`gen_detail_only.py`）跑在**專案獨立的 `.venv`（Python 3.13）**，用 [uv](https://docs.astral.sh/uv/) 管理（新世代工具，pip/venv/pyenv 合一、免 sudo 就能裝任意 Python 版本）。

```bash
# 1) 裝 uv（user 層、免 sudo；裝到 ~/.local/bin）
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"          # 這行可加進 ~/.bashrc

# 2) clone 後建環境（讀 .python-version + pyproject.toml，需要時自動下載 Python 3.13）
uv sync

# 3) 跑產生器
uv run .claude/skills/qa-report/gen_qa_report.py <report_dir> --input <…>/qa-report-input.json
uv run .claude/skills/qa-report/gen_detail_only.py <report_dir> --names <對照>.json --out <out>.html
```

- **版本管理**：`pyproject.toml`（`requires-python`）、`uv.lock`、`.python-version` 都已 commit，團隊環境一致可重現；`.venv/` 不入 repo。
- **目前零第三方依賴**（純標準庫）；未來要寫 `.xlsx` / 接 Google Sheets API 時 `uv add openpyxl` / `uv add gspread` 即可。
- 無 uv 時可退回 `python3 <script>`（腳本純標準庫，任何 Python 3 皆可跑）。

### 安全防線：進版前敏感掃描
避免把本機路徑、密碼/token/金鑰、或誤加的敏感檔（截圖 / `reports/` / `.mcp.json` / `brands/<brand>.yaml`）commit 進 repo。

```bash
git config core.hooksPath hooks        # 啟用 pre-commit 掃描（在 Claude Code 內開過 session 會自動設好）
bash scripts/secret-scan.sh --all      # 想手動全庫體檢時
```

- 啟用後每次 `git commit` 會自動跑 `scripts/secret-scan.sh` 掃暫存區，命中就擋下。
- 在 Claude Code 內開 session 時，SessionStart hook（`scripts/claude-hooks/ensure-git-hookspath.sh`）會自動檢查並補設 `core.hooksPath`，新 clone 忘了設也不會漏防。
- `/git-commit` skill 也會在提交前先掃一次。
- 確認為誤判可 `git commit --no-verify` 略過（請先人工確認）。
- ⚠️ 掃描器抓不到「站點/帳號/品牌被硬編進通用程式或文件」這種（值合法、但不該入 repo）——這類靠 code review 與 CLAUDE.md 核心不變量把關。

### 鐵則機器強制（Claude Code hooks，隨 repo 生效）
`.claude/settings.json`（團隊共用、已 commit）掛了三個 hook，把 CLAUDE.md 幾條鐵則從「自律」升級成「機器擋下」：

| Hook | 觸發 | 行為 |
|------|------|------|
| deny-resize | `browser_resize` / `resize_page` | 一律 deny（鐵則：滿版不 resize） |
| check-screenshot-path | `browser_take_screenshot` 等截圖工具 | 檔名缺省或裸檔名（不含路徑）→ deny，要求給 `report_dir/screenshots/…` 完整路徑；chrome-devtools 不落地的 inline 截圖放行 |
| ensure-git-hookspath | SessionStart | 自動補設 `core.hooksPath=hooks`（見上節） |

腳本在 `scripts/claude-hooks/`，用 bash + python3 標準庫。已在 WSL(Linux) 驗證；**Windows 原生（非 WSL）環境未驗證**，若 hook 報錯請回報。

#### macOS 試跑檢查表（未在 macOS 實測，請照此驗一輪）
1. `bash scripts/secret-scan.sh --all` — 系統 bash 3.2 能跑完（已移除 `mapfile` 依賴，但未實機驗證）。
2. 建一個含 `/Users/<你的帳號>/` 路徑的暫存檔 `git add` 後 `bash scripts/secret-scan.sh` — 應被擋下（macOS home 路徑 pattern）。
3. 在 Claude Code 內叫一次裸檔名截圖 — 應被 deny 並收到歸位提示。

---

## Skill `/test-game-brand` 三個 mode

唯一必填參數是**品牌名**（站點隱含於你準備好的當前頁面）。

| Mode | 你要先停在哪 | Skill 做什麼 |
|------|-------------|-------------|
| `calibrate <brand>` | 停在該品牌遊戲大廳 | AI 自挑大廳第一款進入當 sample → 探出 SPIN 座標 / 介紹頁 / bet / OOPS pattern → 寫 `brands/<brand>.yaml` |
| `run <brand>` | 停在該品牌的遊戲列表頁 | 讀當前 URL（記為 lobby）→ 抓遊戲清單 → 切批 → 跑 → 驗餘額 → 出報告 |
| `post <brand>` | 開後台 bet-report、篩好條件 | 讀當前頁 → 對帳 `games.jsonl` → 寫 `reconcile.md` |

擴充 flag：`--range a-b`、`--resume-from g042`、`--dry-run`。

---

## 流程總覽（Workflow）

整條測試流水線：**你手動準備頁面 → calibrate（首次）→ run → qa-report →（可選）post 對帳**。Skill 只從你開好的當前頁接手。

```mermaid
flowchart TD
    U["👤 你：開瀏覽器 · 登入 · 視窗滿版 · 停在品牌大廳<br/>(+後台投注報表分頁；Skill 不跨站、不登入)"] --> Q{"首次測此品牌?"}
    Q -- "是" --> CAL["/test-game-brand calibrate &lt;brand&gt;<br/>AI 自挑大廳第一款當 sample 探 SPIN座標 · 餘額讀法 · intro · 退出"]
    CAL --> CY[("brands/&lt;brand&gt;.yaml<br/>+ calib-meta.json 校準耗時")]
    Q -- "否（已有參數）" --> RUN["/test-game-brand run &lt;brand&gt;<br/>讀+比對 viewport · 抓清單 · 分批 · 逐款驗餘額"]
    CY --> RUN
    RUN --> RY[("games.jsonl · games.csv<br/>run-summary.md · run-meta.json")]
    RY --> QA["/qa-report<br/>gen_qa_report.py 確定性產單檔 HTML"]
    QA --> QY[("qa-report.html<br/>裁決 · 指標 · 時間投入 · 餘額鏈 · 逐款明細")]
    RY --> POST["👤 開後台 bet-report 篩好條件<br/>→ /test-game-brand post &lt;brand&gt;"]
    POST --> PY[("reconcile.md<br/>對帳 missing / extra")]
```

> 🔴 **貫穿全流程的鐵則**：① 驗到餘額變化才能 PASS（`delta==0` 不准）② 視窗滿版、全程不 `resize`，viewport 不符就 fail-fast ③ 卡住/60s 無回應就開新分頁從 lobby 重啟 ④ 品牌無預設、站點無預設，Skill 不導航不登入。詳見下方〈鐵則〉與 [`docs/architecture-plan.md`](docs/architecture-plan.md) 的詳細流程圖。

---

## 鐵則

**單一真源見 [`CLAUDE.md`](CLAUDE.md)「核心不變量」**（驗餘額才能 PASS／滿版不 resize／卡住換新分頁／品牌站點無預設…）。其中「不 resize」與「截圖歸位」已由 `.claude/settings.json` PreToolUse hook 機器強制。

---

## 現況

全 mode（calibrate / run / post + qa-report）已上線，多品牌實測驗收通過（品牌H／品牌B／品牌G／品牌R，歷史期望值見 [`docs/acceptance-fixtures.md`](docs/acceptance-fixtures.md)）；`browser_resize`／裸檔名截圖已由 hooks 硬防線擋下。架構詳見 [`docs/architecture-plan.md`](docs/architecture-plan.md)。
