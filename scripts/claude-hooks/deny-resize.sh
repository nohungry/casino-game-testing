#!/usr/bin/env bash
# PreToolUse hook：無條件擋 browser resize（鐵則：滿版、不 resize）。
# 由 .claude/settings.json 以 matcher 掛在 mcp__playwright__browser_resize / mcp__chrome-devtools__resize_page。
cat >/dev/null   # 吃掉 stdin 的 hook JSON，避免 broken pipe
cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"鐵則：瀏覽器一律滿版、禁止 resize（座標一致性靠滿版維持）。viewport 只能「讀+比對」，不一致就 fail-fast 回報請使用者調整視窗，不得用 resize 兜。"}}
EOF
exit 0
