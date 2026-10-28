---
id: ASSET-001
type: asset
feature: FEAT-001
title: Guest message triage prompt
version: 1
status: approved
owner: alice
parents:
  - {id: AC-001, version: 1}
  - {id: AC-002, version: 1}
approvals:
  - {by: priya, version: 1, at: '2026-10-28T10:31:00Z'}
  - {by: sam, version: 1, at: '2026-10-28T10:45:00Z'}
updated_at: 2026-10-28T09:56:00Z
human_review_step: Front-desk staff see the suggested queue and urgent flag next to the guest message
  and confirm or change them before it is passed on.
model: example-scripted-v1
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
The model is set in the frontmatter (`model`). The worked example's saved
answers come from a scripted stand-in, so CI needs no API key; see
docs/decisions.md for how to record real ones.

## Human review step
Front-desk staff see the suggested queue and urgent flag next to the guest
message and confirm or change them before it is passed on. Nothing reaches the
guest or dispatches anyone without that confirmation.
