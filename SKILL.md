---
name: freestyle-02-scenario-builder
description: Builds, adapts, validates, and prepares Freestyle-02 buyer-avatar scenarios from source materials and reference scenarios. Use when Codex needs to create or migrate a scenario with shared_base/scenario_overlay components, keep traceability, assemble effective_prompt.md, prepare welcome_message.txt, run readiness checks, or plan baseline-vs-new testing.
---

# Freestyle-02 Scenario Builder

Use this skill to create or adapt a Freestyle-02 buyer-avatar scenario from source materials and one or more reference scenarios.

Core rule: build a controlled working copy first. Treat production/reference sources as read-only unless the user explicitly asks to modify them. If the user explicitly selects a production-tree directory as the working directory, stop once, call out the risk, and proceed only after explicit confirmation; record that confirmation in the scenario/group decision log.

Keep service artifacts separate from source prompt artifacts. Store runtime assembly metadata in the scenario root (`_manifest.yaml`, `_config.yaml`, `effective_prompt.md`) and keep source prompt components plus `welcome_message.txt` in the scenario root unless the project layout explicitly says otherwise. Store traceability in the group `DECISIONS.md` or the active migration protocol.

## Scope

Use this skill for:

- creating a new Freestyle-02 scenario;
- adapting a reference/baseline scenario to a new buyer, product, channel, or language;
- splitting scenario content into `shared_base/` and `scenario_overlay/`;
- maintaining traceability through group `DECISIONS.md`, the active migration protocol, and optional scenario-local review notes;
- assembling and validating `effective_prompt.md`;
- preparing `welcome_message.txt`;
- planning testing and iteration.

Do not use this skill for:

- editing production prompt repositories by default;
- updating plugin `config.yaml` unless the user explicitly requests it;
- treating a baseline as a factual source for a new scenario.

## Required Reading

Before designing or editing layers, read the project Freestyle-02 source of truth:

- `docs/freestyle_02/architecture.md`
- `docs/freestyle_02/file-requirements.md`

Load additional references from this skill only when the workflow reaches that stage:

- `references/communication-gates.md` - required before any write operation or test run.
- `references/freestyle-02-file-responsibilities.md` - required before assigning content to files.
- `references/immersive-prompt-writing.md` - required before writing buyer-avatar prompt text.
- `references/welcome-message.md` - required when preparing seller-facing setup text.
- `references/final-qa-checklist.md` - required before handoff or testing.
- `references/testing-and-iteration.md` - required before running or analyzing tests.
- `references/known-issues.md` - required during final QA and retrospectives.

## Workflow

1. Inventory source materials.
   - Read all user-provided briefs, transcripts, existing prompts, product notes, requirements, and examples.
   - Extract language, channel, buyer role, product context, scene, decision logic, outcomes, risks, and missing data.
   - Produce a source register and stop at Gate 1.

2. Preflight the work boundaries.
   - Confirm target scenario, language, product/context, channel, persona, expected result, reference/prohibited sources, and working directory.
   - Resolve the target directory state:
     - if it does not exist, create it and report the full path;
     - if it exists and is empty, treat that as normal and report it;
     - if it contains files, inspect them, summarize what is present, classify whether they look valuable, and ask the user how to proceed before copying or overwriting.
   - Create or update the group decision log and active migration protocol; create scenario-local review notes if multiple layers are affected.
   - Stop at Gate 2.

3. Select and copy baseline.
   - Recommend which reference provides structure/style and which parts are likely reusable.
   - Do not import factual scenario details from the baseline unless source materials confirm them.
   - Copy the full baseline into the working directory only after confirmation.
   - After files are in their intended locations, plan `_manifest.yaml` creation or update while the layout is clear. Use explicit relative paths from the scenario root for shared files outside the scenario directory. Do not wait until QA to discover assembly order.
   - Stop before content edits.

4. Design layer changes.
   - Use `references/freestyle-02-file-responsibilities.md`.
   - If source material mixes persona facts, seller strategy, product claims, competitor analysis, or examples, classify items before writing: `persona fact`, `scene fact`, `buyer concern`, `seller-facing setup`, `unsupported product claim`, or `do-not-encode`.
   - Draft the planned `scenario_overlay` and `shared_base` changes.
   - Record decisions and unresolved items.
   - Stop at Gate 4 before editing component files.

