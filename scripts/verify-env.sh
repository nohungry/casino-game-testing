#!/usr/bin/env bash
# verify-env.sh — 換機器後的環境自檢（唯讀，不改任何東西、不印任何憑證值）
#
# 用法：bash scripts/verify-env.sh
# 每項印 [OK] / [WARN] / [FAIL]；FAIL 代表跑不動，WARN 代表要人決定。
# 🔴 這支只檢查「本機環境」。viewport 必須在 Claude Code 裡用瀏覽器實讀（見最後說明）。

cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
fail=0; warn=0

ok()   { printf '  [OK]   %s\n' "$1"; }
warnf(){ printf '  [WARN] %s\n' "$1"; warn=$((warn+1)); }
failf(){ printf '  [FAIL] %s\n' "$1"; fail=$((fail+1)); }
sec()  { printf '\n== %s\n' "$1"; }

sec "1. Node / npx（MCP 都靠 npx 啟動）"
if command -v node >/dev/null 2>&1 && command -v npx >/dev/null 2>&1; then
  ok "node $(node -v) / npx $(npx -v 2>/dev/null)"
  case "$(command -v node)" in
    *"/.nvm/"*) warnf "node 來自 nvm → 絕對不要用 sudo npx（PATH 會被重設）" ;;
  esac
else
  failf "找不到 node 或 npx —— 先裝 Node.js"
fi

sec "2. Chromium 本體"
CHROMIUM_DIRS=$(ls -d "$HOME"/.cache/ms-playwright/chromium-* 2>/dev/null)
if [ -n "$CHROMIUM_DIRS" ]; then
  for d in $CHROMIUM_DIRS; do
    for bin in "$d/chrome-linux64/chrome" "$d/chrome-linux/chrome" \
               "$d/chrome-mac/Chromium.app/Contents/MacOS/Chromium" "$d/chrome-win/chrome.exe"; do
      [ -x "$bin" ] && ok "可執行檔：$bin"
    done
  done
else
  failf "~/.cache/ms-playwright/ 下沒有 chromium-* —— 跑 npx playwright install chromium"
fi

sec "3. .mcp.json（本機檔，gitignored）"
if [ -f .mcp.json ]; then
  ok ".mcp.json 存在"
  # args 是多行陣列，用 python 解析比 grep 可靠
  EXEC_PATH=$(python3 - <<'PY' 2>/dev/null
import json
try:
    cfg = json.load(open('.mcp.json'))
    for srv in cfg.get('mcpServers', {}).values():
        a = srv.get('args', [])
        if '--executable-path' in a:
            print(a[a.index('--executable-path') + 1]); break
except Exception:
    pass
PY
)
  if [ -n "$EXEC_PATH" ]; then
    if [ -x "$EXEC_PATH" ]; then ok "--executable-path 指向的檔案存在：$EXEC_PATH"
    else failf "--executable-path 指到不存在的檔案：$EXEC_PATH（換機器後版本號會變，用上面第 2 項的路徑改掉）"; fi
  else
    warnf ".mcp.json 沒有 --executable-path（macOS/一般 Linux 桌面通常正常；WSL 需要指定）"
  fi
  CFG=$(grep -o 'playwright-mcp[a-zA-Z.-]*\.json' .mcp.json | head -1)
  [ -n "$CFG" ] && ok "--config 指向：$CFG"
  [ "$CFG" = "playwright-mcp.unattended.json" ] && [ ! -f playwright-mcp.unattended.json ] \
    && failf "config 指向 unattended，但該檔不存在（cp playwright-mcp.unattended.json.example 後改尺寸）"
else
  failf ".mcp.json 不存在 —— cp .mcp.json.example .mcp.json 再依 README 填路徑"
fi

