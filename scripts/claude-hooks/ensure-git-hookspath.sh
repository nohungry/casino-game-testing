#!/usr/bin/env bash
# SessionStart hook：確保本 clone 已啟用 repo 內建 git hooks（pre-commit secret-scan）。
# core.hooksPath 是本機 git 設定、不隨 clone 帶入；沒設的話整條進版防線都不生效。
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
[ -f hooks/pre-commit ] || exit 0

current="$(git config core.hooksPath 2>/dev/null || true)"
if [ "$current" != "hooks" ]; then
  git config core.hooksPath hooks
  echo "secret-scan 防線：已自動設定 git core.hooksPath=hooks（每次 commit 前會跑 scripts/secret-scan.sh）。"
fi
exit 0
