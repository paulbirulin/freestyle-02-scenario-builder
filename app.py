"""FastAPI entry point — REST endpoints + SSE streaming for the scenario builder web UI."""

from __future__ import annotations

from pathlib import Path

# Load .env BEFORE any other imports so AWS keys are available everywhere
from dotenv import load_dotenv
import os
load_dotenv(Path(__file__).resolve().parent / ".env")
# Remove ANTHROPIC_MODEL — let the SDK auto-select the best available model
# to avoid model_not_found errors with invalid/stale model IDs
os.environ.pop("ANTHROPIC_MODEL", None)

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.orchestrator import ScenarioOrchestrator
from src.state.session import SessionManager
from src.utils import find_scenarios, fork_scenario, collect_source_files

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("app")

SKILL_ROOT = Path(__file__).resolve().parent
STATIC_DIR = SKILL_ROOT / "static"
# Repo root — for scanning existing scenarios
REPO_ROOT = SKILL_ROOT.parent.parent.parent  # .claude/skills/freestyle-02-scenario-builder -> repo root
SCENARIOS_DIR = REPO_ROOT / "SCENARIOS"

app = FastAPI(title="Freestyle-02 Scenario Builder", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Global session manager
session_manager = SessionManager()

# Active orchestrators and their SSE queues
_orchestrators: dict[str, ScenarioOrchestrator] = {}
_sse_queues: dict[str, asyncio.Queue] = {}
# Track running orchestrator tasks to prevent races
_running_tasks: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

# Available models for the UI selector
AVAILABLE_MODELS = [
    {"id": "", "name": "Auto (SDK default)", "description": "SDK auto-selects the best available model"},
    {"id": "sonnet", "name": "Sonnet 4.5", "description": "Claude Sonnet 4.5 — best quality"},
    {"id": "haiku", "name": "Haiku 4.5", "description": "Claude Haiku 4.5 — fast & cheap"},
]

EFFORT_LEVELS = [
    {"id": "low", "name": "Low", "description": "Minimal thinking, fastest"},
    {"id": "medium", "name": "Medium", "description": "Balanced speed and quality"},
    {"id": "high", "name": "High", "description": "Thorough analysis (default)"},
    {"id": "xhigh", "name": "Extra High", "description": "Deep reasoning"},
    {"id": "max", "name": "Max", "description": "Maximum thinking budget"},
]

AVAILABLE_LANGUAGES = [
    {"id": "ru", "name": "Русский", "flag": "🇷🇺"},
    {"id": "en", "name": "English", "flag": "🇺🇸"},
    {"id": "de", "name": "Deutsch", "flag": "🇩🇪"},
    {"id": "tr", "name": "Türkçe", "flag": "🇹🇷"},
    {"id": "he", "name": "עברית", "flag": "🇮🇱"},
]


class CreateSessionRequest(BaseModel):
    source_files: list[str] = []
    workspace_dir: str = ""
    scenario_path: str = ""  # optional: path to existing scenario to load
    fork: bool = True        # if True, clone the scenario directory before editing
    fork_name: str = ""      # custom name for the fork (auto-generated if empty)
    model_id: str = ""       # model shortname: "", "sonnet", "haiku"
    effort: str = "high"     # low | medium | high | xhigh | max
    ui_language: str = "ru"  # language for AI ↔ user communication
    scenario_language: str = "ru"  # language for generated content


class SendMessageRequest(BaseModel):
    message: str


class UpdateSettingsRequest(BaseModel):
    model_id: str | None = None
    effort: str | None = None
    ui_language: str | None = None
    scenario_language: str | None = None


class GateApprovalRequest(BaseModel):
    approved: bool
    comment: str = ""


class QuestionAnswerRequest(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _get_queue(session_id: str) -> asyncio.Queue:
    if session_id not in _sse_queues:
        _sse_queues[session_id] = asyncio.Queue()
    return _sse_queues[session_id]


async def _push_event(session_id: str, event_type: str, data: dict) -> None:
    q = _get_queue(session_id)
    await q.put({"type": event_type, "data": data})


# ---------------------------------------------------------------------------
# Root → serve index.html
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "Frontend not found")
    return index.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existing scenarios browser
# ---------------------------------------------------------------------------

def _parse_yaml_key(path: Path, key: str) -> str | None:
    """Quick parse of a single key from a YAML file without full parser."""
    import re
    try:
        text = path.read_text(encoding="utf-8")
        m = re.search(rf'^{re.escape(key)}:\s*["\']?([^"\'\n]+)', text, re.MULTILINE)
        return m.group(1).strip() if m else None
    except Exception:
        return None


@app.get("/api/scenarios")
async def list_existing_scenarios():
    """Scan SCENARIOS/ directory tree for existing scenarios."""
    scenarios = find_scenarios(SCENARIOS_DIR)

    # Enrich with extra metadata for the web UI
    result = []
    for s in scenarios:
        scenario_dir = Path(s.path)
        config = scenario_dir / "_config.yaml"
        prompt_file = _parse_yaml_key(config, "prompt_file") if config.exists() else None
        result.append({
            "name": s.name,
            "group": s.group,
            "path": s.path,
            "has_config": config.exists(),
            "has_manifest": True,
            "prompt_file": prompt_file or "effective_prompt.md",
            "file_count": s.file_count,
            "components": s.components,
            "display": s.display,
        })

    return {"scenarios": result, "scenarios_dir": str(SCENARIOS_DIR)}


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
async def list_sessions():
    return session_manager.list_sessions()


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    source_files = list(req.source_files)
    workspace_dir = req.workspace_dir
    forked_from = ""
    fork_name_result = ""

    # If an existing scenario path is provided, load its files as sources
    if req.scenario_path:
        scenario_dir = Path(req.scenario_path)
        if scenario_dir.exists() and scenario_dir.is_dir():
            # Fork: clone the scenario directory to avoid editing the original
            if req.fork:
                try:
                    result = fork_scenario(scenario_dir, custom_name=req.fork_name)
                    forked_from = result.original_name
                    fork_name_result = result.new_name
                    scenario_dir = result.new_path
                    logger.info(f"Forked scenario: {forked_from} → {fork_name_result} at {result.new_path}")
                except FileExistsError:
                    raise HTTPException(409, f"Fork target already exists: {req.fork_name}")

            source_files.extend(collect_source_files(scenario_dir))
            workspace_dir = str(scenario_dir)

    state = session_manager.create_session(
        source_files=source_files,
        workspace_dir=workspace_dir,
    )
    # Apply model/effort/language settings
    state.model_id = req.model_id
    state.effort = req.effort
    state.ui_language = req.ui_language
    state.scenario_language = req.scenario_language
    session_manager.save(state)

    return {
        "session_id": state.session_id,
        "workspace_dir": state.workspace_dir,
        "source_files_loaded": len(source_files),
        "model_id": state.model_id,
        "effort": state.effort,
        "ui_language": state.ui_language,
        "scenario_language": state.scenario_language,
        "forked_from": forked_from,
        "fork_name": fork_name_result,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    try:
        state = session_manager.load(session_id)
        return json.loads(state.model_dump_json())
    except FileNotFoundError:
        raise HTTPException(404, f"Session not found: {session_id}")


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_manager.delete_session(session_id):
        _orchestrators.pop(session_id, None)
        _sse_queues.pop(session_id, None)
        return {"deleted": True}
    raise HTTPException(404, "Session not found")


@app.put("/api/sessions/{session_id}/settings")
async def update_settings(session_id: str, req: UpdateSettingsRequest):
    """Update model/effort settings for a session (can be changed between steps)."""
    try:
        state = session_manager.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    if req.model_id is not None:
        valid_ids = [m["id"] for m in AVAILABLE_MODELS]
        if req.model_id not in valid_ids:
            raise HTTPException(400, f"Invalid model_id: {req.model_id}. Valid: {valid_ids}")
        state.model_id = req.model_id
    if req.effort is not None:
        valid_efforts = [e["id"] for e in EFFORT_LEVELS]
        if req.effort not in valid_efforts:
            raise HTTPException(400, f"Invalid effort: {req.effort}. Valid: {valid_efforts}")
        state.effort = req.effort
    if req.ui_language is not None:
        valid_langs = [l["id"] for l in AVAILABLE_LANGUAGES]
        if req.ui_language not in valid_langs:
            raise HTTPException(400, f"Invalid ui_language: {req.ui_language}. Valid: {valid_langs}")
        state.ui_language = req.ui_language
    if req.scenario_language is not None:
        valid_langs = [l["id"] for l in AVAILABLE_LANGUAGES]
        if req.scenario_language not in valid_langs:
            raise HTTPException(400, f"Invalid scenario_language: {req.scenario_language}. Valid: {valid_langs}")
        state.scenario_language = req.scenario_language

    session_manager.save(state)
    logger.info(
        f"Settings updated for {session_id}: model={state.model_id!r}, effort={state.effort}, "
        f"ui_lang={state.ui_language}, scenario_lang={state.scenario_language}"
    )
    return {
        "model_id": state.model_id, "effort": state.effort,
        "ui_language": state.ui_language, "scenario_language": state.scenario_language,
    }


@app.get("/api/models")
async def list_models():
    """Return available models, effort levels, and languages."""
    return {
        "models": AVAILABLE_MODELS,
        "efforts": EFFORT_LEVELS,
        "languages": AVAILABLE_LANGUAGES,
    }


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/upload")
async def upload_file(session_id: str, file: UploadFile = File(...)):
    try:
        state = session_manager.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    workspace = Path(state.workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    # Save uploaded file to workspace/sources/
    sources_dir = workspace / "sources"
    sources_dir.mkdir(exist_ok=True)
    dest = sources_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Add to source_files list
    file_path = str(dest)
    if file_path not in state.source_files:
        state.source_files.append(file_path)
        session_manager.save(state)

    return {"uploaded": file.filename, "path": file_path}


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@app.get("/api/stream/{session_id}")
async def sse_stream(session_id: str):
    """Server-Sent Events stream for real-time updates."""
    try:
        session_manager.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    queue = _get_queue(session_id)

    async def event_generator():
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'data': {'session_id': session_id}})}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                # Keep-alive ping
                yield f"data: {json.dumps({'type': 'ping', 'data': {}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Send message → start/continue orchestration
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/message")
async def send_message(session_id: str, req: SendMessageRequest):
    try:
        state = session_manager.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    # Race guard: reject if an orchestrator task is already running for this session
    existing_task = _running_tasks.get(session_id)
    if existing_task and not existing_task.done():
        logger.warning(f"Rejected /message for {session_id}: orchestrator already running")
        raise HTTPException(
            409,
            "An orchestrator is already running for this session. "
            "Wait for it to finish or stop it first."
        )

    # Create orchestrator callbacks that push to SSE
    async def on_message(data: dict) -> None:
        await _push_event(session_id, "message", data)

    async def on_gate(data: dict) -> None:
        await _push_event(session_id, "gate", data)

    async def on_question(data: dict) -> str:
        await _push_event(session_id, "question", data)
        # Return empty — the actual answer comes via answer_question endpoint
        return ""

    async def on_consistency(data: dict) -> None:
        await _push_event(session_id, "consistency", data)

    async def on_step_change(data: dict) -> None:
        await _push_event(session_id, "step_change", data)

    orch = ScenarioOrchestrator(
        session_manager=session_manager,
        session_id=session_id,
        on_message=on_message,
        on_gate=on_gate,
        on_question=on_question,
        on_consistency=on_consistency,
        on_step_change=on_step_change,
    )
    _orchestrators[session_id] = orch

    # Run in background so the API call returns immediately;
    # track the task so we can prevent races.
    async def _guarded_run():
        import time as _time
        t0 = _time.monotonic()
        final_status = "completed"
        try:
            await orch.run(user_message=req.message)
        except Exception:
            logger.exception(f"Orchestrator failed for session {session_id}")
            final_status = "failed"
        finally:
            _running_tasks.pop(session_id, None)
            elapsed = _time.monotonic() - t0
            # Push completion event with summary (mirrors CLI's final summary)
            try:
                st = session_manager.load(session_id)
                await _push_event(session_id, "completed", {
                    "status": st.status.value if hasattr(st.status, 'value') else str(st.status),
                    "elapsed_seconds": round(elapsed, 1),
                    "steps": st.current_step,
                    "questions": len(st.questions),
                    "gates_approved": sum(
                        1 for g in st.gates.values()
                        if hasattr(g.decision, 'value') and g.decision.value == 'approved'
                    ),
                    "gates_total": len(st.gates),
                    "consistency_checks": len(st.consistency_reports),
                    "sdk_session_id": st.sdk_session_id,
                })
            except Exception:
                logger.exception("Failed to push completion event")

    task = asyncio.create_task(_guarded_run())
    _running_tasks[session_id] = task

    return {"status": "started", "session_id": session_id}


