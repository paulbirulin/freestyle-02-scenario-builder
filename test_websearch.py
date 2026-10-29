"""Test snippet: verify WebSearch works via Claude Agent SDK query().

Run:  python test_websearch.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Load .env from this directory
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock


async def main():
    print("=" * 60)
    print("Testing WebSearch via Claude Agent SDK")
    print("=" * 60)

    options = ClaudeAgentOptions(
        system_prompt="You are a helpful assistant. Answer briefly in 2-3 sentences.",
        allowed_tools=["WebSearch", "WebFetch"],
        disallowed_tools=["Write", "Edit", "Bash", "MultiEdit", "Read"],
        permission_mode="acceptEdits",
        max_turns=5,
    )

    prompt = "What is the current weather in Tel Aviv today? Use WebSearch to find out."

    print(f"\nPrompt: {prompt}")
    print("-" * 60)

    msg_count = 0
    async for msg in query(prompt=prompt, options=options):
        msg_count += 1
        msg_type = type(msg).__name__
        print(f"\n[Message #{msg_count}] Type: {msg_type}")

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(f"  Text: {block.text[:500]}")
                else:
                    block_type = type(block).__name__
                    block_str = str(block)[:200]
                    print(f"  {block_type}: {block_str}")
        else:
            # ResultMessage, SystemMessage, etc.
            attrs = {k: str(v)[:100] for k, v in vars(msg).items() if not k.startswith("_")}
            print(f"  Attrs: {attrs}")

    print("\n" + "=" * 60)
    print(f"Done. Total messages: {msg_count}")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
