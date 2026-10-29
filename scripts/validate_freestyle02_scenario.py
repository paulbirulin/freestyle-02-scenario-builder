#!/usr/bin/env python3
"""Validate Freestyle-02 scenario structure and common artifact hygiene issues."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_MARKERS = [
    "TODO",
    "FIXME",
    "COMPONENT:",
    "SOURCE:",
    "copied baseline",
    "do not use",
]


def parse_key_value(path: Path, key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*[\"']?([^\"']+)[\"']?\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1)
    return None


def parse_assembly_order(manifest_path: Path) -> list[str]:
    order: list[str] = []
    in_order = False
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == "assembly_order:":
            in_order = True
            continue
        if in_order:
            if not stripped:
                continue
            if not raw_line.startswith(" ") and not raw_line.startswith("\t"):
                break
            match = re.match(r"-\s*[\"']?([^\"']+)[\"']?\s*$", stripped)
            if match:
                order.append(match.group(1))
    return order


def find_manifest(scenario_dir: Path) -> Path | None:
    canonical = scenario_dir / "_manifest.yaml"
    if canonical.exists():
        return canonical

    legacy = scenario_dir / ".agents" / "_manifest.yaml"
    if legacy.exists():
        return legacy

    return None


def validate(scenario_dir: Path, forbidden: list[str]) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = find_manifest(scenario_dir)
    config_path = scenario_dir / "_config.yaml"

    if manifest_path is None:
        errors.append("Missing _manifest.yaml")
        assembly_order: list[str] = []
        prompt_file = "effective_prompt.md"
    else:
        assembly_order = parse_assembly_order(manifest_path)
        prompt_file = parse_key_value(manifest_path, "prompt_file") or "effective_prompt.md"
        if not assembly_order:
            errors.append(f"{manifest_path.relative_to(scenario_dir)} has no assembly_order")

    runtime_prompt = scenario_dir / prompt_file
    if not runtime_prompt.exists():
        errors.append(f"Missing runtime prompt: {prompt_file}")

    for required in assembly_order:
        component = scenario_dir / required
        if not component.exists():
            errors.append(f"Missing component from assembly_order: {required}")

    if "welcome_message.txt" in assembly_order:
        errors.append("welcome_message.txt must not be part of assembly_order")

    if config_path.exists():
        for required_key in ["prompt_file", "sellers_dir", "tests_dir"]:
            if parse_key_value(config_path, required_key) is None:
                warnings.append(f"_config.yaml missing {required_key}")
    else:
        warnings.append("Missing _config.yaml")

    if runtime_prompt.exists():
        runtime_text = runtime_prompt.read_text(encoding="utf-8", errors="replace")
        for marker in forbidden:
            if marker in runtime_text:
                errors.append(f"Runtime prompt contains marker: {marker}")

    group_decisions = scenario_dir.parents[1] / "DECISIONS.md" if len(scenario_dir.parents) > 1 else None
    has_traceability = (
        (group_decisions is not None and group_decisions.exists())
        or (scenario_dir / "DECISIONS.md").exists()
        or (scenario_dir / ".agents" / "DECISIONS.md").exists()
    )
    if not has_traceability:
        warnings.append("Missing traceability artifact: group or scenario DECISIONS.md")

    for warning in warnings:
        print(f"WARNING: {warning}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_dir", help="Scenario directory to validate")
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        help="Additional forbidden marker to search in runtime prompt",
    )
    args = parser.parse_args()

    scenario_dir = Path(args.scenario_dir).resolve()
    if not scenario_dir.exists():
        print(f"ERROR: scenario directory does not exist: {scenario_dir}", file=sys.stderr)
        return 2

    errors = validate(scenario_dir, DEFAULT_MARKERS + args.forbid)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Freestyle-02 scenario validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
