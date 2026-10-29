"""Quick test: verify Claude Agent SDK connects via Bedrock with bearer token."""
import asyncio
import os
import traceback
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

# Remove ANTHROPIC_MODEL if present — let SDK auto-select
model = os.environ.pop("ANTHROPIC_MODEL", None)
if model:
    print(f"WARNING: Removed ANTHROPIC_MODEL={model}")

print(f"BEDROCK: {os.environ.get('CLAUDE_CODE_USE_BEDROCK')}")
print(f"REGION: {os.environ.get('AWS_REGION')}")
token = os.environ.get('AWS_BEARER_TOKEN_BEDROCK', 'NOT SET')
print(f"BEARER: {token[:20]}..." if len(token) > 20 else f"BEARER: {token}")

from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher
from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage, SystemMessage

options = ClaudeAgentOptions(
    system_prompt="You are a helpful assistant.",
    cwd=str(Path(__file__).parent.resolve()),
    allowed_tools=["Read"],
    disallowed_tools=["Write", "Edit", "Bash", "MultiEdit"],
    permission_mode="acceptEdits",
    max_turns=1,
)

async def test():
    try:
        async for msg in query(prompt="Say hello in one word", options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"ASSISTANT: {block.text}")
            elif isinstance(msg, ResultMessage):
                print(f"RESULT: subtype={msg.subtype}, is_error={msg.is_error}, model used")
            elif isinstance(msg, SystemMessage):
                print(f"SYSTEM: {msg.subtype}")
        print("\n✅ SDK works!")
    except Exception as e:
        print(f"\n❌ ERROR TYPE: {type(e).__name__}")
        print(f"❌ ERROR MSG: {e}")
        traceback.print_exc()

asyncio.run(test())
