"""Pydantic models for session state, events, and data structures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ConsistencySeverity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class GateDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# User Q&A
# ---------------------------------------------------------------------------

class UserQuestion(BaseModel):
    """A clarifying question from a subagent to the user."""
    question_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    agent: str
    step: int
    question: str
    context: str = ""
    options: list[str] = Field(default_factory=list)
    blocking: bool = True
    answer: str | None = None
    answered_at: datetime | None = None


class UserAnswer(BaseModel):
    """User's answer to a clarifying question."""
    question_id: str
    answer: str


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------

class ConsistencyIssue(BaseModel):
    """A single issue found by the ConsistencyChecker."""
    description: str
    severity: ConsistencySeverity = ConsistencySeverity.WARNING
    component: str = ""
    suggestion: str = ""


class ConsistencyReport(BaseModel):
    """Report from ConsistencyChecker after a step."""
    step: int
    status: ConsistencySeverity = ConsistencySeverity.OK
    issues: list[ConsistencyIssue] = Field(default_factory=list)
    questions: list[UserQuestion] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

class GateStatus(BaseModel):
    """Status of a single gate checkpoint."""
    gate_id: int
    description: str
    decision: GateDecision = GateDecision.PENDING
    decided_at: datetime | None = None
    comment: str = ""


# ---------------------------------------------------------------------------
# Messages for SSE streaming
# ---------------------------------------------------------------------------

class SubagentMessage(BaseModel):
    """A message from a subagent for streaming to the UI."""
    agent: str
    step: int
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolUseEvent(BaseModel):
    """Notification that a subagent used a tool."""
    agent: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""


class StepResult(BaseModel):
    """Result of a completed step / subagent run."""
    step: int
    agent: str
    summary: str = ""
    artifacts_created: list[str] = Field(default_factory=list)
    questions_asked: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session state (persisted to JSON)
# ---------------------------------------------------------------------------

class SessionState(BaseModel):
    """Full session state — serialized to sessions/{id}/state.json."""
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: SessionStatus = SessionStatus.IDLE
    current_step: int = 0
    current_agent: str = ""

    # Model configuration (set per-session from UI)
    model_id: str = ""  # empty = SDK auto-select
    effort: str = "high"  # low | medium | high | xhigh | max

    # Language settings
    ui_language: str = "ru"  # Language for AI communication with user
    scenario_language: str = "ru"  # Language for generated scenario content

    # Feature flags
    consistency_enabled: bool = False  # Run consistency checks after each step

    # Gate tracking
    gates: dict[int, GateStatus] = Field(default_factory=dict)

    # Accumulated data across steps
    source_register: str = ""
    boundaries: str = ""
    layer_plan: str = ""
    qa_result: str = ""
    test_result: str = ""

    # Consistency reports per step
    consistency_reports: dict[int, ConsistencyReport] = Field(default_factory=dict)

    # Q&A history
    questions: list[UserQuestion] = Field(default_factory=list)

    # Files
    source_files: list[str] = Field(default_factory=list)
    workspace_dir: str = ""

    # SDK session tracking for resume between agents
    sdk_session_id: str = ""  # Claude SDK session ID — enables context sharing

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_updated(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
