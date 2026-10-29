"""Main workflow orchestrator — Python state machine controlling 6 subagents.

The orchestrator is NOT an LLM. It is Python code that:
1. Manages the 10-step workflow state machine
2. Launches scoped subagents via Claude Agent SDK (configured for AWS Bedrock)
3. Enforces gates (pause + wait for user approval)
4. Runs ConsistencyChecker after each major step
5. Handles user Q&A via async callbacks
6. Persists state to JSON for crash recovery

AWS Bedrock Configuration:
  Set these environment variables in .env:
    CLAUDE_CODE_USE_BEDROCK=1
    AWS_REGION=us-east-2
    # One of:
    AWS_BEARER_TOKEN_BEDROCK=<your-token>
    # or:
    AWS_ACCESS_KEY_ID=<key>  +  AWS_SECRET_ACCESS_KEY=<secret>
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Coroutine

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    query,
)

from .hooks.gate_enforcement import enforce_gates, update_gates_passed
from .hooks.safety_hooks import enforce_safety
from .hooks.stop_guard import stop_guard, reset_stop_guard
from .state.models import (
    ConsistencyReport,
    ConsistencySeverity,
    GateDecision,
    GateStatus,
    SessionState,
    SessionStatus,
    UserQuestion,
)
from .state.session import SessionManager
from .subagents import ALL_SUBAGENTS, load_system_prompt
from .tools import create_scenario_tools_server
from .tools.file_tools import set_workspace

logger = logging.getLogger(__name__)

# Skill root for reference paths
SKILL_ROOT = Path(__file__).resolve().parent.parent

# Module-level lock: only ONE claude.exe CLI process at a time (across all sessions)
_cli_lock = asyncio.Lock()


class ScenarioOrchestrator:
    """Programmatic controller for the 10-step scenario build workflow."""

    def __init__(
        self,
        session_manager: SessionManager,
        session_id: str,
        *,
        on_message: Callable[[dict], Coroutine[Any, Any, None]] | None = None,
        on_gate: Callable[[dict], Coroutine[Any, Any, None]] | None = None,
        on_question: Callable[[dict], Coroutine[Any, Any, str]] | None = None,
        on_consistency: Callable[[dict], Coroutine[Any, Any, None]] | None = None,
        on_step_change: Callable[[dict], Coroutine[Any, Any, None]] | None = None,
        on_file_change: Callable[[dict], Coroutine[Any, Any, None]] | None = None,
    ):
        self.sm = session_manager
        self.session_id = session_id
        self.state = self.sm.load(session_id)

        # SSE callback hooks (injected by the FastAPI app)
        self._on_message = on_message
        self._on_gate = on_gate
        self._on_question = on_question
        self._on_consistency = on_consistency
        self._on_step_change = on_step_change
        self._on_file_change = on_file_change

        # Gate approval events — threading.Event for cross-thread safety!
        self._gate_events: dict[int, threading.Event] = {}
        self._gate_decisions: dict[int, bool] = {}

        # Question answer events — threading.Event for cross-thread safety!
        # (questions are created in subagent thread, answered from FastAPI thread)
        self._question_events: dict[str, threading.Event] = {}
        self._question_answers: dict[str, str] = {}

        # Concurrency guards
        self._is_running = False
        self._subagent_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, user_message: str = "") -> None:
        """Execute the full workflow from current state."""
        if self._is_running:
            logger.warning(f"Orchestrator for {self.session_id} is already running, ignoring duplicate run()")
            return
        self._is_running = True
        self.state.status = SessionStatus.RUNNING
        self._save()

        workspace = Path(self.state.workspace_dir)
        set_workspace(workspace)

        try:
            # Step 1-2: Source Analysis
            await self._emit_step(1, "SourceAnalyst")
            result = await self._run_subagent(
                "SourceAnalyst",
                prompt=self._build_source_prompt(user_message),
            )
            # Check if agent asked questions as text instead of using tool
            result = await self._rescue_text_questions(result, "SourceAnalyst", 1)
            # Wait for any unanswered questions before proceeding
            await self._wait_pending_questions("SourceAnalyst")
            self.state.source_register = result
            self._save()

            # Gate 1: Review analysis + confirm boundaries
            await self._gate(1, "Review SourceAnalyst output. Approve to continue, reject to stop.")

            # Step 3-4: Structure Planning (plan only, no edits)
            await self._emit_step(3, "StructurePlanner")
            result = await self._run_subagent(
                "StructurePlanner",
                prompt=self._build_structure_prompt(),
            )
            result = await self._rescue_text_questions(result, "StructurePlanner", 3)
            await self._wait_pending_questions("StructurePlanner")
            self.state.layer_plan = result
            self._save()

            # Gate 2: Confirm edit plan before ContentWriter executes
            await self._gate(2, "Review edit plan. Approve to let ContentWriter execute changes.")

            # Step 5-7: Content Writing (executes edits)
            await self._emit_step(5, "ContentWriter")
            await self._run_subagent(
                "ContentWriter",
                prompt=self._build_content_prompt(),
            )
            self._save()

            # Gate 3: Confirm edits look good
            await self._gate(3, "Review file changes. Approve to proceed to QA.")

            # Step 8: QA Discovery — READ-ONLY, same pattern as StructurePlanner
            # Agent finds issues and proposes fixes but CANNOT write files
            await self._emit_step(8, "QAValidator")
            result = await self._run_subagent(
                "QAValidator",
                prompt=self._build_qa_prompt(),
            )
            result = await self._rescue_text_questions(result, "QAValidator", 8)
            await self._wait_pending_questions("QAValidator")
            self.state.qa_result = result
            self._save()

            # Gate 4: Review QA findings — approve to let QAValidator apply fixes
            await self._gate(4, "Review QA findings. Approve to apply fixes, reject to skip.")

            # Step 8b: QA Fix — same agent WITH write tools, applies approved fixes
            await self._emit_step(8, "QAValidator")
            result = await self._run_subagent(
                "QAValidator",
                prompt=self._build_qa_fix_prompt(),
                override_tools="QAValidatorFix",
            )
            self.state.qa_result = result
            self._save()

            # Step 9-10: Test (optional, controlled by gate)
            await self._emit_step(9, "TestRunner")
            # Gate 5: approve = run tests, reject = skip to retrospective
            try:
                await self._gate(5, "Run batch tests? Approve=run, Reject=skip to retrospective")
                result = await self._run_subagent(
                    "TestRunner",
                    prompt=self._build_test_prompt(),
                )
            except GateRejected:
                result = await self._run_subagent(
                    "TestRunner",
                    prompt=self._build_retrospective_prompt(),
                )
            self.state.test_result = result
            self._save()

            self.state.status = SessionStatus.COMPLETED
            self._save()
            await self._emit_message("system", 10, "🎉 Scenario building complete!")

        except GateRejected as e:
            self.state.status = SessionStatus.PAUSED
            self._save()
            await self._emit_message("system", self.state.current_step, f"⏸️ Paused: {e}")
        except Exception as e:
            logger.exception("Orchestrator error")
            self.state.status = SessionStatus.FAILED
            self._save()
            await self._emit_message("system", self.state.current_step, f"❌ Error: {e}")
        finally:
            self._is_running = False

    # ------------------------------------------------------------------
    # Scenario fork (clone before modify)
    # ------------------------------------------------------------------

    async def _fork_scenario(self, src: Path) -> Path:
        """Clone an existing scenario to a new directory.
        
        Finds the next available number in the same group:
        e.g. ERT-03 → ERT-05 (if ERT-04 already exists).
        Returns path to the new scenario directory.
        """
        import re
        import shutil

        scenarios_dir = src.parent  # e.g. .../SCENARIOS/ERT/scenarios/
        base_name = src.name         # e.g. ERT-03

        # Extract prefix and number
        match = re.match(r'^(.+?)-(\d+)$', base_name)
        if match:
            prefix = match.group(1)         # ERT
            current_num = int(match.group(2))  # 3
        else:
            prefix = base_name
            current_num = 0

        # Find next available number
        existing_nums = set()
        if scenarios_dir.exists():
            for d in scenarios_dir.iterdir():
                if d.is_dir():
                    m = re.match(rf'^{re.escape(prefix)}-(\d+)$', d.name)
                    if m:
                        existing_nums.add(int(m.group(1)))

        next_num = max(existing_nums | {current_num}) + 1
        new_name = f"{prefix}-{next_num:02d}"
        new_path = scenarios_dir / new_name

        # Copy entire scenario directory
        shutil.copytree(src, new_path)

        await self._emit_message(
            "system", 0,
            f"📋 Forked: {base_name} → {new_name}\n"
            f"   Original preserved at: {src}\n"
            f"   Working copy: {new_path}"
        )
        logger.info(f"Forked scenario {base_name} -> {new_name} at {new_path}")

        return new_path

    # ------------------------------------------------------------------
    # Gate approval
    # ------------------------------------------------------------------

    async def approve_gate(self, gate_id: int, approved: bool, comment: str = "") -> None:
        """Called by API when user approves/rejects a gate."""
        self._gate_decisions[gate_id] = approved
        if gate_id in self._gate_events:
            self._gate_events[gate_id].set()

        gate = self.state.gates.get(gate_id)
        if gate:
            gate.decision = GateDecision.APPROVED if approved else GateDecision.REJECTED
            gate.comment = comment
            from datetime import datetime, timezone
            gate.decided_at = datetime.now(timezone.utc)
            self._save()

    async def _gate(self, gate_id: int, description: str) -> None:
        """Pause and wait for user to approve a gate.
        
        Ensures all pending questions are answered first so gates
        don't overlap with question prompts.

        Uses async polling instead of blocking event.wait() to keep
        the asyncio event loop alive — critical for Web mode where
        the approve_gate HTTP endpoint must be reachable.
        """
        # Wait for any pending questions to be answered first
        for q in self.state.questions:
            if q.answer is None and q.question_id in self._question_events:
                logger.info(f"Gate {gate_id}: waiting for pending question {q.question_id}")
                # Poll instead of blocking, so event loop stays alive
                deadline = asyncio.get_event_loop().time() + 600
                while not self._question_events[q.question_id].is_set():
                    if asyncio.get_event_loop().time() > deadline:
                        break
                    await asyncio.sleep(0.5)

        gate = GateStatus(gate_id=gate_id, description=description)
        self.state.gates[gate_id] = gate
        self.state.status = SessionStatus.WAITING_FOR_APPROVAL
        self._save()

        await self._emit_gate(gate_id, description)

        # Register event for cross-thread notification (CLI threads can .set() it)
        event = threading.Event()
        self._gate_events[gate_id] = event
        logger.info(f"Waiting for gate {gate_id} decision (async polling)")

        # Poll with asyncio.sleep to keep event loop alive (30 min timeout)
        timeout_seconds = 1800
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while not event.is_set():
            if asyncio.get_event_loop().time() > deadline:
                logger.warning(f"Gate {gate_id} timed out after {timeout_seconds}s")
                break
            await asyncio.sleep(0.5)

        approved = self._gate_decisions.get(gate_id, False)
        if not approved:
            raise GateRejected(f"User rejected Gate {gate_id}: {description}")

        # Update hook state
        gates_passed = {
            gid for gid, gs in self.state.gates.items()
            if gs.decision == GateDecision.APPROVED
        }
        update_gates_passed(gates_passed)

        self.state.status = SessionStatus.RUNNING
        self._save()

    # ------------------------------------------------------------------
    # Wait for pending questions from agent
    # ------------------------------------------------------------------

    async def _wait_pending_questions(self, agent_name: str) -> None:
        """Block pipeline until all questions from this agent are answered.

        The SDK subagent may ask questions via the MCP tool, but since the tool
        runs in a subprocess it can't truly block. This method ensures we wait
        for user answers before proceeding to the next pipeline step.
        """
        pending = [
            q for q in self.state.questions
            if q.agent == agent_name and q.answer is None
        ]
        if not pending:
            return

        await self._emit_message(
            "system", self.state.current_step,
            f"⏳ Waiting for {len(pending)} unanswered question(s) from {agent_name}..."
        )

        timeout = 1800  # 30 minutes
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            pending = [
                q for q in self.state.questions
                if q.agent == agent_name and q.answer is None
            ]
            if not pending:
                logger.info(f"All questions from {agent_name} answered")
                return
            await asyncio.sleep(0.5)

        logger.warning(f"Timeout waiting for {len(pending)} questions from {agent_name}")

    # ------------------------------------------------------------------
    # Rescue: detect questions written as text (not via tool)
    # ------------------------------------------------------------------

    async def _rescue_text_questions(self, result: str, agent_name: str, step: int) -> str:
        """Detect if agent wrote questions as text instead of using ask_user_question tool.
        
        When the SDK agent fails to call the tool (e.g. too many options error,
        or low effort skipping), it writes questions as plain text. This method
        detects that pattern and asks the user directly.
        
        SKIPPED if the agent already asked questions via tool — means it knows
        how to use the tool and text questions are just rhetorical.
        """
        # If agent already asked questions via tool, skip rescue entirely
        # Check for ANY questions from this agent (answered or not)
        agent_questions = sum(
            1 for q in self.state.questions
            if q.agent == agent_name
        )
        if agent_questions > 0:
            logger.info(
                f"Skipping text question rescue for {agent_name}: "
                f"{agent_questions} tool questions already exist"
            )
            return result
        
        # Check if the last ~500 chars of output contain a question
        tail = result[-800:] if len(result) > 800 else result
        
        # Heuristic: output ends with a question (contains "?" near the end)
        lines = tail.strip().split("\n")
        question_lines = [l.strip() for l in lines[-10:] if "?" in l and len(l.strip()) > 10]
        
        if not question_lines:
            return result  # No text questions detected
        
        # Filter out rhetorical/continuation questions
        skip_patterns = [
            "готов", "передать", "передавать", "следующ", "продолж",
            "ещё", "еще", "ясно", "понятно", "okay", "ok?",
        ]
        real_questions = []
        for qline in question_lines:
            clean = qline.lstrip("#-*>0123456789.) ").strip()
            if not clean or len(clean) < 10:
                continue
            lower = clean.lower()
            if any(p in lower for p in skip_patterns):
                continue  # Skip rhetorical
            real_questions.append(clean)
        
        if not real_questions:
            return result
        
        # Agent wrote questions as text! Ask user directly
        await self._emit_message(
            "system", step,
            f"⚠️ {agent_name} wrote questions as text (tool not used). Asking you directly..."
        )
        
        for clean in real_questions:
            answer = await self._question_callback({
                "question": clean,
                "context": f"(rescued from {agent_name} text output)",
                "options": [],
                "blocking": True,
            })
            
            # Append Q&A to result so next agent sees it
            result += f"\n\n**User answered:** {clean}\n→ {answer}"
        
        return result

    # ------------------------------------------------------------------
    # Question answering
    # ------------------------------------------------------------------

    async def answer_question(self, question_id: str, answer: str) -> None:
        """Called by API when user answers a question."""
        self._question_answers[question_id] = answer
        if question_id in self._question_events:
            self._question_events[question_id].set()

        # Update state
        for q in self.state.questions:
            if q.question_id == question_id:
                q.answer = answer
                from datetime import datetime, timezone
                q.answered_at = datetime.now(timezone.utc)
                break
        self._save()

    async def _question_callback(self, question_data: dict) -> str:
        """Called by the ask_user_question tool when a subagent needs user input."""
        q = UserQuestion(
            agent=self.state.current_agent,
            step=self.state.current_step,
            question=question_data["question"],
            context=question_data.get("context", ""),
            options=question_data.get("options", []),
            blocking=question_data.get("blocking", True),
        )
        self.state.questions.append(q)
        self.state.status = SessionStatus.WAITING_FOR_USER
        self._save()

        # Emit to UI
        if self._on_question:
            await self._on_question({
                "question_id": q.question_id,
                "agent": q.agent,
                "step": q.step,
                "question": q.question,
                "context": q.context,
                "options": q.options,
            })

        if not q.blocking:
            return "(non-blocking — user may respond later)"

        # Wait for answer — poll with asyncio.sleep to keep event loop alive.
        # Blocking event.wait() would deadlock in Web mode (FastAPI main thread
        # needs the event loop to process answer_question HTTP requests).
        event = threading.Event()
        self._question_events[q.question_id] = event
        logger.info(f"Waiting for answer to question {q.question_id} (async polling)")

        timeout = 1800  # 30 minutes
        deadline = asyncio.get_event_loop().time() + timeout
        while not event.is_set():
            if asyncio.get_event_loop().time() > deadline:
                break
            await asyncio.sleep(0.5)

        if event.is_set():
            answer = self._question_answers.get(q.question_id, "")
            logger.info(f"Got answer for {q.question_id}: {answer[:50]}")
        else:
            answer = "(timed out — no user response)"
            logger.warning(f"Question {q.question_id} timed out after {timeout}s")

        self.state.status = SessionStatus.RUNNING
        self._save()
        return answer

    async def _ask_user_direct(self, question: str) -> str:
        """Ask a simple yes/no question to the user."""
        return await self._question_callback({
            "question": question,
            "context": "",
            "options": ["yes", "no"],
            "blocking": True,
        })

    # ------------------------------------------------------------------
    # Subagent execution via Claude Agent SDK
    # ------------------------------------------------------------------

    async def _run_subagent(self, name: str, prompt: str, override_tools: str | None = None) -> str:
        """Launch a scoped subagent via Claude Agent SDK query() API.

        On Windows + Python 3.10, asyncio.create_subprocess_exec() requires
        a ProactorEventLoop, but uvicorn uses a different loop type.  We work
        around this by running the SDK query() in a **dedicated thread** with
        its own asyncio event loop.

        Concurrency:
          - _subagent_lock (per-instance): serializes subagent calls within
            a single orchestrator (SourceAnalyst then ConsistencyChecker, etc.)
          - _cli_lock (module-level): ensures only ONE claude.exe process runs
            at a time across ALL sessions and orchestrators.
        """
        # Per-instance lock: serialize subagent calls within this orchestrator
        async with self._subagent_lock:
            # override_tools: use different agent def for tool permissions
            agent_def = ALL_SUBAGENTS[override_tools or name]

            # Load system prompt from skills/*.md file + inline references
            system_parts = [load_system_prompt(agent_def)]
            for ref_name in agent_def.get("references", []):
                ref_path = SKILL_ROOT / "references" / ref_name
                if ref_path.exists():
                    ref_text = ref_path.read_text(encoding="utf-8")
                    system_parts.append(f"\n---\n# Reference: {ref_name}\n{ref_text}")

            system_prompt = "\n".join(system_parts)

            # Inject language instructions
            LANG_NAMES = {"ru":"Russian","en":"English","de":"German","tr":"Turkish","he":"Hebrew"}
            ui_lang = self.state.ui_language or "ru"
            sc_lang = self.state.scenario_language or "ru"
            ui_name = LANG_NAMES.get(ui_lang, ui_lang)
            sc_name = LANG_NAMES.get(sc_lang, sc_lang)
            lang_block = (
                f"\n\n---\n# LANGUAGE INSTRUCTIONS (MANDATORY)\n"
                f"You MUST follow these language rules strictly:\n"
                f"1. **ALL your communication** (messages, questions, explanations, analysis, "
                f"status updates) MUST be in **{ui_name}** ({ui_lang}). "
                f"Never respond in English unless {ui_lang}=='en'.\n"
                f"2. **All generated scenario content** (prompts, dialogues, persona descriptions, "
                f"stage definitions) MUST be in **{sc_name}** ({sc_lang}).\n"
                f"3. When reading source files, do NOT dump their raw content into chat. "
                f"Summarize key findings instead.\n"
                f"4. Keep tool-use results internal. Only share analysis and conclusions with the user.\n"
                f"\n---\n# QUESTION PROTOCOL (MANDATORY)\n"
                f"When you need ANY input, clarification, or decision from the user:\n"
                f"- You MUST use the `ask_user_question` tool. This is the ONLY way to ask questions.\n"
                f"- NEVER write questions as plain text in your response — they will be IGNORED.\n"
                f"- The tool will BLOCK and wait for the user's answer before you continue.\n"
                f"- Use the `options` parameter to list choices when applicable.\n"
                f"- Ask ONE question at a time. Wait for the answer before asking the next.\n"
                f"- CLOSING QUESTION: Before finalizing your output, ALWAYS ask:\n"
                f"  ask_user_question(question='Anything else to add or change?', options=['No, proceed', 'Yes'])\n"
                f"  Only finalize when user says 'No' / 'proceed' / 'done' / 'хватит'.\n"
                f"\n---\n# EDIT PROTOCOL (MANDATORY)\n"
                f"When you need to modify existing files:\n"
                f"- Use `find_replace_in_file` tool — this is the SIMPLEST and PREFERRED way.\n"
                f"  Parameters: path (relative, e.g. 'scenario_overlay/persona.txt'), find (exact text), replace (new text).\n"
                f"  Example: find_replace_in_file(path='scenario_overlay/persona.txt', find='Светлана Петровна', replace='Василий Иванович')\n"
                f"  Call it ONCE per replacement. Call multiple times for multiple replacements.\n"
                f"- Use `write_component` ONLY for creating NEW files (not for editing existing ones).\n"
                f"- NEVER output file content as text and ask the user to copy-paste.\n"
                f"- NEVER create bash/python scripts for the user to run.\n"
                f"- After all edits, summarize what was changed.\n"
            )
            system_prompt += lang_block

            # Create in-process MCP server with question callback
            scenario_tools = create_scenario_tools_server(
                question_callback=self._question_callback
            )

            # Build SDK options — use model/effort from session state
            workspace = Path(self.state.workspace_dir)

            # Model: empty string = None = SDK auto-select
            model = self.state.model_id if self.state.model_id else None
            # Effort: default to "high" if not set
            effort = self.state.effort if self.state.effort else "high"

            logger.info(
                f"Subagent {name}: model={model!r}, effort={effort}, "
                f"session={self.session_id}"
            )

            # Reset stop guard for this subagent
            reset_stop_guard(name)

            # Resume from previous SDK session if available (shared context)
            resume_id = self.state.sdk_session_id if self.state.sdk_session_id else None
            if resume_id:
                logger.info(f"Resuming SDK session {resume_id} for {name}")

            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                cwd=str(workspace),
                allowed_tools=agent_def.get("allowed_tools", []),
                disallowed_tools=["Write", "Edit", "Bash", "MultiEdit"],
                mcp_servers={"scenario-builder-tools": scenario_tools},
                permission_mode="acceptEdits",
                model=model,
                effort=effort,
                resume=resume_id,
                hooks={
                    "PreToolUse": [
                        HookMatcher(matcher="*", hooks=[enforce_gates, enforce_safety]),
                    ],
                    "Stop": [
                        HookMatcher(matcher="*", hooks=[stop_guard]),
                    ],
                },
                max_turns=50,
            )

            step = self.state.current_step

            # ----------------------------------------------------------
            # Run SDK query in a separate thread (Windows subprocess fix)
            # ----------------------------------------------------------
            def _run_in_thread() -> list[Any]:
                """Execute query() in a new event loop on a dedicated thread."""
                import asyncio as _asyncio
                if os.name == "nt":
                    _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(_collect_messages(prompt, options))
                finally:
                    loop.close()

            async def _collect_messages(p: str, opts: ClaudeAgentOptions) -> list[Any]:
                """Iterate over query() and collect all messages."""
                msgs: list[Any] = []
                async for msg in query(prompt=p, options=opts):
                    msgs.append(msg)
                return msgs

            try:
                # Module-level lock: only one claude.exe at a time across all sessions
                import time as _time
                async with _cli_lock:
                    logger.info(
                        f"CLI lock acquired for {name} "
                        f"(session {self.session_id}, step {step})"
                    )
                    t0 = _time.monotonic()
                    await self._emit_message(
                        "system", step,
                        f"⏳ {name} started (model={self.state.model_id or 'auto'}, "
                        f"effort={self.state.effort})..."
                    )
                    loop = asyncio.get_event_loop()
                    messages = await loop.run_in_executor(None, _run_in_thread)
                    elapsed = _time.monotonic() - t0
                    logger.info(
                        f"CLI done for {name}: {elapsed:.1f}s, "
                        f"{len(messages)} msgs (session {self.session_id})"
                    )
                    await self._emit_message(
                        "system", step,
                        f"✅ {name} finished in {elapsed:.1f}s"
                    )

                result_parts: list[str] = []
                actual_model = None
                sdk_session = None
                for msg in messages:
                    if actual_model is None and isinstance(msg, AssistantMessage):
                        actual_model = getattr(msg, 'model', None)
                    # Capture SDK session_id from ResultMessage for resume
                    if isinstance(msg, ResultMessage):
                        sid = getattr(msg, 'session_id', None)
                        if sid:
                            sdk_session = sid
                    text = self._extract_text(msg)
                    if text:
                        result_parts.append(text)
                        # Filter: skip emitting very long messages (likely raw file dumps)
                        if len(text) > 2000:
                            # Save full text to session log file
                            log_dir = Path("sessions") / self.session_id
                            log_dir.mkdir(parents=True, exist_ok=True)
                            log_filename = f"step{step}_{name}.md"
                            log_file = log_dir / log_filename
                            log_file.write_text(text, encoding="utf-8")
                            summary = text[:300] + f"\n\n... [{len(text)} chars total]"
                            await self._emit_message(
                                name, step, summary,
                                log_file=log_filename,
                                full_length=len(text),
                            )
                        else:
                            await self._emit_message(name, step, text)

                # Store SDK session ID for resume by next agent
                if sdk_session:
                    self.state.sdk_session_id = sdk_session
                    logger.info(f"Captured SDK session {sdk_session} from {name}")

                # Log and emit which model actually responded
                if actual_model:
                    logger.info(f"Subagent {name} used model: {actual_model}")
                    await self._emit_message(
                        "system", step,
                        f"🤖 {name} responded using model: {actual_model}"
                    )

                return "\n".join(result_parts)

            except Exception as e:
                error_type = type(e).__name__
                error_msg = f"Subagent {name} error ({error_type}): {e}"
                logger.exception(error_msg)
                await self._emit_message(name, step, f"ERROR: {error_msg}")
                # Re-raise so the pipeline stops (caught by run()'s except Exception)
                raise

    def _extract_text(self, msg: Any) -> str | None:
        """Extract readable text from SDK message types."""
        if isinstance(msg, AssistantMessage):
            parts = []
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
            return "\n".join(parts) if parts else None
        elif isinstance(msg, ResultMessage):
            # ResultMessage has subtype, not result attribute
            return None
        elif isinstance(msg, SystemMessage):
            # System messages (init, etc.) — skip or log
            return None
        return None

    # ------------------------------------------------------------------
    # Consistency checker
    # ------------------------------------------------------------------

    async def _maybe_consistency_check(self, step: int) -> None:
        """Ask user via gate if they want a consistency check.
        
        Uses a gate with negative ID (e.g. -1, -3) so it doesn't
        conflict with regular gates and is handled by gate_responder.
        """
        gate_id = -step  # Negative IDs for consistency gates
        gate = GateStatus(gate_id=gate_id, description=f"Run consistency check after step {step}?")
        self.state.gates[gate_id] = gate
        self.state.status = SessionStatus.WAITING_FOR_APPROVAL
        self._save()

        await self._emit_gate(gate_id, gate.description)

        event = threading.Event()
        self._gate_events[gate_id] = event

        # Poll with asyncio.sleep (30 min timeout)
        deadline = asyncio.get_event_loop().time() + 1800
        while not event.is_set():
            if asyncio.get_event_loop().time() > deadline:
                break
            await asyncio.sleep(0.5)

        approved = self._gate_decisions.get(gate_id, False)
        self.state.status = SessionStatus.RUNNING
        self._save()

        if approved:
            await self._run_consistency_check(step)
        else:
            await self._emit_message(
                "system", step,
                f"⏭️ Consistency check skipped for step {step}"
            )

    async def _run_consistency_check(self, step: int) -> None:
        """Run the ConsistencyChecker subagent after a step."""
        await self._emit_message(
            "ConsistencyChecker", step,
            f"🔍 Running consistency check after step {step}..."
        )

        context = self._build_consistency_context(step)
        result = await self._run_subagent("ConsistencyChecker", prompt=context)

        severity = self._parse_consistency_severity(result)

        report = ConsistencyReport(step=step, status=severity)
        self.state.consistency_reports[step] = report
        self._save()

        if self._on_consistency:
            await self._on_consistency({
                "step": step,
                "status": severity.value,
                "report": result,
            })

    @staticmethod
    def _parse_consistency_severity(result: str) -> ConsistencySeverity:
        """Parse the ConsistencyChecker result to determine severity.

        Uses structured line-start markers to avoid false positives from
        words like 'error' appearing in quoted text, exception names, or
        source code references.
        """
        import re

        # Check for explicit severity/status markers the checker should output
        # e.g. "SEVERITY: ERROR", "STATUS: error", "VERDICT: WARNING"
        severity_pattern = re.compile(
            r"^\s*(?:SEVERITY|STATUS|VERDICT|RESULT)\s*:\s*(ERROR|WARNING|OK|PASS|FAIL)",
            re.IGNORECASE | re.MULTILINE,
        )
        match = severity_pattern.search(result)
        if match:
            level = match.group(1).upper()
            if level in ("ERROR", "FAIL"):
                return ConsistencySeverity.ERROR
            elif level == "WARNING":
                return ConsistencySeverity.WARNING
            else:
                return ConsistencySeverity.OK

        # Fallback: check for verdict emoji at line start (not embedded in text)
        # ❌ at line start = checker's own error verdict
        # ⚠️ at line start = checker's own warning verdict
        lines = result.split("\n")
        has_error_verdict = False
        has_warning_verdict = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("❌"):
                has_error_verdict = True
            elif stripped.startswith("⚠️"):
                has_warning_verdict = True

        if has_error_verdict:
            return ConsistencySeverity.ERROR
        if has_warning_verdict:
            return ConsistencySeverity.WARNING

        return ConsistencySeverity.OK

    def _build_consistency_context(self, step: int) -> str:
        """Build the context prompt for the ConsistencyChecker."""
        parts = [f"## Consistency Check — After Step {step}\n"]

        if self.state.source_register:
            parts.append(f"### Source Register\n{self.state.source_register[:3000]}\n")

        if self.state.layer_plan:
            parts.append(f"### Layer Plan\n{self.state.layer_plan[:3000]}\n")

        # List workspace files
        workspace = Path(self.state.workspace_dir)
        if workspace.exists():
            files = list(workspace.rglob("*"))
            if files:
                file_list = "\n".join(
                    f"- {f.relative_to(workspace)}" for f in files if f.is_file()
                )
                parts.append(f"### Workspace Files\n{file_list}\n")

        # Previous consistency reports
        if self.state.consistency_reports:
            prev = "\n".join(
                f"- Step {s}: {r.status.value}"
                for s, r in sorted(self.state.consistency_reports.items())
            )
            parts.append(f"### Previous Reports\n{prev}\n")

        parts.append(
            "\nPlease read the workspace files and verify consistency. "
            "Use read_source_files and list_workspace tools to inspect the actual file contents. "
            "Report your findings in the structured format described in your system prompt."
        )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_source_prompt(self, user_message: str) -> str:
        files_text = "\n".join(f"- {f}" for f in self.state.source_files) if self.state.source_files else "(no files specified)"
        ws = self.state.workspace_dir
        return (
            f"## User Request\n\n\"{user_message}\"\n\n"
            f"## Workspace\n\n{ws}\n\n"
            f"## Source files to read\n{files_text}\n\n"
            f"## Instructions\n\n"
            f"1. Read ALL source files using `read_source_files` tool\n"
            f"2. Summarize what you found (key facts, structure)\n"
            f"3. Clarify any missing data using `ask_user_question`\n"
            f"4. End with a brief summary of key facts\n\n"
            f"The next agent will continue in YOUR context and see everything you read.\n"
            f"DO NOT propose improvements — StructurePlanner will do that.\n"
            f"DO NOT edit any files."
        )

    def _build_structure_prompt(self) -> str:
        ws = self.state.workspace_dir
        has_resume = bool(self.state.sdk_session_id)
        if has_resume:
            # Agent resumes previous session — full context available
            return (
                f"## Role Change\n\n"
                f"You are now the **StructurePlanner**. You have full context from SourceAnalyst's work above.\n\n"
                f"## Instructions\n\n"
                f"You already have all the files and the Source Register from the previous step.\n"
                f"DO NOT re-read files unless you need to check specific text for find/replace.\n\n"
                f"Your job is to PLAN the changes, NOT execute them. ContentWriter will do the edits.\n"
                f"1. Analyze the scenario: strengths, weaknesses, gaps\n"
                f"2. Propose improvements using `present_proposal`\n"
                f"3. Discuss with user, get approval\n"
                f"4. Create a detailed edit plan with find/replace pairs using `present_proposal`\n"
                f"5. DO NOT edit files yourself. DO NOT use write_component or find_replace_in_file.\n"
            )
        else:
            # No resume — full prompt needed
            return (
                f"## Context\n\n"
                f"### User's Original Task\n{self.state.source_register}\n\n"
                f"### Source Register (from SourceAnalyst)\n{self.state.source_register}\n\n"
                f"### Workspace\n{ws}\n\n"
                f"## Instructions\n\n"
                f"Your job is to PLAN the changes, NOT execute them. ContentWriter will do the edits.\n"
                f"1. Use `list_workspace` to see the file structure\n"
                f"2. Use `read_source_files` to read files and identify what needs changing\n"
                f"3. Produce a DETAILED PLAN listing:\n"
                f"   - Each file that needs editing (relative path)\n"
                f"   - Exact find/replace pairs for each file\n"
                f"4. DO NOT edit files yourself. DO NOT use write_component or find_replace_in_file.\n"
                f"5. End with a complete replacement table.\n"
            )

    def _build_content_prompt(self) -> str:
        ws = self.state.workspace_dir
        return (
            f"## Context\n\n"
            f"### User's Original Task\n{self.state.source_register}\n\n"
            f"### Source Register\n{self.state.source_register}\n\n"
            f"### Edit Plan (from StructurePlanner)\n{self.state.layer_plan}\n\n"
            f"### Workspace\n{ws}\n\n"
            f"## Instructions\n\n"
            f"Execute ALL replacements from the Edit Plan above.\n"
            f"For each find/replace pair in the plan, call:\n"
            f"  find_replace_in_file(path='file_path', find='old text', replace='new text')\n\n"
            f"Steps:\n"
            f"1. Go through the Edit Plan line by line\n"
            f"2. Call `find_replace_in_file` for EVERY replacement listed\n"
            f"3. After all edits, read modified files to verify changes\n"
            f"4. Summarize: which files changed, how many replacements per file\n\n"
            f"CRITICAL: Execute the plan NOW using `find_replace_in_file`. "
            f"Do NOT ask questions. Do NOT output text for copy-paste. Just do the replacements."
        )

    def _build_qa_prompt(self) -> str:
        """QA discovery prompt — READ-ONLY, no write tools available."""
        ws = self.state.workspace_dir
        return (
            f"## Context\n\n"
            f"### Source Register\n{self.state.source_register}\n\n"
            f"### Workspace\n{ws}\n\n"
            f"## Instructions\n\n"
            f"Run full QA on the scenario at {ws}:\n"
            f"1. Use `validate_scenario` tool for deterministic checks\n"
            f"2. Use `read_source_files` to manually verify files\n"
            f"3. Check for consistency issues, stale names, gender mismatches\n"
            f"4. Report ALL findings with concrete fix proposals\n\n"
            f"**IMPORTANT**: You are in DISCOVERY mode. You do NOT have write tools.\n"
            f"Report your findings — the user will review them and approve fixes in the next step.\n"
            f"Use `present_proposal` to show a structured QA report.\n"
            f"DO NOT attempt to fix anything — just report what you found.\n"
            f"Verdict: PASS (no issues) / FAIL (issues found, listed above)."
        )

    def _build_qa_fix_prompt(self) -> str:
        """QA fix prompt — applies fixes approved by user."""
        ws = self.state.workspace_dir
        return (
            f"## Context\n\n"
            f"### QA Findings (from previous discovery pass)\n{self.state.qa_result}\n\n"
            f"### Workspace\n{ws}\n\n"
            f"## Instructions\n\n"
            f"The user has reviewed and approved the QA findings above.\n"
            f"Apply ALL proposed fixes:\n"
            f"1. Use `find_replace_in_file` for each fix\n"
            f"2. After all fixes, run `assemble_prompt` to rebuild effective_prompt.md\n"
            f"3. Run `validate_scenario` to confirm fixes worked\n"
            f"4. Summarize: what was fixed, final verdict\n\n"
            f"CRITICAL: Apply the fixes NOW. Do NOT ask questions. Do NOT re-analyze.\n"
            f"Just fix what was approved."
        )

    def _build_test_prompt(self) -> str:
        return (
            f"## Context\n\n"
            f"### QA Result\n{self.state.qa_result[:1000]}\n\n"
            f"### Workspace\n{self.state.workspace_dir}\n\n"
            f"## Instructions\n\n"
            f"Plan and run tests. Ask me to confirm ALL test parameters before executing. "
            f"Then do a retrospective."
        )

    def _build_retrospective_prompt(self) -> str:
        return (
            f"## Context\n\n"
            f"Testing was skipped by user choice.\n\n"
            f"### QA Result\n{self.state.qa_result[:1000]}\n\n"
            f"## Instructions\n\n"
            f"Do a mini-retrospective: process issues, accepted residuals, recommendations."
        )

    # ------------------------------------------------------------------
    # Event emitters
    # ------------------------------------------------------------------

    async def _emit_message(self, agent: str, step: int, text: str, **kwargs) -> None:
        if self._on_message:
            data = {"agent": agent, "step": step, "text": text}
            data.update(kwargs)  # log_file, full_length, etc.
            await self._on_message(data)

    async def _emit_gate(self, gate_id: int, description: str) -> None:
        if self._on_gate:
            await self._on_gate({
                "gate_id": gate_id,
                "description": description,
                "status": "pending",
            })

    async def _emit_step(self, step: int, agent: str) -> None:
        self.state.current_step = step
        self.state.current_agent = agent
        self._save()
        if self._on_step_change:
            await self._on_step_change({"step": step, "agent": agent})

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        self.sm.save(self.state)


class GateRejected(Exception):
    """Raised when the user rejects a gate."""
    pass