5. Edit components.
   - Use `references/immersive-prompt-writing.md`.
   - Edit source components, not assembled prompt files.
   - Keep `shared_base` generic and reusable; keep scene/persona/product specifics in `scenario_overlay`.

6. Assemble `effective_prompt.md`.
   - Prefer `scripts/assemble_effective_prompt.py` when `_manifest.yaml` contains `assembly_order`.
   - If the project layout did not previously use a manifest, create `_manifest.yaml` during structure planning, infer the order from the selected baseline or project convention, then assemble from the manifest.
   - If manifest creation is impossible, assemble mechanically from the confirmed order and record the reason, order, and command/process in the active migration protocol or group decision log.

7. Prepare `welcome_message.txt` when needed.
   - Use `references/welcome-message.md`.
   - Show variants and wait for explicit user selection before writing or replacing the file.

8. Run final QA.
   - Use `references/final-qa-checklist.md` and `references/known-issues.md`.
   - Prefer `scripts/validate_freestyle02_scenario.py` for deterministic checks.
   - If a warning is accepted rather than fixed, record it as an accepted residual with the issue, reason, evidence, and whether it blocks handoff.
   - Fix component files, reassemble, and repeat QA until clean.

9. Test and iterate when requested or useful.
   - Use `references/testing-and-iteration.md`.
   - Treat testing as optional unless the user asks for it, the task explicitly includes validation by dialogue runs, or QA surfaces a behavioral risk that cannot be checked statically.
   - Before any real test, show parameters and get explicit confirmation.
   - Analyze results before editing prompts again.

10. Retrospective.
    - Summarize process issues, new checks, and candidate updates to `references/known-issues.md`.
    - After final QA, do a mini-retrospective even if no test run happened: note workflow friction, accepted residuals, and candidate skill/reference updates.
    - Do not silently expand `SKILL.md`; keep durable lessons in references.

At every stopping point, proactively offer the next concrete step and state whether it will read only, create files, modify prompt content, assemble runtime artifacts, prepare seller-facing setup, run QA, or run real tests.

## Required Artifacts

Create or maintain these in the working scenario directory:

- `_manifest.yaml` - required when the scenario uses `effective_prompt.md` assembly; create or update it after baseline/layout planning, not as a last-minute QA repair.
- `_config.yaml` - runtime config with `prompt_file`, `sellers_dir`, `tests_dir`, language and default test settings.
- `effective_prompt.md` - assembled runtime prompt when the project group uses this file.
- `welcome_message.txt` - seller setup text only after user selection or explicit approval.
- Group `DECISIONS.md` / migration protocol - traceability table of changes, sources, open questions, risks and validation notes.

If a project group has its own scenario layout, follow it. For EXANTE-style groups, the scenario directory name can be the version boundary, `effective_prompt.md` is the generated runtime buyer prompt, and an extra `prompts/{version}` level is usually unnecessary.

## Safety Rules

- Never write to production/reference sources unless explicitly asked.
- If a target directory exists and is empty, this is normal. If it contains files, inspect and report before overwriting. If it does not exist, create it only after the working-directory boundary is confirmed and report the full created path.
- Baseline names and leakage notes may appear in traceability artifacts; `effective_prompt.md`, source prompt components, and seller-facing setup must not retain old persona/company/context unless the new source confirms them.
- If scenario source data is insufficient, ask for missing data instead of filling gaps from baseline.
- Do not call the working result a production candidate unless the user explicitly asks for production publication.
- Do not run real tests without explicit confirmation of models, sellers, run count, worker count, turns, and output location.

## Definition Of Done

- Source register and open questions are documented.
- Scenario components follow Freestyle-02 file responsibilities.
- `_manifest.yaml` records the assembly order when the scenario uses `effective_prompt.md`.
- `effective_prompt.md` is assembled from components in manifest order.
- `welcome_message.txt`, if present, is concise, seller-facing, and not part of prompt assembly.
- QA checks pass or known risks are documented.
- Testing plan or results are recorded when testing is requested or needed; otherwise the handoff states that testing was intentionally skipped.
- `.ai-skills/` remains the canonical skill source; `.claude/skills/` is regenerated with the project sync script.
