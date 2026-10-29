"""Tool for subagents to ask clarifying questions to the user via the web UI.

The question_callback is injected by the orchestrator/tools __init__ and is
an async function that:
  1. Sends an SSE event to the frontend
  2. Waits for the user's answer
  3. Returns the answer string
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from claude_agent_sdk import tool

# Injected at runtime by create_scenario_tools_server()
_question_callback: Callable[..., Coroutine[Any, Any, str]] | None = None


@tool("ask_user_question", "Ask the user a clarifying question and wait for their answer. Only 'question' is required. Optionally provide 'context' (string), 'options' (list of strings, max 10), and 'blocking' (bool, default true).", {
    "question": str,
})
async def ask_user_question(args):
    """Ask the user a question through the web UI.

    Returns the user's answer as a tool result so the subagent can continue.
    """
    question = args.get("question", args.get("text", str(args)))
    print(f"  ❓ question: {question[:60]}", flush=True)
    context = args.get("context", "")
    options = args.get("options", [])
    blocking = args.get("blocking", True)
    # Ensure options is a list
    if not isinstance(options, list):
        options = [str(options)]

    callback = getattr(ask_user_question, "_question_callback", None) or _question_callback

    if callback is None:
        return {"content": [{"type": "text", "text": (
            f"[QUESTION FOR USER]: {question}\n"
            f"Context: {context}\n"
            f"Options: {options}\n"
            "(No callback configured — cannot reach user interactively)"
        )}]}

    try:
        answer = await callback({
            "question": question,
            "context": context,
            "options": options,
            "blocking": blocking,
        })
        return {"content": [{"type": "text", "text": f"User answered: {answer}"}]}
    except asyncio.TimeoutError:
        return {"content": [{"type": "text", "text": "User did not respond in time. Proceeding with best judgment."}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error getting user answer: {e}"}]}
