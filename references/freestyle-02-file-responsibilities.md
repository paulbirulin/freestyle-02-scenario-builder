# Freestyle-02 File Responsibilities

Read the project source-of-truth documents first:

- `docs/freestyle_02/architecture.md`
- `docs/freestyle_02/file-requirements.md`

Use this reference as an operational checklist while assigning content to files.

## Scenario Layer

`scenario_overlay/situation.txt`

- Scene, channel, call setup, what is known before the call, product/business context, success criteria, and possible outcomes.
- Put pre-call knowledge here, not in persona files.

`scenario_overlay/persona_background.txt`

- Stable biography and professional context.
- Long-lived experience, constraints, preferences, and history that exist outside the specific call.
- Do not include scene-specific briefing or seller-known setup text.

`scenario_overlay/persona.txt`

- Live role identity, decision logic, speech texture, what the buyer notices, how they evaluate credibility.
- Do not include technical termination protocol or explicit prompt assembly notes.

`scenario_overlay/mechanics_scenario.txt`

- Scenario-specific triggers, response tendencies, disclosure logic, objections, and progression.
- Do not encode a fixed dialogue script.

`scenario_overlay/rules_scenario.txt`

- Scene/channel/product boundaries and scenario-specific constraints.
- Do not duplicate shared-base rules.

## Shared Base

`shared_base/mechanics_core.txt`

- Generic conversation engine, realism, turn logic, information disclosure principles.
- Must be reusable across personas and products.

`shared_base/language.txt`

- Language policy, code-switching, register, clarity, and term usage.
- Keep product-specific terminology only if it is genuinely shared across the scenario family.

`shared_base/speech_and_output.txt`

- Output format, TTS readiness, no stage directions, concise speech rules.

`shared_base/rules_core.txt`

- Stable simulation boundaries and universal buyer-avatar rules.

`shared_base/termination_protocol.txt`

- End-of-dialogue and feedback protocol.
- Keep technical protocol out of persona and scenario overlay files.

## Common Placement Errors

- Pre-call knowledge duplicated in `situation.txt`, `persona_background.txt`, and `persona.txt`.
- Persona files containing scene briefing instead of durable identity.
- Scenario layer duplicating shared output hygiene.
- `rules_scenario.txt` used as a second `rules_core.txt`.
- `mechanics_scenario.txt` containing fixed turn scripts instead of response tendencies.
- `welcome_message.txt` treated as a prompt component. It is app setup text, not part of assembly.
