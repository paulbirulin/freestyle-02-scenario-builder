# Final QA Checklist

Run this after component edits, prompt assembly, and welcome-message selection. If a defect is found, fix the source component, reassemble, and repeat QA.

## Runtime Files

Check at least:

- `_manifest.yaml`;
- `_config.yaml` when present;
- `effective_prompt.md` or configured runtime prompt file;
- all component files listed in manifest `assembly_order`;
- `welcome_message.txt` when present.

## Assembly

- Runtime prompt was assembled mechanically from components.
- Assembly order matches `_manifest.yaml`.
- All required components exist.
- `welcome_message.txt` is not included in assembly.
- Generated runtime prompt is under `.agents/` unless the project layout explicitly requires another location.
- Review/source comments are absent from runtime prompt.
- If the project previously had no manifest, `_manifest.yaml` was created during structure planning or before assembly, not inferred silently during final QA.

## Cross-layer Consistency

- `situation.txt` contains scene, channel, start knowledge, and outcomes.
- `persona_background.txt` contains durable background, not scene-specific briefing.
- `persona.txt` contains live identity, decision logic, and speech texture.
- `mechanics_scenario.txt` contains scenario hooks, not generic engine rules.
- `rules_scenario.txt` contains scene/channel boundaries, not shared-base rules.
- `termination_protocol` and `speech_and_output` are not duplicated in scenario layer.

## Factual Consistency

The following must be consistent across runtime files:

- buyer name;
- role;
- current provider or competitor, if any;
- channel;
- initiator of contact;
- product/context;
- next step;
- language policy.

## Artifact Hygiene

Search prompt/runtime artifacts for:

- `TODO`, `FIXME`, `draft`;
- `COMPONENT:`, `SOURCE:`;
- `copied baseline`, `do not use`;
- old buyer names, companies, providers, channels, or call context;
- meta-comparisons with baseline instead of direct runtime instruction.

Traceability files in `.agents/` may mention baseline names or leakage notes when documenting provenance, decisions, and removals; do not treat that alone as runtime leakage.

## Accepted Residuals

If a warning is not fixed, record it in `.agents/SCENARIO_PLAN.md` with:

- issue;
- why it is accepted;
- evidence or local layout precedent;
- whether it blocks handoff or testing.

## Deterministic Check

Prefer running:

```bash
python .ai-skills/freestyle-02-scenario-builder/scripts/validate_freestyle02_scenario.py <scenario-dir>
```

Use the script as a check, not as a replacement for semantic review.