# ---------------------------------------------------------------------------
# Gate approval
# ---------------------------------------------------------------------------

@app.post("/api/gates/{session_id}/{gate_id}")
async def approve_gate(session_id: str, gate_id: int, req: GateApprovalRequest):
    orch = _orchestrators.get(session_id)
    if orch is None:
        raise HTTPException(404, "No active orchestrator for this session")
    await orch.approve_gate(gate_id, req.approved, req.comment)
    return {"gate_id": gate_id, "approved": req.approved}


# ---------------------------------------------------------------------------
# Question answering
# ---------------------------------------------------------------------------

@app.post("/api/questions/{session_id}/{question_id}")
async def answer_question(session_id: str, question_id: str, req: QuestionAnswerRequest):
    orch = _orchestrators.get(session_id)
    if orch is None:
        raise HTTPException(404, "No active orchestrator for this session")
    await orch.answer_question(question_id, req.answer)
    return {"question_id": question_id, "answered": True}


# ---------------------------------------------------------------------------
# Session log files (long agent outputs)
# ---------------------------------------------------------------------------

@app.get("/api/sessions/{session_id}/logs/{filename}")
async def get_session_log(session_id: str, filename: str):
    """Serve a session log file (long agent output saved as .md)."""
    import re
    # Safety: only allow safe filenames
    if not re.match(r'^step\d+_\w+\.md$', filename):
        raise HTTPException(400, "Invalid log filename")

    log_path = SKILL_ROOT / "sessions" / session_id / filename
    if not log_path.exists():
        raise HTTPException(404, "Log file not found")

    content = log_path.read_text(encoding="utf-8", errors="replace")
    return {"filename": filename, "content": content, "size": len(content)}


