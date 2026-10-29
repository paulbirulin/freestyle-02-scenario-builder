# Welcome Message Workflow

`welcome_message.txt` is seller-facing setup text. It helps the seller understand the scene before the dialogue starts.

It is not a prompt component and must not be included in `effective_prompt.md`, `_manifest.yaml` `assembly_order`, or required prompt files.

## Hard Rule

Do not immediately write or overwrite `welcome_message.txt` with one variant. Even if the user says "create", "recreate", "update", or "make welcome_message", first prepare variants and wait for explicit selection or approval.

If a file was already written without selection, treat it as a draft, stop, show variants, and offer to replace it after the user chooses.

## Before Writing

Extract from source files:

- call initiator;
- channel and timing;
- seller-known context;
- buyer role;
- seller task;
- buyer-visible objective;
- success criteria;
- constraints the seller must respect.

Use:

- `situation.txt` for scene, pre-call context, call objectives, and success criteria;
- `persona_background.txt` and `persona.txt` for role, pain points, and decision logic;
- successful batch dialogue turns when available, especially turns 1-3.

If context is unclear or contradictory, stop and ask for clarification.

## Content Rules

- Keep it short: usually 40-80 words unless the user asks for a longer briefing.
- One compact paragraph is preferred for runtime app setup.
- Tell the seller what they know and what they are trying to do.
- Describe only the scene and facts the seller can actually observe or reasonably know before the dialogue starts.
- Do not give the seller hidden buyer history, private motives, internal doubts, future scripted reactions, or persona-only facts that the seller could not see. Convert those into a seller task instead: ask, diagnose, connect the offer to the buyer's real situation, and earn the answer in dialogue.
- Do not reveal hidden buyer-avatar internals, scripted reactions, or private evaluation mechanics.
- Do not describe the product broadly. Mention product/company only as part of the scene and seller task.
- Formulate outcome, not instructions: "understand whether cooperation fits" is better than "do not pressure close".

## Variant Presentation

When showing options:

1. Use separate sections, not narrow tables.
2. Put each variant in a code block.
3. Add a short analysis after each variant:
   - length;
   - focus;
   - strong points;
   - weak points;
   - language tone.
4. If the welcome message is in English, include a Russian meaning check under it.
5. End with a short recommendation and selection guidance.

## After Approval

Write the chosen text to `welcome_message.txt` in the scenario root unless the project layout explicitly requires another seller-facing setup location.

Record in `.agents/SCENARIO_PLAN.md`:

```text
welcome_message.txt created/updated after user selection and validated against scenario context.
```

## Pre-test Check

- The file is in the scenario root.
- It is not in prompt assembly.
- It uses the scenario language or user-requested language.
- It gives seller-known context only.
- It does not leak invisible buyer biography or private buyer state as if the seller already knows it.
- It does not leak hidden buyer reactions.
