"""Wraps scripts/validate_freestyle02_scenario.py as an in-process MCP tool."""

from __future__ import annotations

import sys
from pathlib import Path

from claude_agent_sdk import tool

_skill_root = Path(__file__).resolve().parent.parent.parent
_scripts_dir = _skill_root / "scripts"


@tool("validate_scenario", "Run Freestyle-02 structural validation on a scenario directory", {
    "scenario_dir": str,
    "extra_forbidden": list,
})
async def validate_scenario(args):
    """Validate scenario structure — wraps the existing validation script."""
    scenario_dir = Path(args["scenario_dir"]).resolve()
    extra = args.get("extra_forbidden", [])
    print(f"  ✅ validate: {scenario_dir.name}", flush=True)

    if not scenario_dir.exists():
        return {"content": [{"type": "text", "text": f"ERROR: Directory not found: {scenario_dir}"}]}

    try:
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        from validate_freestyle02_scenario import validate, DEFAULT_MARKERS
        errors = validate(scenario_dir, DEFAULT_MARKERS + extra)

        if errors:
            error_text = "\n".join(f"❌ {e}" for e in errors)
            return {"content": [{"type": "text", "text": f"VALIDATION FAILED:\n{error_text}"}]}

        return {"content": [{"type": "text", "text": "✅ Validation passed."}]}

    except Exception as e:
        return {"content": [{"type": "text", "text": f"ERROR running validation: {e}"}]}