class UpdateLogRequest(BaseModel):
    content: str


@app.put("/api/sessions/{session_id}/logs/{filename}")
async def update_session_log(session_id: str, filename: str, req: UpdateLogRequest):
    """Save edits to a session log file AND update orchestrator state.

    This ensures the next agent receives the edited content, not the original.
    Mapping: step1_SourceAnalyst → source_register, step3_StructurePlanner → layer_plan, etc.
    """
    import re
    if not re.match(r'^step\d+_\w+\.md$', filename):
        raise HTTPException(400, "Invalid log filename")

    log_path = SKILL_ROOT / "sessions" / session_id / filename
    if not log_path.exists():
        raise HTTPException(404, "Log file not found")

    # Save to disk
    log_path.write_text(req.content, encoding="utf-8")

    # Update orchestrator state so next agent gets edited content
    state_field_updated = ""
    orch = _orchestrators.get(session_id)
    if orch:
        # Map filename → state field
        field_map = {
            "SourceAnalyst": "source_register",
            "StructurePlanner": "layer_plan",
            "QAValidator": "qa_result",
            "TestRunner": "test_result",
        }
        m = re.match(r'^step\d+_(\w+)\.md$', filename)
        if m:
            agent_name = m.group(1)
            field = field_map.get(agent_name)
            if field and hasattr(orch.state, field):
                setattr(orch.state, field, req.content)
                orch._save()
                state_field_updated = field
                logger.info(f"Updated state.{field} from edited log ({len(req.content)} chars)")

    logger.info(f"Updated log file: {log_path} ({len(req.content)} chars)")
    return {
        "filename": filename,
        "size": len(req.content),
        "saved": True,
        "state_updated": state_field_updated,
    }


