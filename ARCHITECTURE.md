# Freestyle-02 Scenario Builder — Architecture

## Overview

An AI-powered scenario building system using **Claude Agent SDK** with specialized subagents, a gate-based approval pipeline, and both CLI and Web interfaces. The system transforms source materials into structured role-play training scenarios through a multi-step, human-supervised workflow.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  INTERFACES                                                         │
│  ┌──────────┐    ┌──────────────────────────────────────────────┐   │
│  │  cli.py   │    │  app.py (FastAPI)                            │   │
│  │ Terminal  │    │  REST API + SSE + Static Files               │   │
│  └────┬─────┘    └──────────────┬───────────────────────────────┘   │
│       │                         │                                    │
│       └──────────┬──────────────┘                                    │
│                  ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  ORCHESTRATOR (src/orchestrator.py)                           │   │
│  │  • Session lifecycle    • Pipeline flow (Gates 1-5)           │   │
│  │  • Subagent management  • Question/Answer exchange            │   │
│  │  • State persistence    • SSE event emission                  │   │
│  └───────┬────────────┬────────────┬────────────────────────────┘   │
│          │            │            │                                  │
│    ┌─────▼──┐   ┌─────▼─────┐  ┌──▼────────────┐                   │
│    │ HOOKS  │   │   TOOLS   │  │  SUBAGENTS    │                   │
│    │(3 types)│  │ (9 MCP)   │  │ (7 agents)    │                   │
│    └────────┘   └───────────┘  └───────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Flow

```
 User Request
      │
      ▼
┌─ Step 1-2 ──────────────────────────────────────────────────────┐
│  SourceAnalyst (READ-ONLY)                                      │
│  • Reads source files, inventories content                      │
│  • Asks clarifying questions via ask_user_question               │
│  • Output → state.source_register                               │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
                    ┌── Gate 1 ──┐
                    │  Approve?  │
                    └──────┬─────┘
                           ▼
┌─ Step 3-4 ──────────────────────────────────────────────────────┐
│  StructurePlanner (READ-ONLY)                                   │
│  • Analyzes scenario, proposes improvements                     │
│  • Uses present_proposal to show edit plan                      │
│  • Output → state.layer_plan                                    │
│  • Has RESUME mode when SDK session is available                │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
                    ┌── Gate 2 ──┐
                    │  Approve?  │
                    └──────┬─────┘
                           ▼
┌─ Step 5-7 ──────────────────────────────────────────────────────┐
│  ContentWriter (HAS WRITE TOOLS)                                │
│  • Executes edit plan: find_replace_in_file, write_component    │
│  • Assembles effective_prompt.md                                 │
│  • Writes welcome_message.txt                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
                    ┌── Gate 3 ──┐
                    │  Approve?  │
                    └──────┬─────┘
                           ▼
┌─ Step 8: QA Discovery ─────────────────────────────────────────┐
│  QAValidator (READ-ONLY — no write tools!)                      │
│  • Runs validate_scenario deterministic checks                   │
│  • Reads files, checks consistency                               │
│  • Reports findings via present_proposal                         │
│  • CANNOT modify files — same pattern as StructurePlanner        │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
                    ┌── Gate 4 ──┐
                    │  Approve?  │
                    └──────┬─────┘
                           ▼
┌─ Step 8b: QA Fix ──────────────────────────────────────────────┐
│  QAValidatorFix (HAS WRITE TOOLS — same agent, different perms) │
│  • Applies approved fixes from QA findings                       │
│  • Uses find_replace_in_file, write_component                    │
│  • Reassembles prompt, re-validates                              │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
                    ┌── Gate 5 ──┐
                    │  Run tests?│
                    └──────┬─────┘
                           ▼
┌─ Step 9-10 ─────────────────────────────────────────────────────┐
│  TestRunner (READ-ONLY)                                         │
│  • Runs batch tests or retrospective                             │
│  • Final summary                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Between Steps

```
user_message
    ↓  _build_source_prompt()
