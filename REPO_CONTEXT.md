# REPO.md — Deep Repository Analysis

> **Generated:** 2026-05-21 | **Repo:** `DealBooster-ai/infinity-buyer`

---

## 1. Project Identity

**INFINITY Buyer** is an AI avatar that simulates a realistic B2B/B2C buyer for sales training. The core philosophy is **"scenario without scenario"** — the avatar has no predefined script. Sellers bring their own context and the avatar adapts dynamically. Quality is measured on discovery, objection handling, and rapport — not just "sold/didn't sell."

**Author:** Vladimir Radkevich  
**Primary language:** Russian (docs), English (code, prompts)  
**License:** Not specified (private repository)

---

## 2. Architecture Overview

The system is an **LLM-vs-LLM testing loop** with three agents:

```
Seller LLM  ←─────────────→  Buyer LLM
  (simulates salesperson)      (prompt under test)
                  ↓
             Judge LLM
       (evaluates dialogue quality)
```

**Goal:** Iteratively improve buyer prompts by measuring behavior quality through automated evaluation across 39 metrics.

### Core Runtime Flow

1. `test-experiment` (bash orchestrator) loads configs and resolves paths
2. `run_test.py` simulates multi-turn dialogue (seller vs buyer via LLM API)
3. `infinity_judge.py` evaluates the dialogue with regex pre-checks + LLM scoring
4. Results saved as JSON with transcript + evaluation scores
5. `run_batch.py` orchestrates N sellers × M runs with parallel workers

### Configuration Hierarchy (lowest → highest priority)

| Layer | File | Purpose |
|---|---|---|
| Built-in defaults | `test-experiment` script | Hardcoded fallbacks |
| Global config | `test-experiment.config.yaml` | Models, timeouts |
| Scenario config | `SCENARIOS/{GROUP}/scenarios/{ID}/_config.yaml` | Version, sellers, language |
| CLI flags | `--buyer-model`, `--turns`, etc. | Runtime overrides |

---

## 3. Repository Structure

```
infinity-buyer/
├── test-experiment                    # Main bash test runner (600 lines)
├── test-experiment.config.yaml        # Global model/test defaults
├── test-seller-turn                   # Quick single-turn test wrapper
│
├── SCENARIOS/                         # Runtime scenario groups
│   ├── EXANTE/                        # English finance (3 scenarios, 3 sellers)
│   ├── ERT/                           # Russian B2B IT (2 scenarios, 3 sellers)
│   ├── iSpace/                        # Russian/English retail (2 scenarios, 5 sellers)
│   ├── Freestyle-02/                  # Historical pointer only
│   └── _archive/                      # Legacy scenarios and old sellers
│
├── config/                            # Global configs
│   ├── inf_metrics_v4.yaml            # SSOT: 39 metrics, profiles, weights (44KB)
│   ├── main_prompt_v6c.txt            # V6c buyer system prompt (EN)
│   └── main_prompt_v6c_RU.txt         # V6c buyer system prompt (RU)
│
├── scripts/                           # 33 Python files + shell scripts
│   ├── config.py                      # Centralized paths, env loader
│   ├── model_config.py                # LLM client factory (7 providers)
│   ├── models.yaml                    # SSOT: all model definitions (269 lines)
│   ├── testing/                       # Core test scripts (15 files)
│   │   ├── run_test.py                # Dialogue simulation + evaluation (1195 lines)
│   │   ├── run_batch.py               # Batch runner with parallelism (862 lines)
│   │   ├── infinity_judge.py          # Judge evaluator (1099 lines)
│   │   ├── test_seller_turn.py        # Fast single-turn test
│   │   ├── debug_judge.py             # Re-evaluate existing results
│   │   ├── debug_logger.py            # Full API exchange logging
│   │   ├── compare_results.py         # A/B comparison
│   │   ├── seller_generator.py        # Generate sellers from archetypes
│   │   ├── seller_context.py          # Seller context management
│   │   └── dify_chat.py               # Dify workflow integration
│   ├── analytics/                     # Dashboards (3 files)
│   │   ├── inf-dashboard.py           # Streamlit + Plotly web dashboard
│   │   ├── dashboard.py               # Rich TUI dashboard
│   │   └── speech_kpi_analyzer.py     # KPI analysis for S02/S03/S04
│   ├── data/                          # Data management (5 files)
│   ├── personas/                      # Persona generation (6 files)
│   └── util/                          # Utilities (2 files)
│
├── docs/                              # Methodology docs
│   ├── infinity_buyer_concept/        # Prompt engineering, evaluation, personas
│   └── freestyle_02/                  # Freestyle-02 architecture (8 docs)
│
├── .agents/                           # LLM agent guidance
│   ├── doc/                           # 10 working documents
│   └── METRICS_CONFIG.md              # Quick metrics reference
│
├── .ai-skills/                        # Canonical project skills (4 skills)
├── .claude/                           # Generated Claude Code mirror
├── REFERENCE/                         # Compiled prompts & analysis scripts
└── CLAUDE.md                          # Claude Code project guidance (258 lines)
```

