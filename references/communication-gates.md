# Communication Gates

This workflow is intentionally gated. Stop at the listed points even when the user supplied target and baseline in the first message.

At every gate, report:

- what was read or changed;
- what is understood;
- conflicts, gaps, and assumptions;
- the proposed next step;
- which next actions will write files or modify prompt content.
- whether the next step is read-only, creates files, edits prompt components, assembles runtime artifacts, prepares seller-facing setup, runs QA, or runs real tests.

Continue only after explicit user confirmation.

When a gate is complete, do not end with a passive status only. Offer the next concrete step and ask for the specific confirmation needed to proceed.

## Gates

1. **After source inventory**
   - Confirm source register, extracted scenario essence, and open questions.
   - Do not create or edit scenario files before this confirmation, except reading source files.

2. **After preflight**
   - Confirm target directory, result type, language, channel, persona, product/context, reference sources, and prohibited sources.
   - Report target directory state:
     - missing and created, with full path;
     - exists and empty, safe to populate after confirmation;
     - exists with files, list and classify files before asking how to proceed.
   - Do not copy baseline before this confirmation.

3. **Before baseline copy**
   - Confirm selected baseline and whether the target contains valuable user files.
   - If target overlaps production/reference source, stop and ask for explicit confirmation.
   - After copying or placing files, plan or create `_manifest.yaml` while the component/shared-file layout is known.

4. **Before component edits**
   - Confirm planned overlay/shared-base changes: keep, rewrite, add, delete, and `needs-user` decisions.
   - Do not modify component files before confirmation.

5. **Before assembling runtime prompt**
   - Confirm component files are ready for mechanical assembly.
   - Confirm whether the project group expects `effective_prompt.md`, `prompt.txt`, or another runtime file.
   - Confirm `_manifest.yaml` exists or will be created from an explicitly confirmed order before assembly.

6. **Before real tests**
   - Confirm scenario, sellers, runs, workers, turns, buyer model, seller model, judge model, output location, and `--yes` usage.
   - Dry-run first when the test runner supports it.

## If A Gate Was Missed

If work was done without a required gate:

1. Stop.
2. Describe the changes already made.
3. Do not continue editing.
4. Ask whether to keep the files as a draft working copy, remove them, or continue from the current state.