state.source_register  ←  SourceAnalyst output
    ↓  _build_structure_prompt()
state.layer_plan  ←  StructurePlanner output (edit plan)
    ↓  _build_content_prompt()
(file edits executed)  ←  ContentWriter
    ↓  _build_qa_prompt()
state.qa_result  ←  QAValidator findings
    ↓  _build_qa_fix_prompt()
(fixes applied)  ←  QAValidatorFix
    ↓  _build_test_prompt() / _build_retrospective_prompt()
state.test_result  ←  TestRunner
    ↓
🎉 COMPLETED
```

### Between Each Step

After every subagent finishes, the orchestrator runs:

1. **`_rescue_text_questions(result, agent, step)`** — Detects if agent wrote questions as text (not via tool). Scans last 800 chars for '?'. Skipped if agent already used `ask_user_question`. Filters rhetorical questions ("готов", "передать", "следующ", etc.).
2. **`_wait_pending_questions()`** — Blocks pipeline until ALL questions from this agent are answered. Polls every 0.5s, timeout 30 min.
3. **`_maybe_consistency_check(step)`** — Optional (user-controlled via gate with negative ID). Runs ConsistencyChecker subagent with workspace context. Parses severity from structured markers.

---

## Module Reference

### Entry Points

| File | Role | Description |
|------|------|-------------|
| `app.py` | Web Server | FastAPI — REST API, SSE streaming, static file serving. Port 8765. |
| `cli.py` | Terminal UI | Interactive CLI — same orchestrator, no web server |

### Core (`src/`)

| File | Role | Description |
|------|------|-------------|
| `orchestrator.py` | **Pipeline Engine** | Manages the full 10-step pipeline. Launches subagents via Claude Agent SDK `query()`. Handles gates, questions, state, SSE events. ~1100 lines. |
| `utils.py` | Shared Utils | Scenario discovery (`find_scenarios`), fork/clone (`fork_scenario`), source file collection. Used by both CLI and Web. |

### State (`src/state/`)

| File | Role |
|------|------|
| `models.py` | Pydantic models: `SessionState` (18 fields), `GateStatus`, `UserQuestion`, `ConsistencyReport`, `SessionStatus` |
| `session.py` | `SessionManager` — file-based session persistence (JSON), in-memory cache via `_active` dict |

### Subagents (`src/subagents/`)

| File | Role |
|------|------|
| `__init__.py` | Agent definitions — maps agent names to skill files, references, and **allowed_tools** |

### Tools (`src/tools/`) — 9 MCP Tools

All tools are registered as **in-process SDK MCP servers** via `create_sdk_mcp_server()` — no subprocess overhead. The MCP server name is `scenario-builder-tools`.

| Tool | File | Description | Write? |
|------|------|-------------|--------|
| `read_source_files` | `file_tools.py` | Read workspace files. Truncates at **50,000 chars**. | ❌ |
| `write_component` | `file_tools.py` | Create/update scenario files. **overwrite=True** default. Path sandboxed. Auto `mkdir -p`. | ✅ |
| `find_replace_in_file` | `file_tools.py` | Find & replace text. Counts occurrences, errors on 0 matches. | ✅ |
| `list_workspace` | `file_tools.py` | List directory contents. Shows recursive file count for dirs. | ❌ |
| `read_reference` | `file_tools.py` | Read reference docs from `references/`. Auto-appends `.md` suffix. | ❌ |
| `assemble_prompt` | `assembly_tools.py` | Build `effective_prompt.md` from manifest. Wraps script in-process. Supports `dry_run`. | ❌ |
| `validate_scenario` | `validation_tools.py` | Deterministic QA checks. Uses `DEFAULT_MARKERS + extra_forbidden`. | ❌ |
| `ask_user_question` | `question_tool.py` | Ask user a question, block until answer. Callback injected at runtime. | ❌ |
| `present_proposal` | `proposal_tool.py` | Show proposal with title + full content. Min 20 chars content. Default options: Approve/Modify/Reject. | ❌ |

#### Path Sandboxing

```
Tool called with path argument
  ├─ is_absolute? → validate directly
  ├─ is_relative? → prepend _workspace_root
  └─ resolved.startswith(_workspace_root)?
       ├─ No  → ERROR "Path outside workspace"
       └─ Yes → Execute tool