---

## 4. Prompt Architecture

Two prompt architectures coexist:

### Freestyle-01 (Legacy/Archive)
- Flat `components/` folder with 7 files
- Assembly via `_manifest.yaml` → `prompt.txt`
- Only in `SCENARIOS/_archive/`

### Freestyle-02 (Active Production)
All active scenarios use this two-layer system:

```
{SCENARIO}/
├── shared_base/          # Reusable rules (speech, language, mechanics, termination)
├── scenario_overlay/     # Scenario-specific (persona, situation, rules)
├── effective_prompt.md   # Assembled runtime prompt (DO NOT edit directly)
├── _manifest.yaml        # Assembly order + provenance
├── _config.yaml          # Runtime parameters
└── welcome_message.txt   # Initial greeting
```

**Key rule:** Never edit `effective_prompt.md` directly — edit source components and reassemble.

---

## 5. Active Scenario Groups

| Group | Scenarios | Language | Sellers | Domain |
|---|---|---|---|---|
| **EXANTE** | Selin-01-EN, Claire-01-EN, Anna-01-EN | EN | 3 (standard, aggressive, mumbler) | Finance/brokerage inbound discovery |
| **ERT** | ERT-03, ERT-04 | RU | 3 (standard, mumbler, farewell-loop) | B2B IT infrastructure qualification |
| **iSpace** | IS-NB-01-RU, IS-NB-01-EN | RU/EN | 5 (standard, aggressive, challenging, farewell-loop, questioner) | Retail notebook consultation |

All groups are **dry-run verified**. Production source of truth is `pipelines-plugin-files/root/FREESTYLE-02` (read-only reference).

---

## 6. LLM Provider Ecosystem

The system supports **7 providers** via `model_config.py`:

| Provider | Key Models | Notes |
|---|---|---|
| **Skoltech Local** | `sk-qwen3-235b-local` | **Current default** — Qwen3 235B on local H200 |
| **Skoltech Public** | `sk-qwen3-235b` | Public endpoint |
| **OpenAI** | `gpt-5.3-chat-latest`, `gpt-5.4`, `gpt-4o` | Requires `OPENAI_API_KEY` |
| **Anthropic** | `claude-3-7-sonnet`, `claude-opus-4-5` | Requires `ANTHROPIC_API_KEY` |
| **Ollama** | `ollama/qwen3.6-35b`, `ollama/gemma4-26b` | Local, supports reasoning mode toggle |
| **Cerebras** | `cerebras/qwen3-235b` | Fast remote inference |
| **Azure** | `azure/gpt-4o` | Azure-hosted OpenAI |

**Current defaults:** All three roles (buyer, seller, judge) use `sk-qwen3-235b-local`.  
**Judge models** use `judge/` prefix with `temperature=0.0` and `max_tokens=6000`.

---

## 7. Evaluation Framework

### 39 Metrics in 8 Categories

