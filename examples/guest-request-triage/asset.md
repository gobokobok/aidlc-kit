# Guest message triage prompt

## Purpose
Suggests a team queue and an urgent flag for one guest message. It serves
AC-001 (right queue, readable answers) and AC-002 (urgent messages not missed).

## System
```text
You help hotel front-desk staff by sorting guest messages. You only suggest;
a person always confirms. Never write a reply to the guest.
```

## Prompt
```text
Sort the guest message below.

Queues: housekeeping, maintenance, food_and_beverage, front_desk, other.
Mark urgent as true only for danger to a person or the building, a medical
need, a security problem, or a guest who is locked out of their room.
Answer with one JSON object and nothing else, for example:
{"category": "housekeeping", "urgent": false}

Guest message:
{{ input }}
```

## Output format
One JSON object with `category` (one of the five queues) and `urgent`
(true or false). These match the fields in the golden set.

## Model and settings
The model is set in `aidlc.yaml` (`eval.model`). Saved answers in
`evals/cache/` let CI re-run the golden set without an API key; a change to
this prompt or the model needs a new `/eval --live`.

## Human review step
Front-desk staff see the suggested queue and urgent flag next to the guest
message and confirm or change them before it is passed on. Nothing reaches the
guest or dispatches anyone without that confirmation.
