"""Wraps scripts/assemble_effective_prompt.py as an in-process MCP tool."""

from __future__ import annotations

import sys
from pathlib import Path

from claude_agent_sdk import tool

# Add scripts/ to path so we can import the assembly module
_skill_root = Path(__file__).resolve().parent.parent.parent
_scripts_dir = _skill_root / "scripts"


@tool("assemble_prompt", "Assemble effective_prompt.md from _manifest.yaml", {
    "scenario_dir": str,
    "dry_run": bool,
})
async def assemble_prompt(args):
    """Assemble the effective prompt from manifest — wraps the existing script."""
    scenario_dir = Path(args["scenario_dir"]).resolve()
    dry_run = args.get("dry_run", False)
    print(f"  🏗️ assemble: {scenario_dir.name} {'(dry run)' if dry_run else ''}", flush=True)

    if not scenario_dir.exists():
        return {"content": [{"type": "text", "text": f"ERROR: Directory not found: {scenario_dir}"}]}

    # Import the existing script in-process
    try:
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        from assemble_effective_prompt import assemble
        assemble(scenario_dir, output=None, dry_run=dry_run)
        mode = "DRY RUN" if dry_run else "Assembled"
        return {"content": [{"type": "text", "text": f"{mode}: effective_prompt.md in {scenario_dir.name}"}]}
    except FileNotFoundError as e:
        return {"content": [{"type": "text", "text": f"ERROR: {e}"}]}
    except ValueError as e:
        return {"content": [{"type": "text", "text": f"ERROR: {e}"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"ERROR assembling prompt: {e}"}]}