_workspace_root is set by orchestrator via set_workspace()
before each subagent run. Points to the scenario directory.
```

### Hooks (`src/hooks/`) — 3 PreToolUse/Stop Hooks

| Hook | File | Event | Description |
|------|------|-------|-------------|
| `enforce_gates` | `gate_enforcement.py` | PreToolUse | Blocks write tools until required gate is passed. Also enforces QA write lock: during QAValidator, writes blocked until agent calls `present_proposal`. |
| `enforce_safety` | `safety_hooks.py` | PreToolUse | Blocks built-in Write/Edit/Bash/MultiEdit. Forces custom MCP tools for sandboxing. Also tracks WebSearch/WebFetch/Read for progress display. |
| `stop_guard` | `stop_guard.py` | Stop | Prevents agent from finishing if it wrote questions as text. Scans last 500 chars for lines with '?' (min 15 chars). |

#### Gate Requirements

| Tool | Required Gate |
|------|---------------|
| `write_component` | Gate 2 |
| `find_replace_in_file` | Gate 2 |
| `assemble_prompt` | Gate 2 |
| `run_batch_test` | Gate 4 |

### Skills (`skills/`) — Agent Instructions

| File | Agent | Steps | Has Write Tools? |
|------|-------|-------|-------------------|
| `source-analyst.md` | SourceAnalyst | 1-2 | ❌ |
| `structure-planner.md` | StructurePlanner | 3-4 | ❌ |
| `content-writer.md` | ContentWriter | 5-7 | ✅ |
| `qa-validator.md` | QAValidator | 8 | ❌ (discovery) / ✅ (fix) |
| `test-runner.md` | TestRunner | 9-10 | ❌ |
| `consistency-checker.md` | ConsistencyChecker | — | ❌ |

### Static (`static/`)

| File | Description |
|------|-------------|
| `index.html` | SPA entry point |
| `styles.css` | Dark-themed premium UI |
| `app.js` | Frontend logic, SSE handling, gate/question UI |
| `architecture.html` | Interactive architecture documentation (11 tabs) |

---

## SDK Execution Model

### Thread Isolation

Each subagent runs via `claude-agent-sdk` which spawns `claude.exe` as a subprocess. On Windows, asyncio subprocess support requires a `ProactorEventLoop`, but uvicorn uses a different loop. The workaround: each subagent runs in a **dedicated thread** with its own event loop.

```
orchestrator.run()
  └─ _run_subagent(name, prompt, override_tools?)
       ├─ Load system prompt from skills/*.md
       ├─ Inject reference docs from references/
       ├─ Append LANGUAGE + QUESTION + EDIT protocol blocks
       ├─ Create in-process MCP server with question callback
       ├─ Build ClaudeAgentOptions:
       │    model, effort, allowed_tools, disallowed_tools,
       │    mcp_servers, hooks, permission_mode, resume, max_turns=50
       │
       ├─ Acquire _subagent_lock (per-instance)
       │  └─ Acquire _cli_lock (module-level)
       │     └─ Thread: new ProactorEventLoop
       │        └─ async for msg in query(prompt, options):
       │             collect messages
       │        └─ loop.close()
       │     ← _cli_lock released
       │  ← _subagent_lock released
       │
       ├─ Process messages:
       │    AssistantMessage → extract TextBlock → emit to SSE
       │    ResultMessage    → capture session_id for resume
       │    SystemMessage    → skip
       │
       ├─ Long messages (>2000 chars):
       │    Save to sessions/{id}/step{N}_{Agent}.md
       │    Emit truncated (300 chars) + log_file + full_length
       │
       └─ Return joined text
```

### Dual Lock System

| Lock | Scope | Purpose |
|------|-------|---------|
| `_cli_lock` | Module-level (global) | Only **one** `claude.exe` process at a time across ALL sessions |
| `_subagent_lock` | Per-instance | Serializes subagent calls within a single orchestrator |

### ClaudeAgentOptions

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `system_prompt` | skill .md + refs + lang block | Agent instructions |
| `cwd` | workspace directory | Working dir for claude.exe |
| `allowed_tools` | per-agent list | Physical tool access control |
| `disallowed_tools` | ["Write","Edit","Bash","MultiEdit"] | Block built-in write tools |
| `mcp_servers` | {"scenario-builder-tools": server} | Custom tool server |
| `permission_mode` | "acceptEdits" | Auto-accept tool calls |
| `model` | from session state (or None) | sonnet / haiku / auto |
| `effort` | low / medium / high / xhigh / max | Thinking budget |
| `resume` | previous session_id | Context sharing between agents |
| `max_turns` | 50 | Prevent infinite loops |

### Language Injection

System prompt enriched with ~30 lines of mandatory protocol:
- **LANGUAGE**: UI language + scenario content language
- **QUESTION PROTOCOL**: Must use tool, one at a time, closing question
- **EDIT PROTOCOL**: find_replace preferred, write_component for new files

Supported languages: 🇷🇺 ru, 🇺🇸 en, 🇩🇪 de, 🇹🇷 tr, 🇮🇱 he

---

## Enforcement Model

### Principle: Behavior via Tools & Permissions, NOT Prompts

The system enforces constraints **programmatically**, never relying on prompt instructions alone.

### 4-Layer Enforcement

```
Agent calls tool
  │
  ├─ Layer 1: Is it in allowed_tools?  ── No ──→  SDK BLOCKS (tool invisible)
  │                               Yes
  ├─ Layer 2: enforce_safety: Built-in Write/Edit/Bash?  ── Yes ──→  DENIED
  │                                                  No
  ├─ Layer 3: enforce_gates: Required gate passed?  ── No ──→  DENIED
  │                                           Yes
  ├─ Layer 3b: enforce_gates: QA write lock active?  ── Yes + write tool ──→  DENIED
  │                                           No
  └─ Tool executes normally ✅

Agent tries to stop
  │
  └─ Layer 4: stop_guard: Questions as text?  ── Yes ──→  BLOCKED (must use tool)
                                       No
                                       └─ Agent stops ✅
```

### Gate System

| Gate | What it Approves | What it Unlocks |
|------|------------------|-----------------|
| 1 | SourceAnalyst results | StructurePlanner |
| 2 | Edit plan | write_component, find_replace_in_file |
| 3 | ContentWriter output | QA phase |
| 4 | QA findings | QA fix phase (write tools) |
| 5 | Test execution | TestRunner |

---

## Question & Proposal Lifecycle

### ask_user_question — Full Flow

```
Agent calls ask_user_question(question="...", options=[...], blocking=True)
  │
  ├─ question_tool.py → callback = injected _question_callback
  │
  └─ orchestrator._question_callback()
       ├─ Create UserQuestion object (uuid[:8], agent, step, question, options)
       ├─ Append to state.questions[]
       ├─ Set status → WAITING_FOR_USER
       ├─ Save state to JSON
       ├─ Emit SSE "question" event to frontend
       │
       ├─ if not blocking → return "(non-blocking)" immediately
       │
       ├─ Create threading.Event()
       ├─ Register in _question_events[qid]
       └─ POLL: while not event.is_set():
            await asyncio.sleep(0.5)   ← keeps event loop alive
            timeout: 30 minutes
                 │
                 │  ← User answers in browser
                 │     POST /api/questions/{sid}/{qid} {answer}
                 │     → orchestrator.answer_question(qid, answer)
                 │       → _question_answers[qid] = answer
                 │       → _question_events[qid].set()  ← unblocks poll
                 │
                 └─ Return answer to tool → tool returns to agent
                    → Agent continues
```

### present_proposal

Agent provides `title` + `content` (min 20 chars). Content is formatted as `📋 **{title}**\n\n{content}` and sent through the same `_question_callback` pipeline. Default options: Approve / Modify / Reject.

### Rescue Mechanism — _rescue_text_questions

```
After each subagent finishes → _rescue_text_questions(result, agent, step)
  ├─ Agent already has tool questions?  → SKIP
  ├─ Scan last 800 chars for lines with '?'
  ├─ Filter: min 10 chars, strip markdown
  ├─ Filter: skip rhetorical ("готов", "передать", "следующ", "продолж", "okay")
  ├─ No real questions?  → RETURN original result
  └─ For each real question:
       ├─ Emit "⚠️ agent wrote questions as text" system message
       ├─ Call _question_callback() directly
       └─ Wait for user answer → append Q&A to result
```

---

## State Model (Pydantic v2)

### SessionState — 18 Fields

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `session_id` | str | uuid[:12] | Unique session identifier |
| `status` | SessionStatus | IDLE | Current pipeline state |
| `current_step` | int | 0 | Active step number |
| `current_agent` | str | "" | Active agent name |
| `model_id` | str | "" (auto) | sonnet / haiku / "" |
| `effort` | str | "high" | low / medium / high / xhigh / max |
| `ui_language` | str | "ru" | AI ↔ user communication |
| `scenario_language` | str | "ru" | Generated content language |
| `consistency_enabled` | bool | False | Run checks after steps |
| `gates` | dict[int, GateStatus] | {} | Gate decisions |
| `source_register` | str | "" | SourceAnalyst output |
| `layer_plan` | str | "" | StructurePlanner edit plan |
| `qa_result` | str | "" | QAValidator findings |
| `test_result` | str | "" | TestRunner summary |
| `consistency_reports` | dict[int, Report] | {} | Per-step reports |
| `questions` | list[UserQuestion] | [] | All Q&A history |
| `source_files` | list[str] | [] | Input file paths |
| `workspace_dir` | str | "" | Scenario directory |
| `sdk_session_id` | str | "" | Resume between agents |

### Status Transitions

```
IDLE → RUNNING → WAITING_FOR_USER (question asked)
              │         ↓ (answer received)
              │    RUNNING
              │
              ├──→ WAITING_FOR_APPROVAL (gate pending)
              │         ↓ (gate approved)
              │    RUNNING
              │         ↓ (gate rejected)
              │    PAUSED
              │
              ├──→ COMPLETED (all steps done, 🎉)
              │
              └──→ FAILED (exception in pipeline)
```

### Enums

- **SessionStatus**: `idle` · `running` · `waiting_for_user` · `waiting_for_approval` · `paused` · `completed` · `failed`
- **GateDecision**: `pending` · `approved` · `rejected`
- **ConsistencySeverity**: `ok` · `warning` · `error` — parsed via regex: `^SEVERITY|STATUS|VERDICT: ERROR|WARNING|OK`

### Persistence

- All state in `sessions/{id}/state.json`
- `SessionManager` provides CRUD with in-memory cache via `_active` dict
- Sessions survive server restarts

---

## REST API & SSE Protocol

### API Endpoints — 18+ Routes (FastAPI, port 8765)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve index.html |
| GET | `/api/scenarios` | List SCENARIOS/ tree with metadata |
| GET | `/api/models` | Available models, effort levels, languages |
| POST | `/api/sessions` | Create session (+ optional fork) |
| GET | `/api/sessions/{id}` | Full session state JSON |
| DELETE | `/api/sessions/{id}` | Delete session + workspace |
| PUT | `/api/sessions/{id}/settings` | Update model / effort / language |
| POST | `/api/sessions/{id}/upload` | Upload source file (multipart) |
| GET | `/api/stream/{id}` | SSE event stream |
| POST | `/api/sessions/{id}/message` | Start pipeline (runs in background task) |
| POST | `/api/sessions/{id}/stop` | Pause pipeline, cancel task |
| POST | `/api/gates/{id}/{gate_id}` | Approve / reject gate |
| POST | `/api/questions/{id}/{qid}` | Answer question |
| GET | `/api/sessions/{id}/logs/{f}` | Read log file (stepN_Agent.md) |
| PUT | `/api/sessions/{id}/logs/{f}` | Edit log + update orchestrator state |
| POST | `/api/sessions/{id}/save-question-log` | Save question content as log file |
| GET | `/api/sessions/{id}/files` | List workspace files |
| GET | `/api/sessions/{id}/files/{path}` | Read workspace file content |

### SSE Event Types — 8 Events

| Event | Data Fields | When |
|-------|-------------|------|
| `connected` | session_id | Initial handshake |
| `message` | agent, step, text, log_file?, full_length? | Agent output |
| `gate` | gate_id, description, status | Gate pending |
| `question` | question_id, agent, step, question, context, options | Agent asks user |
| `step_change` | step, agent | Pipeline moves to next step |
| `consistency` | step, status, report | Consistency check result |
| `completed` | status, elapsed_seconds, steps, questions, gates_* | Pipeline finished |
| `ping` | {} | Keep-alive (30s timeout) |

### Race Protection

- `_running_tasks` dict tracks active `asyncio.Task` per session. POST `/message` returns **409 Conflict** if pipeline already running.
- `_guarded_run()` wrapper: tracks elapsed time, cleans up `_running_tasks` in `finally`, pushes `completed` SSE event.
- PUT `/logs/{filename}` updates both disk file AND orchestrator state. Maps: `step1_SourceAnalyst → source_register`, `step3_StructurePlanner → layer_plan`, etc.

---

## Prompt Chain — 7 Builders

Each subagent receives a dynamically generated prompt from the orchestrator. The prompt includes context from previous steps (passed via `state.*` fields).

| Builder | Step | Inputs | Key Instructions | Inter-step |
|---------|------|--------|------------------|------------|
| `_build_source_prompt(user_message)` | 1-2 | user_message, workspace, source_files | Read ALL files, summarize, clarify. DO NOT propose. | Step 2: rescue_text_questions → wait_pending_questions → **Gate 1** |
| `_build_structure_prompt()` | 3-4 | source_register (or resume) | Two modes: RESUME (brief) / FULL (with source_register). Plan changes, DO NOT write. | Step 4: rescue_text_questions → wait_pending_questions → **Gate 2** |
| `_build_content_prompt()` | 5-7 | source_register + layer_plan | Execute ALL find/replace from edit plan. Do NOT ask questions. | Steps 6-7: save state → **Gate 3** |
| `_build_qa_prompt()` | 8 | source_register + workspace | DISCOVERY only. validate_scenario + manual check. Report via present_proposal. | rescue_text_questions → wait_pending_questions → **Gate 4** |
| `_build_qa_fix_prompt()` | 8b | qa_result + workspace | Apply ALL fixes, reassemble, re-validate. Do NOT re-analyze. | save state → **Gate 5** |
| `_build_test_prompt()` | 9-10 | qa_result (1000 chars) | Plan tests, confirm parameters. | Step 10: save state → COMPLETED 🎉 |
| `_build_retrospective_prompt()` | 9-10 (skip) | qa_result | Testing skipped → mini post-mortem. | Step 10: save state → COMPLETED 🎉 |

---

## Key Design Decisions

1. **Two-pass QA**: Discovery (read-only) → Gate → Fix (with writes). Same pattern as StructurePlanner → ContentWriter. The SDK's `allowed_tools` list physically prevents writes during discovery.

2. **Hooks don't cover MCP tools**: SDK PreToolUse hooks fire only for built-in tools (Read, Write, Edit, Bash). MCP tool enforcement is via `allowed_tools` in `ClaudeAgentOptions`.

3. **Questions via tools, not text**: `stop_guard` hook + `_rescue_text_questions` ensure agents use the `ask_user_question` tool, enabling proper UI integration.

4. **State persistence**: All state saved as JSON in `sessions/{session_id}/state.json`. Sessions survive server restarts.

5. **Thread isolation**: Each subagent runs in a dedicated thread with its own asyncio event loop (Windows ProactorEventLoop workaround).

6. **Dual lock system**: `_cli_lock` (module-level) ensures only one `claude.exe` runs at any time. `_subagent_lock` (per-instance) serializes within an orchestrator.

7. **Session resume**: SDK session ID captured from `ResultMessage` and passed to next agent via `resume`, enabling StructurePlanner to see SourceAnalyst's full context.

8. **QA write lock**: During QAValidator, the `enforce_gates` hook blocks writes until the agent presents findings via `present_proposal`. Unlock happens in `_question_callback`, not in the hook.

---

## File Tree

```
freestyle-02-scenario-builder/
├── app.py                    # FastAPI web server (689 lines)
├── cli.py                    # Terminal CLI
├── SKILL.md                  # Original workflow specification
├── ARCHITECTURE.md           # This file
├── requirements.txt          # Python dependencies (pinned)
├── pyproject.toml            # Project metadata
│
├── skills/                   # Agent instruction files (.md)
│   ├── source-analyst.md
│   ├── structure-planner.md
│   ├── content-writer.md
│   ├── qa-validator.md
│   ├── test-runner.md
│   └── consistency-checker.md
│
├── references/               # Reference docs loaded by agents
│   ├── freestyle-02-file-responsibilities.md
│   ├── communication-gates.md
│   ├── immersive-prompt-writing.md
│   ├── welcome-message.md
│   ├── final-qa-checklist.md
│   ├── known-issues.md
│   └── testing-and-iteration.md
│
├── scripts/                  # Assembly & validation scripts
│   ├── assemble_effective_prompt.py
│   └── validate_freestyle02_scenario.py
│
├── src/
│   ├── orchestrator.py       # Pipeline engine (1097 lines)
│   ├── utils.py              # Shared utilities (146 lines)
│   ├── hooks/
│   │   ├── gate_enforcement.py  # Gate checks + QA write lock (100 lines)
│   │   ├── safety_hooks.py      # Block built-in tools (53 lines)
│   │   └── stop_guard.py        # Force question tool usage (87 lines)
│   ├── subagents/
│   │   └── __init__.py          # 7 agent defs & tool permissions (179 lines)
│   ├── state/
│   │   ├── models.py            # Pydantic state models (176 lines)
│   │   └── session.py           # File-based persistence (123 lines)
│   └── tools/
│       ├── __init__.py          # MCP server factory (50 lines)
│       ├── file_tools.py        # read/write/list/replace (179 lines)
│       ├── assembly_tools.py    # assemble_prompt (42 lines)
│       ├── validation_tools.py  # validate_scenario (41 lines)
│       ├── question_tool.py     # ask_user_question (60 lines)
│       └── proposal_tool.py     # present_proposal (81 lines)
│
├── static/                   # Web UI
│   ├── index.html            # SPA entry point
│   ├── styles.css            # Dark-themed premium UI
│   ├── app.js                # Frontend logic, SSE, gate/question UI
│   └── architecture.html     # Interactive architecture docs (11 tabs)
│
├── SCENARIOS/                # Scenario repository (ERT-*, etc.)
└── sessions/                 # Persisted state (JSON + log files)
    └── {session_id}/
        ├── state.json           # SessionState snapshot
        ├── workspace/           # Generated/edited files
        ├── step1_SourceAnalyst.md  # Long agent output
        └── step3_StructurePlanner.md
```
