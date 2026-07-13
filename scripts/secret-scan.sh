#!/usr/bin/env bash
# secret-scan.sh — 進版前敏感內容/檔案掃描。
# 掃「已 staged 的檔」，命中即 exit 1 擋下 commit（由 hooks/pre-commit 呼叫）。
#   scripts/secret-scan.sh            預設：掃暫存區 (git diff --cached)
#   scripts/secret-scan.sh --all      全庫體檢：掃所有追蹤檔
# 抓：本機路徑(/home、/mnt/c/Users、C:\Users)、密碼/token/金鑰關鍵字、私鑰、
#     JWT/雲端金鑰格式、URL 內含帳密，以及誤加的敏感檔類型(截圖/reports/.mcp.json/brands 參數…)。
# 站點/帳號硬編這種「值本身合法、只是不該出現在通用工具」的情況 pattern 難通用偵測，
# 靠 /git-commit skill 提示 + 人工 review 補；本腳本專抓可穩定 pattern 化的類型。
set -u

mode="${1:-staged}"
self="scripts/secret-scan.sh"
fail=0

# 本機詞表變更 → 自動升級為全庫體檢（新詞只有掃過存量才算真正生效）
# hash 記在 .git/ 內（不入版控），全庫掃通過後才更新。
local_patterns="scripts/secret-scan.local-patterns"
patterns_marker="$(git rev-parse --git-dir 2>/dev/null)/secret-scan-patterns.sha"
patterns_hash=""
if [ -f "$local_patterns" ]; then
  patterns_hash="$(sha256sum "$local_patterns" 2>/dev/null | awk '{print $1}')"
  if [ "$mode" != "--all" ] && [ "$patterns_hash" != "$(cat "$patterns_marker" 2>/dev/null)" ]; then
    echo "secret-scan: 偵測到本機詞表更新 → 自動升級為全庫體檢（--all）"
    mode="--all"
  fi
fi

# 不用 mapfile：macOS 系統 bash 3.2 沒有，跨平台用 while read 收集
files=()
if [ "$mode" = "--all" ]; then
  # --all 讀「工作目錄」內容做全庫體檢（staged 模式讀 index，兩者語義不同：
  # 體檢看的是現況檔案，未 add 的改動也會掃到）
  while IFS= read -r _f; do files+=("$_f"); done < <(git ls-files)
  getcontent() { cat "$1" 2>/dev/null; }
else
  while IFS= read -r _f; do files+=("$_f"); done < <(git diff --cached --name-only --diff-filter=ACM)
  getcontent() { git show ":$1" 2>/dev/null; }
fi

if [ "${#files[@]}" -eq 0 ]; then
  echo "secret-scan: 無待掃檔案。"
  exit 0
fi

report() { printf '  ✗ [%s] %s\n' "$1" "$2"; fail=1; }

for f in "${files[@]}"; do
  [ -z "$f" ] && continue

  # (1) 敏感「檔案類型/路徑」被納入版本控制
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.bmp)  report "影像/截圖" "$f（截圖不入 repo）" ;;
    reports/*)                              report "報告目錄"  "$f（reports/ 不入 repo）" ;;
    .mcp.json)                              report "MCP設定"   "$f（含本機路徑；範本用 .mcp.json.example）" ;;
    *settings.local.json)                   report "本機設定"  "$f" ;;
    *.env|*.pem|*.key|*.p12|*id_rsa*)       report "憑證/金鑰檔" "$f" ;;
    brands/_schema.yaml|brands/_template.yaml) : ;;
    brands/*.yaml)                          report "品牌參數"  "$f（brands/<brand>.yaml 不入 repo）" ;;
    .venv/*|*/__pycache__/*|*.pyc)          report "Python工件" "$f" ;;
  esac

  # (2) 內容 pattern（略過掃描器自身與 hook，其內含 pattern 定義會自我誤判）
  case "$f" in "$self"|hooks/pre-commit) continue ;; esac

  content="$(getcontent "$f")"
  printf '%s' "$content" | grep -Iq . 2>/dev/null || continue   # 二進位跳過

  hits="$(printf '%s\n' "$content" | grep -nE \
      -e '/home/[A-Za-z0-9_][A-Za-z0-9_.-]*/' \
      -e '/Users/[A-Za-z0-9_][A-Za-z0-9_.-]*/' \
      -e '/mnt/c/Users/[^/[:space:]]+' \
      -e 'C:\\Users\\[^\\[:space:]]+' \
      -e '(password|passwd|secret|api[_-]?key|apikey|access[_-]?key|auth[_-]?token|client_secret)[[:space:]]*[:=]' \
      -e 'BEGIN [A-Z ]*PRIVATE KEY' \
      -e 'sk-[A-Za-z0-9]{20,}' \
      -e 'ghp_[A-Za-z0-9]{20,}' \
      -e 'AKIA[0-9A-Z]{16}' \
      -e 'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}' \
      -e '://[^/[:space:]]+:[^/@[:space:]]+@' \
      2>/dev/null || true)"
  if [ -n "$hits" ]; then
    while IFS= read -r line; do report "內容" "$f:$line"; done <<< "$hits"
  fi

  # (3) 本機自訂敏感詞（站點/品牌/帳號等「值合法但不得入 repo」的詞）
  #     詞表放 scripts/secret-scan.local-patterns（gitignored，每行一個 ERE pattern，# 開頭為註解）
  #     ——詞表本身含敏感詞，絕不 commit；repo 只帶這個讀取機制。詞表 hash 見開頭：變更會自動觸發全庫體檢。
  if [ -f "$local_patterns" ]; then
    while IFS= read -r pat; do
      case "$pat" in ''|'#'*) continue ;; esac
      lhits="$(printf '%s\n' "$content" | grep -inE -e "$pat" 2>/dev/null || true)"
      if [ -n "$lhits" ]; then
        while IFS= read -r line; do report "本機敏感詞" "$f:$line"; done <<< "$lhits"
      fi
    done < "$local_patterns"
  fi
done

echo
if [ "$fail" -ne 0 ]; then
  echo "❌ secret-scan 擋下 commit：上列疑似敏感內容/檔案不應進版。"
  echo "   修正後重 commit；確認為誤判可 'git commit --no-verify' 略過（不建議）。"
  exit 1
fi
echo "✅ secret-scan 通過：暫存區無明顯敏感內容。"
# 掃描通過才記下詞表 hash（下次詞表沒變就不必重複全庫體檢）
if [ -n "$patterns_hash" ] && [ "$mode" = "--all" ]; then
  printf '%s' "$patterns_hash" > "$patterns_marker" 2>/dev/null || true
fi
exit 0
