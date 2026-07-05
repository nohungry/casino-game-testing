#!/usr/bin/env python3
"""PreToolUse hook：截圖檔名必須帶目錄路徑，擋「裸檔名」散落。

裸檔名（如 x.png）會被 MCP server 寫到它的 cwd＝repo 根，到處散落
（CLAUDE.md「測試產物一律歸位 report_dir/」鐵則的機器強制版）。

規則：
- mcp__playwright__browser_take_screenshot：filename 缺省或不含路徑分隔 → deny。
- mcp__chrome-devtools__take_screenshot：filePath 缺省＝回傳 inline 影像（不落地），放行；
  有給 filePath 但是裸檔名 → deny。
只驗「有沒有帶目錄」，不強制在 report_dir 底下（calib_dir / 暫存目錄也是合法去處）。
"""
import json
import sys

DENY_REASON = (
    "鐵則：截圖檔名一律給完整路徑，例如 report_dir/screenshots/<名稱>.png"
    "（對帳頁截圖給 report_dir/backoffice/）。裸檔名會落到 MCP cwd＝repo 根、到處散落。"
    "無 report_dir 的一次性探測請截到暫存目錄或 calib_dir。"
)


def deny() -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # 讀不懂 hook 輸入就放行，寧漏勿擋壞流程

    tool = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("filename") or tool_input.get("filePath") or ""

    if path:
        if "/" not in path and "\\" not in path:
            deny()  # 裸檔名
        sys.exit(0)

    # 未給檔名：playwright 會自動落地（散落風險）→ deny；
    # chrome-devtools 未給 filePath 是 inline 影像（讀餘額等合法用途）→ 放行。
    if "playwright" in tool:
        deny()
    sys.exit(0)


if __name__ == "__main__":
    main()
