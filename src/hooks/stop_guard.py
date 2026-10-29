"""Stop hook: prevent agent from finishing if it has unanswered text questions.

When the agent writes questions as text instead of using ask_user_question tool,
this hook detects the pattern and forces the agent to continue and use the tool.
"""

from __future__ import annotations

from typing import Any

# Shared state — set by orchestrator before each subagent run
_stop_guard_state: dict[str, Any] = {
    "tool_questions_asked": 0,  # count of ask_user_question tool calls
    "agent_name": "",
}


def reset_stop_guard(agent_name: str) -> None:
    """Reset counters before each subagent run."""
    _stop_guard_state["tool_questions_asked"] = 0
    _stop_guard_state["agent_name"] = agent_name


def on_question_tool_called() -> None:
    """Called by question_tool when ask_user_question is invoked."""
    _stop_guard_state["tool_questions_asked"] += 1


async def stop_guard(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """Stop hook: check if the agent's output contains unanswered questions.
    
    If the agent wrote questions as text (contains '?') but never called
    ask_user_question tool, DENY the stop and instruct to use the tool.
    
    The hook fires when the agent is about to finish (Stop event).
    Returning a deny prevents the agent from stopping.
    """
    # Get the agent's last output text
    # input_data for Stop hook contains the stop reason and recent messages
    stop_reason = input_data.get("stop_reason", "")
    
    # Check recent assistant messages for text questions
    messages = input_data.get("messages", [])
    last_text = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                last_text = content
            elif isinstance(content, list):
                last_text = " ".join(
                    b.get("text", "") for b in content 
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            break
    
    if not last_text:
        return {}  # No text to check, allow stop
    
    # Check if last output ends with questions
    tail = last_text[-500:] if len(last_text) > 500 else last_text
    lines = tail.strip().split("\n")
    question_lines = [
        l.strip() for l in lines[-8:] 
        if "?" in l and len(l.strip()) > 15
    ]
    
    if not question_lines:
        return {}  # No text questions, allow stop
    
    # Agent wrote questions as text! Block the stop
    questions_text = "\n".join(f"  - {q[:80]}" for q in question_lines)
    
    return {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "decision": "block",
            "reason": (
                f"You wrote {len(question_lines)} question(s) as text but did NOT use "
                f"the `ask_user_question` tool. Questions will be IGNORED unless you use the tool.\n"
                f"Detected text questions:\n{questions_text}\n\n"
                f"Please use ask_user_question(question='...') for EACH question. "
                f"This is the ONLY way to get user answers."
            ),
        }
    }