class SaveQuestionLogRequest(BaseModel):
    question_id: str
    content: str


@app.post("/api/sessions/{session_id}/save-question-log")
async def save_question_log(session_id: str, req: SaveQuestionLogRequest):
    """Save question content as a log file so it can be edited via the modal."""
    log_dir = SKILL_ROOT / "sessions" / session_id
    log_dir.mkdir(parents=True, exist_ok=True)

    # Determine step from orchestrator state
    orch = _orchestrators.get(session_id)
    step = 0
    agent = "question"
    if orch:
        step = orch.state.current_step
        agent = orch.state.current_agent or "question"

    filename = f"step{step}_{agent}.md"
    log_path = log_dir / filename
    log_path.write_text(req.content, encoding="utf-8")
    logger.info(f"Saved question log: {log_path} ({len(req.content)} chars)")
    return {"filename": filename, "size": len(req.content)}


# ---------------------------------------------------------------------------
# Session control
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    orch = _orchestrators.get(session_id)
    if orch:
        from src.state.models import SessionStatus
        orch.state.status = SessionStatus.PAUSED
        session_manager.save(orch.state)

    # Cancel the running orchestrator task
    task = _running_tasks.get(session_id)
    if task and not task.done():
        task.cancel()
        _running_tasks.pop(session_id, None)
        logger.info(f"Cancelled running task for session {session_id}")

    # Push stop event to SSE
    await _push_event(session_id, "completed", {
        "status": "paused",
        "elapsed_seconds": 0,
        "steps": orch.state.current_step if orch else 0,
        "questions": len(orch.state.questions) if orch else 0,
        "gates_approved": 0,
        "gates_total": len(orch.state.gates) if orch else 0,
        "consistency_checks": 0,
        "sdk_session_id": orch.state.sdk_session_id if orch else "",
    })

    return {"status": "paused"}


# ---------------------------------------------------------------------------
# Workspace file listing
# ---------------------------------------------------------------------------

@app.get("/api/sessions/{session_id}/files")
async def list_files(session_id: str):
    try:
        state = session_manager.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    workspace = Path(state.workspace_dir)
    if not workspace.exists():
        return {"files": []}

    files = []
    for f in sorted(workspace.rglob("*")):
        if f.is_file():
            files.append({
                "path": str(f.relative_to(workspace)),
                "size": f.stat().st_size,
                "name": f.name,
            })
    return {"files": files}


@app.get("/api/sessions/{session_id}/files/{path:path}")
async def read_file(session_id: str, path: str):
    try:
        state = session_manager.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")

    workspace = Path(state.workspace_dir)
    target = (workspace / path).resolve()

    # Safety check
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(403, "Path outside workspace")

    if not target.exists():
        raise HTTPException(404, "File not found")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(500, f"Error reading file: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8765, reload=True)
