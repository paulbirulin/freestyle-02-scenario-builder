"""Tool for subagents to present proposals/ideas to the user for approval.

Unlike ask_user_question (which asks for input), this tool:
1. DISPLAYS the agent's generated content to the user
2. Waits for approval/rejection/modification request
3. Returns the user's decision

This forces the agent to pass its proposals through a tool,
ensuring the user always SEES what the agent came up with.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from claude_agent_sdk import tool

# Injected at runtime by create_scenario_tools_server()
_question_callback: Callable[..., Coroutine[Any, Any, str]] | None = None


@tool("present_proposal", "Present your generated content/proposal to the user for review. MUST include the full text of what you propose. Returns user's decision: approve, reject, or modification request.", {
    "title": str,
    "content": str,
})
async def present_proposal(args):
    """Present a proposal to the user and get their decision.
    
    Args:
        title: Short title for the proposal (e.g. "Improvement Plan", "Edit Plan")
        content: FULL text of the proposal — all details, all decisions.
                 This is what the user will read. Must be complete.
        options: Optional list of choices (default: approve/modify/reject)
    """
    title = args.get("title", "Proposal")
    content = args.get("content", "")
    options = args.get("options", [
        "Approve — proceed",
        "Modify — I want to change something", 
        "Reject — start over",
    ])

    if not content or len(content.strip()) < 20:
        return {"content": [{"type": "text", "text": 
            "ERROR: You must provide the FULL content of your proposal. "
            "The 'content' field cannot be empty. Include ALL details, ALL decisions, "
            "ALL generated text that the user needs to review."
        }]}

    print(f"  📋 proposal: {title} ({len(content)} chars)", flush=True)

    # Ensure options is a list
    if not isinstance(options, list):
        options = [str(options)]

    callback = getattr(present_proposal, "_question_callback", None) or _question_callback

    if callback is None:
        return {"content": [{"type": "text", "text": (
            f"[PROPOSAL: {title}]\n\n{content}\n\n"
            f"Options: {options}\n"
            "(No callback configured — cannot reach user interactively)"
        )}]}

    try:
        # Format the question with the full proposal content
        question = f"📋 **{title}**\n\n{content}"
        
        answer = await callback({
            "question": question,
            "context": f"Proposal: {title}",
            "options": options,
            "blocking": True,
        })
        return {"content": [{"type": "text", "text": f"User decision: {answer}"}]}
    except asyncio.TimeoutError:
        return {"content": [{"type": "text", "text": "TIMEOUT: User did not respond. STOP immediately. Do NOT proceed with any changes."}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error getting user decision: {e}"}]}
