# Immersive Prompt Writing

Write buyer-avatar prompts to create live behavior, not checklist execution.

## Main Pattern

Describe behavioral intent, inner logic, motivation, pressure, and decision process. Avoid mandatory opening lines unless a literal example is required.

Weak:

- "At the start, say that the call was agreed."
- "Respond to the greeting with this exact sentence."
- "Show skepticism and ask about fees."

Better:

- "At the start, behave like someone who expected the call but does not want to waste time on formality."
- "Briefly acknowledge contact and move the conversation toward the practical reason for the call."
- "When claims sound too polished, bring the conversation back to practical trade-offs."

## Avoid Robotic Speech

- Write motivation, pressure, context, and decision logic instead of literal scripts.
- Prefer "how this person naturally reacts" over "what to say".
- Use examples only as optional variation, not required utterances.
- Give positive replacements after prohibitions.
- Avoid internal service language inside runtime persona text: "confirm context", "state status", "declare that the call was scheduled".
- Check each instruction: would a living person behave this way, or is this a service instruction for a robot?

## Goals Instead Of State Control

Do not control the persona through direct emotional states such as "be warmer", "be irritated", or "be skeptical". Describe the information goal or practical result that causes the behavior.

Weak:

```text
Become warmer when the seller is concise and recognizes your constraints.
```

Better:

```text
When the seller gives concrete information that helps you understand whether the offer applies to your situation, you naturally open up and go deeper. You ask because you are trying to decide, not because you are testing the seller.
```

This keeps behavior grounded in the dialogue content instead of turning emotion into a script.

## Where It Matters Most

- `persona.txt` - live identity, speech texture, decision logic, natural reactions.
- `situation.txt` - scene and pressure of the moment, not a sequence of lines.
- `rules_scenario.txt` - channel and product boundaries through behavior, not canned responses.
- `mechanics_scenario.txt` - triggers and tendencies, not a fixed turn sequence.

## Practical Lesson

If a source says "the buyer can say X at the beginning", convert it into behavioral context unless the exact phrase is part of the task. Literal starter phrases often create repetitive and robotic openings.
