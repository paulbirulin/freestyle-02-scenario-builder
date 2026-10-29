"""File-system tools with path sandboxing for the scenario builder."""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import tool

# These will be set by the orchestrator before each subagent run
_workspace_root: Path | None = None
_skill_root: Path = Path(__file__).resolve().parent.parent.parent


def set_workspace(workspace: Path) -> None:
    """Set the active workspace root for path validation."""
    global _workspace_root
    _workspace_root = workspace.resolve()


def _validate_path(p: Path, must_be_in_workspace: bool = True) -> Path:
    """Resolve and validate a path is within allowed boundaries."""
    resolved = p.resolve()
    if must_be_in_workspace and _workspace_root is not None:
        if not str(resolved).startswith(str(_workspace_root)):
            raise ValueError(f"Path outside workspace: {resolved}")
    return resolved


@tool("read_source_files", "Read a source file from the workspace or source materials", {
    "path": str,
})
async def read_source_files(args):
    """Read a file from the workspace or source directories."""
    target = Path(args["path"]).resolve()
    print(f"  📖 read: {target.name}", flush=True)
    if not target.exists():
        return {"content": [{"type": "text", "text": f"ERROR: File not found: {target}"}]}
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
        # Truncate very large files
        if len(text) > 50_000:
            text = text[:50_000] + f"\n\n... [truncated, total {len(text)} chars]"
        return {"content": [{"type": "text", "text": text}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"ERROR reading file: {e}"}]}


@tool("write_component", "Create or update a scenario component file in the workspace. Overwrites by default.", {
    "path": str,
    "content": str,
    "overwrite": bool,
})
async def write_component(args):
    """Write a file to the workspace with path validation."""
    print(f"  📝 write: {args.get('path', '?')}", flush=True)
    if _workspace_root is None:
        return {"content": [{"type": "text", "text": "ERROR: Workspace not configured"}]}

    target = Path(args["path"])
    if not target.is_absolute():
        target = _workspace_root / target
    target = target.resolve()

    # Safety: must be within workspace
    if not str(target).startswith(str(_workspace_root)):
        return {"content": [{"type": "text", "text": f"ERROR: Path outside workspace: {target}"}]}

    if target.exists() and not args.get("overwrite", True):
        return {"content": [{"type": "text", "text": f"File already exists: {target.name}. Use overwrite=true to replace."}]}

    target.parent.mkdir(parents=True, exist_ok=True)
    content = args["content"]
    existed = target.exists()
    target.write_text(content, encoding="utf-8")
    action = "Updated" if existed else "Created"
    return {"content": [{"type": "text", "text": f"{action}: {target.name} ({len(content)} chars)"}]}


@tool("list_workspace", "List files and directories in the workspace", {
    "subpath": str,
})
async def list_workspace(args):
    """List contents of a workspace directory."""
    print(f"  📂 list: {args.get('subpath', '.')}", flush=True)
    if _workspace_root is None:
        return {"content": [{"type": "text", "text": "ERROR: Workspace not configured"}]}

    subpath = args.get("subpath", ".")
    target = (_workspace_root / subpath).resolve()

    if not str(target).startswith(str(_workspace_root)):
        return {"content": [{"type": "text", "text": "ERROR: Path outside workspace"}]}

    if not target.exists():
        return {"content": [{"type": "text", "text": f"Directory not found: {subpath}"}]}

    if target.is_file():
        return {"content": [{"type": "text", "text": f"FILE: {target.name} ({target.stat().st_size} bytes)"}]}

    lines = []
    for item in sorted(target.iterdir()):
        rel = item.relative_to(_workspace_root)
        if item.is_dir():
            count = sum(1 for _ in item.rglob("*") if _.is_file())
            lines.append(f"📁 {rel}/ ({count} files)")
        else:
            lines.append(f"📄 {rel} ({item.stat().st_size} bytes)")

    if not lines:
        lines.append("(empty directory)")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool("read_reference", "Read a reference document from the skill's references/ directory", {
    "name": str,
})
async def read_reference(args):
    """Read a reference .md file from references/."""
    name = args["name"]
    if not name.endswith(".md"):
        name += ".md"

    ref_path = _skill_root / "references" / name
    if not ref_path.exists():
        # List available references
        available = [f.name for f in (_skill_root / "references").glob("*.md")]
        return {"content": [{"type": "text", "text": (
            f"ERROR: Reference not found: {name}\n"
            f"Available: {', '.join(available)}"
        )}]}

    text = ref_path.read_text(encoding="utf-8")
    return {"content": [{"type": "text", "text": text}]}


@tool("find_replace_in_file", "Find and replace text in a workspace file. Simple and reliable way to edit files.", {
    "path": str,
    "find": str,
    "replace": str,
})
async def find_replace_in_file(args):
    """Find and replace text in a file within the workspace."""
    if _workspace_root is None:
        return {"content": [{"type": "text", "text": "ERROR: Workspace not configured"}]}

    target = Path(args["path"])
    if not target.is_absolute():
        target = _workspace_root / target
    target = target.resolve()

    # Safety: must be within workspace
    if not str(target).startswith(str(_workspace_root)):
        return {"content": [{"type": "text", "text": f"ERROR: Path outside workspace: {target}"}]}

    if not target.exists():
        return {"content": [{"type": "text", "text": f"ERROR: File not found: {target.name}"}]}

    find_text = args["find"]
    replace_text = args["replace"]
    print(f"  🔧 replace in {target.name}: '{find_text[:40]}' → '{replace_text[:40]}'", flush=True)

    content = target.read_text(encoding="utf-8")
    count = content.count(find_text)

    if count == 0:
        return {"content": [{"type": "text", "text": (
            f"NOT FOUND: '{find_text[:50]}' not found in {target.name}. "
            f"File has {len(content)} chars. Check exact spelling and whitespace."
        )}]}

    new_content = content.replace(find_text, replace_text)
    target.write_text(new_content, encoding="utf-8")

    return {"content": [{"type": "text", "text": (
        f"REPLACED: {count} occurrence(s) of '{find_text[:30]}' → '{replace_text[:30]}' "
        f"in {target.name}"
    )}]}