| Category | Weight | Metrics | Focus |
|---|---|---|---|
| **Technical (T)** | 3.0× | T01–T05 | System leaks, meta-breaks, format violations |
| **Safety (G)** | 2.5× | G01–G02 | Off-topic handling, absurd claim rejection |
| **Realism (R)** | 2.0× | R01–R06 | Emotional dynamics, selective listening, farewell loops |
| **Resistance (E)** | 2.0× | E01–E04 | Pushback presence, coaching detection, role reversal |
| **Hallucination (H)** | 2.0× | H01–H03 | Data disclosure control, knowledge boundaries |
| **Speech (S)** | 1.5× | S01–S06 | Naturalness, echo patterns, monologue detection |
| **Freestyle (F)** | 1.5× | F01–F05 | Context neutrality, discovery questions |
| **Prompt adherence (P)** | 1.0× | P01–P08 | Role consistency, question quality, dialogue flow |

### Critical Floor
If any T01–T05 metric scores ≤ 2 → **overall score capped at 3.0**.

### Evaluation Pipeline
1. **Regex pre-checks** (free, instant) — T01, T02, T05, S04, R04
2. **LLM evaluation** — full 39-metric scoring with evidence citations
3. **Score merge** — pre-checks override LLM where auto-checked
4. **Weighted average** by category
5. **Critical floor** application

### Metric Profiles

| Profile | Use Case |
|---|---|
| `FULL` | All 39 metrics (default) |
| `CURRENT` / `ISPACE` | Russian dialogue — excludes untestable metrics |
| `ENGLISH` | English scenarios — all metrics active |

---

## 8. Testing Modes

| Mode | Time | Tokens | Use Case |
|---|---|---|---|
| **Single test** | ~2–3 min | ~100K | Quick prompt change verification |
| **Batch test** | ~15–60 min | ~1–5M | Full version validation (N sellers × M runs) |
| **Debug** | ~3–5 min | ~150K | Full API exchange logging per turn |
| **Single turn** | ~10 sec | ~15K | Iterate on specific dialogue turn |
| **Dry-run** | instant | 0 | Path validation, no LLM calls |

### Key Commands

```bash
# Single test
./test-experiment --scenario EXANTE/scenarios/Selin-01-EN --seller-type exante-standard

# Batch test (always dry-run first)
python scripts/testing/run_batch.py \
  --scenario iSpace/scenarios/IS-NB-01-RU --sellers all --runs 3 --workers 5 --dry-run

# Fast single-turn
python scripts/testing/test_seller_turn.py --scenario ispace --prompt-version vE --turn 5
```

---

## 9. Dialogue Protocol

Each turn = one API call per agent. History is embedded in system prompt (Dify-compatible format):

```
system: {buyer_prompt} + Dialog History (user/assistant alternation)
user:   {current seller message}
```

**Termination:** Buyer emits `#feedback` as a standalone turn → system ends dialogue → transcript sent to judge.

**Hard stops:** Meta-commentary detection (agent broke character), `#feedback` signal, max turns limit.

**Known issue — Stochastic Collapse:** ~10–15% of runs produce `num_turns=20, score≈3.0, all S-metrics→1`. Not a prompt issue — exclude from analysis.

---

## 10. Project Skills System

4 canonical skills in `.ai-skills/`:

| Skill | Purpose |
|---|---|
| `/test-analysis` | Analyze test results, diagnose metrics, iterate prompts |
| `/prompt-analysis-table` | Decompose prompt into analysis table |
| `/prompt-component-canonicalization` | Canonicalize to shared_base/scenario_overlay |
| `/freestyle-02-scenario-builder` | End-to-end Freestyle-02 scenario creation |

Skills are mirrored to `.claude/skills/` via `sync-agent-skills.sh/ps1`. Never edit mirrors directly.

---

## 11. Dependencies

```
openai>=1.0.0          # LLM client (OpenAI, Azure, Cerebras, Ollama via compat)
anthropic>=0.39.0      # Anthropic Claude
pyyaml>=6.0            # Metrics/config parsing
requests>=2.31.0       # HTTP (Dify API)
tqdm>=4.66.0           # Progress bars
streamlit>=1.40.0      # Web dashboard
pandas>=2.0.0          # Data analysis
plotly>=5.18.0         # Chart generation
rich>=13.0.0           # TUI dashboard
reportlab>=3.6.0       # PDF reports
```

---

## 12. Prompt Engineering Principles

Distilled lessons from V1–V8 evolution:

