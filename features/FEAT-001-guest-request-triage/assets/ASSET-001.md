---
id: ASSET-001
type: asset
feature: FEAT-001
title: Guest message triage prompt
version: 1
status: approved
owner: gobokobok
parents:
  - {id: AC-001, version: 1}
  - {id: AC-002, version: 1}
approvals:
  - {by: alexdanm-oss, version: 1, at: '2026-10-28T11:54:26Z'}
updated_at: 2026-10-28T11:42:07Z
human_review_step: Front-desk staff see the suggested queue and urgent flag next to the guest message
  and confirm or change them before it is passed on.
---

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
Use other for anything that is not a request for one of the four teams, such
as thanks, feedback, or questions about the area.
Mark urgent as true only for danger to a person or the building (water leaks,
flooding, gas, smoke, fire), a medical need, an allergic reaction, a security
problem such as a door that will not lock, or a guest locked out of their
room. A slow order, a warm room or a broken gadget is not urgent.
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
