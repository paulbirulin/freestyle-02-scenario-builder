"""Test: verify PreToolUse hook fires for MCP tools."""
import asyncio
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
os.environ.pop("ANTHROPIC_MODEL", None)

from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher
from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage
from src.tools import create_scenario_tools_server

# Track if hook fires
hook_calls = []

async def test_hook(input_data, tool_use_id, context):
    tool_name = input_data.get("tool_name", "")
    short = tool_name.split("__")[-1] if "__" in tool_name else tool_name
    print(f"  🪝 HOOK FIRED: {short} (full: {tool_name})")
    hook_calls.append(short)
    return {}  # allow

async def test():
    tools = create_scenario_tools_server()
    
    options = ClaudeAgentOptions(
        system_prompt="You are a test agent. Use list_workspace tool to see files, then stop.",
        cwd=str(Path(__file__).parent.resolve()),
        allowed_tools=[
            "mcp__scenario-builder-tools__list_workspace",
            "Read",
        ],
        disallowed_tools=["Write", "Edit", "Bash", "MultiEdit"],
        mcp_servers={"scenario-builder-tools": tools},
        permission_mode="acceptEdits",
        hooks={
            "PreToolUse": [
                HookMatcher(matcher="*", hooks=[test_hook]),
            ],
        },
        max_turns=3,
    )
    
    print("Starting test...")
    async for msg in query(prompt="Use list_workspace to see files in current directory", options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(f"  AGENT: {block.text[:100]}")
    
    print(f"\n{'='*50}")
    print(f"Hook fired {len(hook_calls)} times: {hook_calls}")
    if hook_calls:
        print("✅ Hooks WORK for MCP tools")
    else:
        print("❌ Hooks DO NOT fire for MCP tools — this is the bug!")

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
asyncio.run(test())