sec "4. 視窗尺寸設定的一致性（unattended 模式才需要）"
if [ -f playwright-mcp.unattended.json ]; then
  VP_W=$(grep -o '"width"[[:space:]]*:[[:space:]]*[0-9]*' playwright-mcp.unattended.json | grep -o '[0-9]*' | head -1)
  VP_H=$(grep -o '"height"[[:space:]]*:[[:space:]]*[0-9]*' playwright-mcp.unattended.json | grep -o '[0-9]*' | head -1)
  ok "unattended viewport = ${VP_W}x${VP_H}"
  if [ -f .env ]; then
    WS=$(grep -E '^WINDOW_SIZE=' .env | head -1 | sed 's/^WINDOW_SIZE=//; s/[" ]//g; s/#.*//')
    if [ "$WS" = "${VP_W},${VP_H}" ]; then ok ".env WINDOW_SIZE 與 config 一致（$WS）"
    else failf ".env WINDOW_SIZE=$WS 與 config ${VP_W},${VP_H} 不一致（座標會全失效）"; fi
  fi
  for y in brands/*.yaml; do
    [ -e "$y" ] || continue
    case "$(basename "$y")" in _*) continue ;; esac
    if grep -q "viewport" "$y" 2>/dev/null; then
      YV=$(grep -A2 -i "viewport" "$y" | grep -oE '[0-9]{3,4}[^0-9]+[0-9]{3,4}' | head -1)
      [ -n "$YV" ] && ok "$(basename "$y") 的 viewport 標示：$YV（需與上面相同，否則該 yaml 的座標作廢）"
    fi
  done
else
  warnf "沒有 playwright-mcp.unattended.json（只跑有人在場模式就正常；無人值守必須有）"
fi

sec "5. 本機檔案（都 gitignored，不會跟著 git clone 過來）"
for f in .env .mcp.json playwright-mcp.unattended.json scripts/secret-scan.local-patterns; do
  if [ -f "$f" ]; then ok "$f"
  else
    case "$f" in
      .env) failf "$f 缺（站點/帳密都在這；範本 .env.example）" ;;
      scripts/secret-scan.local-patterns) failf "$f 缺（pre-commit 的敏感詞表，換機器要重建）" ;;
      *) warnf "$f 缺" ;;
    esac
  fi
done
BRANDS=$(ls brands/*.yaml 2>/dev/null | grep -v '/_' | wc -l | tr -d ' ')
[ "$BRANDS" = "0" ] && warnf "brands/ 沒有校準檔（要嘛從舊機器複製，要嘛重新 calibrate）" \
                    || ok "brands/ 有 $BRANDS 份校準檔"

sec "6. .env 必要鍵（只檢查鍵名，不印任何值）"
if [ -f .env ]; then
  MISSING=""
  for k in SITE1_KEY SITE1_HOST SITE1_USER SITE1_PASS SITE1_ADMIN SITE1_ADMIN_USER SITE1_ADMIN_PASS \
           SITE2_KEY SITE2_HOST SITE2_USER SITE2_PASS SITE2_ADMIN SITE2_ADMIN_USER SITE2_ADMIN_PASS \
           SITE3_KEY SITE3_HOST SITE3_USER SITE3_PASS SITE3_ADMIN SITE3_ADMIN_USER SITE3_ADMIN_PASS \
           PLATFORM_API WINDOW_SIZE; do
    grep -qE "^${k}=" .env || MISSING="$MISSING $k"
  done
  [ -z "$MISSING" ] && ok "必要鍵齊全" || failf "缺少鍵：$MISSING"
  EMPTY=$(grep -E '^(SITE[0-9]_(USER|PASS|ADMIN_USER|ADMIN_PASS))=("")?[[:space:]]*(#.*)?$' .env | cut -d= -f1 | tr '\n' ' ')
  [ -n "$EMPTY" ] && warnf "以下鍵存在但沒填值：$EMPTY"
fi

sec "7. Python / uv（報告產生器）"
if [ -x .venv/bin/python ]; then
  ok ".venv 存在（$(.venv/bin/python -V 2>&1)）"
  .venv/bin/python -c "import sys" 2>/dev/null && ok ".venv 可執行"
  if .venv/bin/python .claude/skills/qa-report/gen_qa_report.py --help >/dev/null 2>&1; then
    ok "gen_qa_report.py 可載入"
  else
    warnf "gen_qa_report.py 執行失敗（缺套件？跑 uv sync）"
  fi
else
  if command -v uv >/dev/null 2>&1; then failf ".venv 不存在 —— 跑 uv sync"
  else failf "沒有 uv 也沒有 .venv —— 先裝 uv 再 uv sync"; fi
fi

sec "8. git hook 防線"
HP=$(git config core.hooksPath 2>/dev/null)
if [ "$HP" = "hooks" ]; then ok "core.hooksPath=hooks"
else warnf "core.hooksPath='$HP'（應為 hooks；在 Claude Code 開 session 會自動補設，純 CLI 要自己下 git config core.hooksPath hooks）"; fi
[ -x hooks/pre-commit ] && ok "hooks/pre-commit 可執行" || failf "hooks/pre-commit 不存在或不可執行"
if [ -f scripts/secret-scan.local-patterns ]; then
  bash scripts/secret-scan.sh >/dev/null 2>&1 && ok "secret-scan.sh 跑得起來" || warnf "secret-scan.sh 回非 0（可能是暫存區有東西，非環境問題）"
fi

sec "9. 中文字型（繁中/簡中站；缺會變方塊）"
if command -v fc-list >/dev/null 2>&1; then
  N=$(fc-list :lang=zh 2>/dev/null | wc -l | tr -d ' ')
  [ "$N" -gt 0 ] && ok "系統有 $N 個中文字型" || failf "沒有中文字型 —— Debian/Ubuntu: sudo apt-get install -y fonts-noto-cjk"
else
  warnf "沒有 fc-list（macOS/Windows 內建中文字型，通常免裝）"
fi

sec "10. Claude Code 記憶目錄"
SLUG=$(echo "$ROOT" | sed 's#/#-#g')
MEM="$HOME/.claude/projects/$SLUG/memory"
if [ -d "$MEM" ]; then
  ok "記憶目錄存在：$MEM（$(ls "$MEM"/*.md 2>/dev/null | wc -l | tr -d ' ') 個檔）"
  [ -f "$MEM/MEMORY.md" ] && ok "MEMORY.md 索引存在" || failf "缺 MEMORY.md 索引（記憶不會被載入）"
else
  failf "記憶目錄不存在：$MEM
         🔴 目錄名是【專案絕對路徑把 / 換成 -】。換機器若專案路徑不同，
            必須把舊機器的 memory/ 複製成這個新名字，否則記憶不會載入。"
fi

printf '\n== 結果：FAIL %d 項、WARN %d 項\n' "$fail" "$warn"
cat <<'EOT'

🔴 這支檢查不了、必須在 Claude Code 裡實測的兩件事：
  a) viewport：開瀏覽器到 about:blank，讀 window.innerWidth/innerHeight，
     必須與 .env 的 WINDOW_SIZE 逐字相同。不同就代表所有 brand 座標與
     memory 裡的座標（真人下注區、SPIN、籌碼列 clip…）全部作廢。
  b) 前台登入：三站各登一次，確認登入態（頁面還有「登入」鈕＝沒登入）。
EOT
[ "$fail" -gt 0 ] && exit 1 || exit 0
