"""Shared utilities for CLI and Web interfaces."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

class ScenarioInfo(NamedTuple):
    name: str
    group: str
    path: str
    file_count: int
    components: int
    display: str


def find_scenarios(scenarios_dir: Path) -> list[ScenarioInfo]:
    """Scan SCENARIOS/ directory tree for existing scenarios.

    Returns a list of ScenarioInfo for each scenario that has a _manifest.yaml.
    """
    if not scenarios_dir.exists():
        return []

    result: list[ScenarioInfo] = []
    for group_dir in sorted(scenarios_dir.iterdir()):
        if not group_dir.is_dir():
            continue
        sc_dir = group_dir / "scenarios"
        if not sc_dir.exists():
            continue
        for scenario_dir in sorted(sc_dir.iterdir()):
            if not scenario_dir.is_dir() or not (scenario_dir / "_manifest.yaml").exists():
                continue
            files = [f for f in scenario_dir.rglob("*") if f.is_file()]
            components = sum(1 for f in files if f.suffix in (".md", ".txt"))
            result.append(ScenarioInfo(
                name=scenario_dir.name,
                group=group_dir.name,
                path=str(scenario_dir),
                file_count=len(files),
                components=components,
                display=f"{group_dir.name} / {scenario_dir.name}",
            ))
    return result


# ---------------------------------------------------------------------------
# Scenario fork (clone with auto-numbered name)
# ---------------------------------------------------------------------------

class ForkResult(NamedTuple):
    new_path: Path
    new_name: str
    original_name: str


def fork_scenario(
    scenario_dir: Path,
    custom_name: str = "",
) -> ForkResult:
    """Clone a scenario directory with an auto-incremented name.

    Args:
        scenario_dir: Path to the original scenario directory.
        custom_name: Optional custom name for the fork. If empty, auto-generates.

    Returns:
        ForkResult with the new path, name, and original name.

    Raises:
        FileExistsError: If the target directory already exists.
        FileNotFoundError: If the source directory doesn't exist.
    """
    if not scenario_dir.exists():
        raise FileNotFoundError(f"Scenario not found: {scenario_dir}")

    base_name = scenario_dir.name
    parent = scenario_dir.parent

    if custom_name:
        new_name = custom_name
    else:
        # Auto-generate: find next available number
        m = re.match(r'^(.+?)-(\d+)$', base_name)
        prefix = m.group(1) if m else base_name
        existing_nums: set[int] = set()
        for d in parent.iterdir():
            if d.is_dir():
                mx = re.match(rf'^{re.escape(prefix)}-(\d+)$', d.name)
                if mx:
                    existing_nums.add(int(mx.group(1)))
        base_num = int(m.group(2)) if m else 0
        next_num = max(existing_nums | {base_num}) + 1
        new_name = f"{prefix}-{next_num:02d}"

    new_path = parent / new_name
    if new_path.exists():
        raise FileExistsError(f"Fork target already exists: {new_name}")

    shutil.copytree(scenario_dir, new_path)
    return ForkResult(new_path=new_path, new_name=new_name, original_name=base_name)


def suggest_fork_name(scenario_dir: Path) -> str:
    """Generate the suggested fork name without actually forking."""
    base_name = scenario_dir.name
    parent = scenario_dir.parent
    m = re.match(r'^(.+?)-(\d+)$', base_name)
    prefix = m.group(1) if m else base_name
    existing_nums: set[int] = set()
    for d in parent.iterdir():
        if d.is_dir():
            mx = re.match(rf'^{re.escape(prefix)}-(\d+)$', d.name)
            if mx:
                existing_nums.add(int(mx.group(1)))
    base_num = int(m.group(2)) if m else 0
    next_num = max(existing_nums | {base_num}) + 1
    return f"{prefix}-{next_num:02d}"


# ---------------------------------------------------------------------------
# Source file collection
# ---------------------------------------------------------------------------

SCENARIO_EXTENSIONS = (".md", ".txt", ".yaml", ".yml")


def collect_source_files(scenario_dir: Path) -> list[str]:
    """Collect all source files from a scenario directory.

    Returns list of absolute path strings for files with supported extensions.
    """
    if not scenario_dir.exists():
        return []
    return [
        str(f) for f in sorted(scenario_dir.rglob("*"))
        if f.is_file() and f.suffix in SCENARIO_EXTENSIONS
    ]
