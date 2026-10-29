# Known Issues

Use this list during final QA and retrospective. Add durable new issue classes here, not in `SKILL.md`.

## Previously Observed Problems

- Runtime prompt retained source/review comments such as `COMPONENT:` or `SOURCE:`.
- Scenario layer retained baseline/meta-comparisons instead of direct instructions for the current persona.
- Runtime text used the word `baseline` where an ordinary term such as `starting objection` or `reference point` was intended.
- `welcome_message.txt` was written as one option without user selection.
- Welcome-message variants were shown without a Russian meaning check when the user needed one.
- Old `welcome_message.txt` or copied baseline text remained after overlay rewrite.
- `welcome_message.txt` was treated as a prompt component, though it is an app setup artifact.
- `effective_prompt.md` was not reassembled after component edits.
- Generated `effective_prompt.md` was left in the scenario root instead of `effective_prompt.md`.
- Traceability files were missing or did not reflect final state.
- Old buyer names, providers, competitors, channel, or call context remained from baseline.
- Target directory handling was ambiguous when the directory existed but was empty.
- Manifest creation was delayed until QA instead of planned once file layout was known.
- Service artifacts were kept in the prompt root instead of `scenario/.agents/`, causing prompt files and workflow files to mix.
- Deterministic validator warnings were left unexplained instead of recorded as accepted residuals.
- Mixed source materials were encoded directly without classifying persona facts, scene facts, buyer concerns, seller setup, unsupported product claims, and do-not-encode items.
- Baseline names in traceability artifacts were mistaken for runtime leakage.
- Agent ended a gate without proposing the next concrete step and the confirmation needed.
- Testing was treated as mandatory even when the requested deliverable was a validated draft scenario.

## Update Rule

When a new recurring issue is discovered:

1. Add it here as a durable issue class.
2. Add a deterministic validator check if the issue can be detected mechanically.
3. Keep `SKILL.md` compact; do not grow the controller with every lesson.