- **Compact > Complex** — Short prompts with metaphors outperform detailed rule sets
- **Trigger-specific rules** — Bind rules to concrete dialogue situations, not abstract prohibitions
- **Additive, not rewrite** — Add examples to existing rules rather than rewriting
- **Soft guidance** — Hard constraints compete with generation inertia and kill adjacent metrics
- **U-shaped attention** — LLMs attend more to prompt beginning and end; critical instructions go at top or bottom
- **One change at a time** — Isolate the effect of each edit

### Anti-Patterns
1. Fixed dialogue templates (kills naturalism)
2. Imbalanced or contradictory constraints
3. Hard constraints without trigger context
4. Persona conflicts with main prompt

---

## 13. Codebase Statistics

| Metric | Value |
|---|---|
| Python scripts | 33 files |
| Largest script | `run_test.py` (1195 lines, 50KB) |
| Judge module | `infinity_judge.py` (1099 lines, 46KB) |
| Batch runner | `run_batch.py` (862 lines, 32KB) |
| Metrics config | `inf_metrics_v4.yaml` (841 lines, 44KB) |
| Main orchestrator | `test-experiment` (600 lines bash) |
| Active scenarios | 7 across 3 groups |
| Active sellers | 11 total |
| Documentation files | 30+ markdown files |
| Agent docs | 10 working documents in `.agents/doc/` |

---

## 14. Data Flow Diagram

```mermaid
graph TD
    A[test-experiment] -->|loads| B[test-experiment.config.yaml]
    A -->|loads| C[SCENARIOS/{GROUP}/scenarios/{ID}/_config.yaml]
    A -->|calls| D[run_test.py]
    
    D -->|reads| E[effective_prompt.md]
    D -->|reads| F[seller prompt .txt]
    D -->|creates| G[Seller LLM Client]
    D -->|creates| H[Buyer LLM Client]
    
    G <-->|dialogue loop| H
    
    H -->|#feedback| I[Dialogue Complete]
    I -->|transcript| J[infinity_judge.py]
    
    J -->|1. regex| K[Pre-checks]
    J -->|2. LLM| L[Metric Scoring]
    K -->|merge| M[Final Scores]
    L -->|merge| M
    
    M -->|JSON| N[Result File]
    N -->|aggregate| O[run_batch.py → YAML Report]
```

---

## 15. Key Design Decisions

1. **Dify-compatible message format** — History embedded in system prompt (not multi-message), matching production deployment
2. **Group-based scenario layout** — Scenarios organized by customer group (EXANTE, ERT, iSpace), not by prompt version
3. **Seller prompts are group-local** — No global seller directory; each group owns its sellers
4. **Judge pre-checks** — Regex-based automated detection for 5 metrics (T01, T02, T05, S04, R04) runs before LLM evaluation, saving cost
5. **Critical floor mechanism** — Technical bugs (T01–T05) can cap the entire score at 3.0, preventing high scores on broken dialogues
6. **On-premise LLM default** — Skoltech Qwen3-235B on local H200 GPUs for cost-free, unlimited testing

---

## 16. File Relationships

```
models.yaml ─────→ model_config.py ─────→ run_test.py
                                    ─────→ infinity_judge.py
                                    ─────→ test_seller_turn.py

config.py ────────→ (all scripts: paths, env, defaults)

inf_metrics_v4.yaml ──→ infinity_judge.py (metric definitions + profiles)

test-experiment.config.yaml ──→ test-experiment (bash: global defaults)
_config.yaml ─────────────────→ test-experiment (bash: scenario overrides)
_manifest.yaml ───────────────→ assembly order for effective_prompt.md

run_batch.py ──→ test-experiment ──→ run_test.py ──→ infinity_judge.py
```

---

## 17. Notable Gaps & TODOs

1. **No automated tests** — No unit/integration test suite for the Python codebase
2. **English sellers for iSpace** — IS-NB-01-EN uses Russian seller prompts; needs dedicated English sellers
3. **Replay/mutation tool** — Documented in architecture but `replay_test.py` not yet implemented
4. **Batch checkpoint/resume** — Listed as future enhancement in `run_batch.py`
5. **No CI/CD** — No GitHub Actions or similar pipeline configured
6. **Metrics v4 has 39 metrics** — But YAML comments and code reference "41 metrics" inconsistently
