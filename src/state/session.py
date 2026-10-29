"""Session lifecycle management with JSON file persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .models import SessionState, SessionStatus

if TYPE_CHECKING:
    pass

# Base directory for all sessions — resolved relative to the skill root
SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = SKILL_ROOT / "sessions"


class SessionManager:
    """Create, load, save, and list sessions with JSON persistence."""

    def __init__(self, sessions_dir: Path | None = None):
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache of active sessions
        self._active: dict[str, SessionState] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_session(
        self,
        source_files: list[str] | None = None,
        workspace_dir: str = "",
    ) -> SessionState:
        """Create a new session and persist it."""
        state = SessionState(
            source_files=source_files or [],
            workspace_dir=workspace_dir,
        )
        session_dir = self.sessions_dir / state.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        # Create workspace subdirectory for generated files
        (session_dir / "workspace").mkdir(exist_ok=True)
        if not state.workspace_dir:
            state.workspace_dir = str(session_dir / "workspace")
        self._active[state.session_id] = state
        self.save(state)
        return state

    def load(self, session_id: str) -> SessionState:
        """Load session from JSON file or in-memory cache."""
        if session_id in self._active:
            return self._active[session_id]
        state_path = self.sessions_dir / session_id / "state.json"
        if not state_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        data = json.loads(state_path.read_text(encoding="utf-8"))
        state = SessionState.model_validate(data)
        self._active[session_id] = state
        return state

    def save(self, state: SessionState) -> None:
        """Persist session state to JSON."""
        state.mark_updated()
        session_dir = self.sessions_dir / state.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        state_path = session_dir / "state.json"
        state_path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def list_sessions(self) -> list[dict]:
        """List all sessions with basic info."""
        result = []
        if not self.sessions_dir.exists():
            return result
        for d in sorted(self.sessions_dir.iterdir()):
            state_path = d / "state.json"
            if state_path.exists():
                try:
                    data = json.loads(state_path.read_text(encoding="utf-8"))
                    result.append({
                        "session_id": data.get("session_id", d.name),
                        "status": data.get("status", "unknown"),
                        "current_step": data.get("current_step", 0),
                        "current_agent": data.get("current_agent", ""),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    })
                except (json.JSONDecodeError, KeyError):
                    pass
        return result

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its workspace."""
        import shutil
        session_dir = self.sessions_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            self._active.pop(session_id, None)
            return True
        return False

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def update_status(self, session_id: str, status: SessionStatus) -> SessionState:
        state = self.load(session_id)
        state.status = status
        self.save(state)
        return state

    def update_step(self, session_id: str, step: int, agent: str) -> SessionState:
        state = self.load(session_id)
        state.current_step = step
        state.current_agent = agent
        self.save(state)
        return state
