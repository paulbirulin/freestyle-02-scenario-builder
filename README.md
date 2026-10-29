# Freestyle-02 Scenario Builder — Web App

Web-based scenario builder for buyer-avatar sales training, powered by **Claude Agent SDK** via **AWS Bedrock**.

## Architecture

- **6 Subagents** with separate SKILL `.md` files (editable without touching Python)
- **ConsistencyChecker** — inter-step data integrity watchdog
- **Custom MCP Tools** — in-process SDK servers (no subprocess overhead)
- **Hooks** — `PreToolUse` gate enforcement + safety rules
- **FastAPI Backend** — SSE streaming, gate approval, Q&A endpoints
- **Premium Dark Theme UI** — chat, gates, questions, consistency reports

## Setup

### 1. Install dependencies

```bash
pip install -e .
# or
pip install claude-agent-sdk fastapi uvicorn pydantic pyyaml python-multipart python-dotenv
```

### 2. Configure AWS Bedrock credentials

Edit `.env` — choose one authentication method:

**Bearer token (simpler):**
```bash
CLAUDE_CODE_USE_BEDROCK=1
AWS_REGION=us-east-2
AWS_BEARER_TOKEN_BEDROCK=your-token-here
```

**IAM keys:**
```bash
CLAUDE_CODE_USE_BEDROCK=1
AWS_REGION=us-east-2
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
```

### 3. Start the server

```bash
python app.py
```

Open http://localhost:8765

## Editing Subagent Behavior

Each subagent's system prompt is in `skills/*.md` — edit these files to change behavior without touching Python:

```
skills/
├── source-analyst.md          ← Steps 1-2
├── structure-planner.md       ← Steps 3-4
├── content-writer.md          ← Steps 5-7
├── qa-validator.md            ← Step 8
├── test-runner.md             ← Steps 9-10
└── consistency-checker.md     ← inter-step watchdog
```

## Project Structure

```
freestyle-02-scenario-builder/
├── .env                        ← AWS credentials (gitignored)
├── app.py                      ← FastAPI entry point
├── pyproject.toml              ← Project config
├── src/
│   ├── orchestrator.py         ← Main workflow state machine (uses ClaudeSDKClient)
│   ├── subagents/              ← Subagent definitions + skill file loading
│   ├── tools/                  ← Custom MCP tools (@tool + create_sdk_mcp_server)
│   ├── hooks/                  ← PreToolUse hooks (gate + safety enforcement)
│   └── state/                  ← Pydantic models + JSON session persistence
├── skills/                     ← SKILL .md files for each subagent
├── references/                 ← Existing reference docs (read-only)
├── scripts/                    ← Existing scripts (assemble, validate)
└── static/                     ← Frontend HTML/CSS/JS
```
