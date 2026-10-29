"""Custom MCP tools for the scenario builder.

All tools are registered as in-process SDK MCP servers so Claude can invoke
them without subprocess overhead.
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server

from .file_tools import read_source_files, write_component, list_workspace, read_reference, find_replace_in_file
from .assembly_tools import assemble_prompt
from .validation_tools import validate_scenario
from .question_tool import ask_user_question
from .proposal_tool import present_proposal

# Skill root — used by tools to locate references/ and scripts/
SKILL_ROOT = Path(__file__).resolve().parent.parent.parent


def create_scenario_tools_server(question_callback=None):
    """Create the in-process MCP server with all scenario builder tools.

    Args:
        question_callback: async callable(question_data) -> str
            Called when ask_user_question is invoked; must return the user's answer.
    """
    # Inject the callback so the question tool can reach the orchestrator
    if question_callback is not None:
        ask_user_question._question_callback = question_callback
        present_proposal._question_callback = question_callback

    return create_sdk_mcp_server(
        name="scenario-builder-tools",
        version="1.0.0",
        tools=[
            read_source_files,
            write_component,
            find_replace_in_file,
            list_workspace,
            read_reference,
            assemble_prompt,
            validate_scenario,
            ask_user_question,
            present_proposal,
        ],
    )
