"""Subagent definitions: load system prompts from skills/*.md files.

Each subagent is defined by:
- A .md SKILL file in skills/ (editable without touching Python)
- Reference mappings
- Tool permissions
"""

from __future__ import annotations

from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = SKILL_ROOT / "skills"


def _load_skill(filename: str) -> str:
    """Load a skill .md file, stripping the YAML frontmatter."""
    path = SKILLS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")
    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter (---...---)
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip("\n")
    return text


# Subagent configs — system_prompt loaded from .md at import time
SOURCE_ANALYST = {
    "name": "SourceAnalyst",
    "steps": [1, 2],
    "skill_file": "source-analyst.md",
    "references": [],
    "allowed_tools": [
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__ask_user_question",
        "mcp__scenario-builder-tools__present_proposal",
        "Read",
        "WebSearch",
        "WebFetch",
    ],
}

STRUCTURE_PLANNER = {
    "name": "StructurePlanner",
    "steps": [3, 4],
    "skill_file": "structure-planner.md",
    "references": [
        "freestyle-02-file-responsibilities.md",
        "communication-gates.md",
    ],
    "allowed_tools": [
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__read_reference",
        "mcp__scenario-builder-tools__ask_user_question",
        "mcp__scenario-builder-tools__present_proposal",
        "Read",
        "WebSearch",
        "WebFetch",
    ],
}

CONTENT_WRITER = {
    "name": "ContentWriter",
    "steps": [5, 6, 7],
    "skill_file": "content-writer.md",
    "references": [
        "immersive-prompt-writing.md",
        "welcome-message.md",
    ],
    "allowed_tools": [
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__write_component",
        "mcp__scenario-builder-tools__find_replace_in_file",
        "mcp__scenario-builder-tools__read_reference",
        "mcp__scenario-builder-tools__assemble_prompt",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__ask_user_question",
        "Read",
    ],
}

QA_VALIDATOR = {
    "name": "QAValidator",
    "steps": [8],
    "skill_file": "qa-validator.md",
    "references": [
        "final-qa-checklist.md",
        "known-issues.md",
    ],
    "allowed_tools": [
        # READ-ONLY: discovery phase — no write tools!
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__validate_scenario",
        "mcp__scenario-builder-tools__assemble_prompt",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__read_reference",
        "mcp__scenario-builder-tools__ask_user_question",
        "mcp__scenario-builder-tools__present_proposal",
        "Read",
    ],
}

# Same agent but WITH write tools — used after user approves QA findings
QA_VALIDATOR_FIX = {
    "name": "QAValidator",
    "steps": [8],
    "skill_file": "qa-validator.md",
    "references": [
        "final-qa-checklist.md",
        "known-issues.md",
    ],
    "allowed_tools": [
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__validate_scenario",
        "mcp__scenario-builder-tools__find_replace_in_file",
        "mcp__scenario-builder-tools__write_component",
        "mcp__scenario-builder-tools__assemble_prompt",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__read_reference",
        "mcp__scenario-builder-tools__ask_user_question",
        "Read",
    ],
}

TEST_RUNNER = {
    "name": "TestRunner",
    "steps": [9, 10],
    "skill_file": "test-runner.md",
    "references": [
        "testing-and-iteration.md",
    ],
    "allowed_tools": [
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__read_reference",
        "mcp__scenario-builder-tools__ask_user_question",
        "Read",
    ],
}

CONSISTENCY_CHECKER = {
    "name": "ConsistencyChecker",
    "steps": [],
    "skill_file": "consistency-checker.md",
    "references": [
        "final-qa-checklist.md",
        "freestyle-02-file-responsibilities.md",
        "known-issues.md",
    ],
    "allowed_tools": [
        "mcp__scenario-builder-tools__read_source_files",
        "mcp__scenario-builder-tools__list_workspace",
        "mcp__scenario-builder-tools__read_reference",
        "mcp__scenario-builder-tools__ask_user_question",
        "Read",
    ],
}

ALL_SUBAGENTS = {
    "SourceAnalyst": SOURCE_ANALYST,
    "StructurePlanner": STRUCTURE_PLANNER,
    "ContentWriter": CONTENT_WRITER,
    "QAValidator": QA_VALIDATOR,
    "QAValidatorFix": QA_VALIDATOR_FIX,
    "TestRunner": TEST_RUNNER,
    "ConsistencyChecker": CONSISTENCY_CHECKER,
}


def load_system_prompt(agent_def: dict) -> str:
    """Load system prompt from the skill .md file."""
    return _load_skill(agent_def["skill_file"])
