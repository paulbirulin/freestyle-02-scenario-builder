"""PreToolUse hook: block raw Write/Edit/Bash to force custom tools.

Subagents must use the controlled write_component tool instead of
built-in file operations, ensuring path sandboxing and audit.
Also tracks WebSearch/WebFetch usage for progress display.
"""

from __future__ import annotations

from typing import Any

# Built-in tools that are blocked — subagents should use our custom MCP tools instead
BLOCKED_TOOLS = {"Write", "Edit", "Bash", "MultiEdit"}

# Built-in tools that get progress tracking
TRACKED_TOOLS = {"WebSearch", "WebFetch", "Read"}


async def enforce_safety(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """PreToolUse hook: deny raw file-writing and shell tools, track web search."""
    tool_name = input_data.get("tool_name", "")

    if tool_name in BLOCKED_TOOLS:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Tool '{tool_name}' is blocked. "
                    f"Use the custom MCP tools instead: "
                    f"write_component (for file writes), "
                    f"read_source_files (for file reads), "
                    f"list_workspace (for directory listing)."
                ),
            }
        }

    # Progress tracking for web search and other built-in tools
    if tool_name in TRACKED_TOOLS:
        tool_input = input_data.get("tool_input", {})
        if tool_name == "WebSearch":
            query = tool_input.get("query", tool_input.get("search_query", "?"))
            print(f"  🌐 web search: {str(query)[:60]}", flush=True)
        elif tool_name == "WebFetch":
            url = tool_input.get("url", tool_input.get("URL", "?"))
            print(f"  🌐 web fetch: {str(url)[:60]}", flush=True)
        elif tool_name == "Read":
            path = tool_input.get("file_path", tool_input.get("path", "?"))
            print(f"  📖 read (built-in): {str(path)[-40:]}", flush=True)

    return {}

