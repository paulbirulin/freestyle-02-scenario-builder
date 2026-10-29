# Testing And Iteration

Before testing, read project testing rules:

- `.agents/doc/TESTING_PROCESS.md`
- `.agents/doc/SCRIPTS_REFERENCE.md`

## Readiness Check

Before changing prompt content for test readiness, verify:

- `_config.yaml`;
- configured `prompt_file`;
- `sellers_dir`;
- seller manifest;
- `tests_dir`;
- `runs_dir_name`;
- write permissions for result directory.

For EXANTE-style groups, sellers may live at group level, for example `SCENARIOS/EXANTE/sellers`, and results may live under `SCENARIOS/EXANTE/tests/{scenario_id}/Runs`.

For Freestyle-02 prototype validation, `run_batch.py` also supports deterministic replay mode. Replay mode fixes seller turns from Markdown/JSON prototype files and evaluates only the buyer prompt. Use it before drawing conclusions from LLM-scripted sellers when exact prototype trajectory matters.

## User Confirmation Required

Before any real batch test, show and confirm:

- scenario;
- sellers;
- runs;
- workers;
- turns;
- buyer model;
- seller model;
- judge model;
- output location;
- whether `--yes` will be used.

Default proposal when no better project-specific setting exists:

- `--sellers all`
- `--runs 3`
- `--workers 3`
- `--buyer-model sk-qwen3-235b-local`
- `--seller-model sk-qwen3-235b-local`
- `--judge-model judge/sk-qwen3-235b-local`

Replay batch proposal when prototype dialogues exist:

- `--replay-dir /abs/path/to/Dialogs Eamples`
- `--replay-dialogs all` or comma-separated prototype stems
- `--runs 5`
- `--workers 3`
- `--buyer-model sk-qwen3-235b-local`
- `--judge-model judge/sk-qwen3-235b-local`
- `--metrics config/inf_metrics_v4.yaml`
- `--metrics-profile ISPACE`
- `--language ru`
- `--compare-prototypes`

Example:

```bash
python scripts/testing/run_batch.py \
  --scenario iSpace/scenarios/IS-ISUP-01-RU \
  --replay-dir "/Users/sergey/Library/CloudStorage/Dropbox/Obsidian/Personal/PILOT/ISPACE/iSupport-2/Dialogs Eamples" \
  --replay-dialogs all \
  --runs 5 --workers 3 \
  --buyer-model sk-qwen3-235b-local \
  --judge-model judge/sk-qwen3-235b-local \
  --metrics config/inf_metrics_v4.yaml \
  --metrics-profile ISPACE \
  --language ru \
  --compare-prototypes \
  --yes
```

## Analysis Before Edits

Do not edit prompt files during test analysis. Read batch YAML and JSON runs first, then separate:

- prompt defect;
- seller behavior;
- judge artifact;
- model instability;
- invalid test setup;
- UI/application setup issue.

For replay batch reports, read `results_by_replay`, `cross_replay_summary`, and `run_log[].replay_case`. Seller model is not used in replay mode. If `--compare-prototypes` was used, inspect `run_log[].comparison_report`; seller fidelity should be `1.000` for deterministic replay.

Use a comparison table:

```markdown
| Metric | Baseline | New | Delta | Interpretation | Action |
|---|---:|---:|---:|---|---|
```

After analysis, propose a controlled iteration plan and wait for user confirmation before editing components.
