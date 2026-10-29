#!/usr/bin/env python3
"""Assemble effective_prompt.md from a Freestyle-02 _manifest.yaml."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def find_manifest(scenario_dir: Path) -> Path:
    """Return the canonical manifest path, with .agents fallback for legacy layouts."""
    canonical = scenario_dir / "_manifest.yaml"
    if canonical.exists():
        return canonical

    legacy = scenario_dir / ".agents" / "_manifest.yaml"
    if legacy.exists():
        return legacy

    raise FileNotFoundError(f"Missing manifest: {canonical}")


def parse_manifest(manifest_path: Path) -> tuple[str, list[str]]:
    prompt_file = "effective_prompt.md"
    assembly_order: list[str] = []
    in_order = False

    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        prompt_match = re.match(r"prompt_file:\s*[\"']?([^\"']+)[\"']?\s*$", stripped)
        if prompt_match:
            prompt_file = prompt_match.group(1)
            continue

        if stripped == "assembly_order:":
            in_order = True
            continue

        if in_order:
            if not stripped:
                continue
            if (
                not raw_line.startswith(" ")
                and not raw_line.startswith("\t")
                and not stripped.startswith("-")
            ):
                in_order = False
                continue
            item_match = re.match(r"-\s*[\"']?([^\"']+)[\"']?\s*$", stripped)
            if item_match:
                assembly_order.append(item_match.group(1))

    if not assembly_order:
        raise ValueError(f"No assembly_order found in {manifest_path}")

    return prompt_file, assembly_order


def assemble(scenario_dir: Path, output: str | None, dry_run: bool) -> None:
    manifest_path = find_manifest(scenario_dir)
    prompt_file, assembly_order = parse_manifest(manifest_path)
    output_path = scenario_dir / (output or prompt_file)

    parts: list[str] = []
    for relative_path in assembly_order:
        component_path = scenario_dir / relative_path
        if not component_path.exists():
            raise FileNotFoundError(f"Missing component from assembly_order: {component_path}")
        text = component_path.read_text(encoding="utf-8").strip()
        parts.append(text)

    assembled = "\n\n---\n\n".join(parts).rstrip() + "\n"

    if dry_run:
        print(f"Would assemble {len(assembly_order)} files into {output_path}")
        return

    output_path.write_text(assembled, encoding="utf-8")
    print(f"Assembled {len(assembly_order)} files into {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_dir", help="Scenario directory containing _manifest.yaml")
    parser.add_argument("--output", help="Override output file name from manifest")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write")
    args = parser.parse_args()

    assemble(Path(args.scenario_dir).resolve(), args.output, args.dry_run)


if __name__ == "__main__":
    main()
