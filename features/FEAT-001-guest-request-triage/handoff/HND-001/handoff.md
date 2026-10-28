---
id: HND-001
type: handoff
feature: FEAT-001
title: 'Handoff: Guest request triage'
version: 1
status: approved
owner: gobokobok
parents:
  - {id: RISK-001, version: 1}
  - {id: DISC-001, version: 1}
  - {id: REQ-001, version: 1}
  - {id: REQ-002, version: 1}
  - {id: REQ-003, version: 1}
  - {id: AC-001, version: 1}
  - {id: AC-002, version: 1}
  - {id: ASSET-001, version: 1}
  - {id: EVAL-001, version: 1}
approvals:
  - {by: alexdanm-oss, version: 1, at: '2026-10-28T11:55:19Z'}
updated_at: 2026-10-28T11:54:46Z
tier: T2
---

# Handoff: Guest request triage

The package engineering picks up: the specification, the approved prompt and
risk profile, the golden set (20 cases) and the trace from each
criterion back to the discovery brief. It is frozen when built. Once reviewers
accept it, the feature is merged and tagged `FEAT-001/handoff-v1`.

Tier 2 (Medium).

## Built from
- RISK-001 v1: Risk profile (approved by alexdanm-oss)
- DISC-001 v1: Guests wait too long for a reply to simple requests (approved by alexdanm-oss)
- REQ-001 v1: Sort every guest message into one team queue (approved by alexdanm-oss)
- REQ-002 v1: Flag urgent messages (approved by alexdanm-oss)
- REQ-003 v1: Suggest only: a person confirms every message (approved by alexdanm-oss)
- AC-001 v1: Messages land in the right queue (approved by alexdanm-oss)
- AC-002 v1: Urgent messages are not missed (approved by alexdanm-oss)
- ASSET-001 v1: Guest message triage prompt (approved by alexdanm-oss)
- EVAL-001 v1: Golden set (approved by alexdanm-oss)

## In this folder
`spec.md`, `risk.md`, `assets/`, `golden.yaml`, `eval-report.md`,
`trace.json` and `manifest.json` (with a checksum of each file).
