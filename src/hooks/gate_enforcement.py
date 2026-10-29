"""PreToolUse hook: block tools if prerequisite gate has not been passed.

Also enforces QA write-lock: during QAValidator, write tools are blocked
until the user has actually responded to a present_proposal/ask_user_question.

The unlock happens in orchestrator's _question_callback (not here),
so timeout = writes stay locked = agent can't fix anything.

The session_state dict is injected from the orchestrator before each run.
"""

from __future__ import annotations

from typing import Any

# Shared mutable state — set by orchestrator before each subagent invocation
session_state: dict[str, Any] = {
    "gates_passed": set(),
    "qa_writes_locked": False,  # When True, write tools blocked until user responds
}

# Map: tool short name -> minimum gate that must be passed before using this tool
# Pipeline: Gate 1 (analysis) → Gate 2 (edit plan) → ContentWriter → QAValidator → Gate 3 (review) → Gate 4 (tests)
GATE_REQUIREMENTS: dict[str, int] = {
    "write_component": 2,      # ContentWriter/QAValidator need gate 2 (edit plan approved)
    "find_replace_in_file": 2,  # Same — editing requires gate 2
    "assemble_prompt": 2,       # Assembly is part of editing
    "run_batch_test": 4,        # Tests need gate 4
}

# Tools that modify files — blocked during QA until user responds
QA_WRITE_TOOLS = {"write_component", "find_replace_in_file"}


async def enforce_gates(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """PreToolUse hook: deny tool calls if the required gate is not yet passed."""
    import logging
    _log = logging.getLogger("gate_enforcement")

    tool_name = input_data.get("tool_name", "")

    # Extract short name from MCP-qualified name
    # e.g. "mcp__scenario-builder-tools__write_component" -> "write_component"
    short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name

    qa_locked = session_state.get("qa_writes_locked", False)
    _log.info(f"HOOK PreToolUse: tool={short_name!r} (full={tool_name!r}), qa_locked={qa_locked}")

    # --- QA write lock ---
    # During QAValidator: write tools blocked until user responds to proposal.
    # Unlock happens in orchestrator's _question_callback, NOT here.
    # This means: timeout = lock stays = agent can't write. Programmatic enforcement.
    if qa_locked:
        if short_name in QA_WRITE_TOOLS:
            _log.warning(f"HOOK DENIED: {short_name} blocked by QA write lock")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "QA write lock active. You must present your findings "
                        "to the user via present_proposal and WAIT for their response "
                        "BEFORE making any changes."
                    ),
                }
            }

    # --- Gate requirements ---
    required_gate = GATE_REQUIREMENTS.get(short_name)
    if required_gate is not None:
        passed = session_state.get("gates_passed", set())
        if required_gate not in passed:
            _log.warning(f"HOOK DENIED: {short_name} blocked — gate {required_gate} not passed (have: {sorted(passed)})")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Gate {required_gate} not yet passed. "
                        f"Current gates passed: {sorted(passed)}. "
                        f"Complete the previous steps and get user approval first."
                    ),
                }
            }

    return {}


def update_gates_passed(gates: set[int]) -> None:
    """Called by orchestrator when gates are approved."""
    session_state["gates_passed"] = gates


def set_qa_write_lock(locked: bool) -> None:
    """Called by orchestrator before/after QAValidator run."""
    import logging
    logging.getLogger("gate_enforcement").info(f"SET QA WRITE LOCK: {locked}")
    session_state["qa_writes_locked"] = locked

