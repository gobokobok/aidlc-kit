---
id: HND-001
type: handoff
feature: FEAT-001
title: 'Handoff: Guest request triage'
version: 1
status: approved
owner: alice
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
  - {by: priya, version: 1, at: '2026-10-28T11:06:00Z'}
  - {by: sam, version: 1, at: '2026-10-28T11:13:00Z'}
updated_at: 2026-10-28T10:59:00Z
tier: T2
---

# Handoff: Guest request triage

The package engineering picks up: the specification, the approved prompt and
risk profile, the golden set (20 cases) and the trace from each
criterion back to the discovery brief. It is frozen when built. Once reviewers
accept it, the feature is merged and tagged `FEAT-001/handoff-v1`.

Tier 2 (Medium).

## Built from
- RISK-001 v1: Risk profile (approved by sam)
- DISC-001 v1: Guests wait too long for a reply to simple requests (approved by dana and sam)
- REQ-001 v1: Sort every guest message into one team queue (approved by bob, priya and sam)
- REQ-002 v1: Flag urgent messages (approved by bob, priya and sam)
- REQ-003 v1: Suggest only: a person confirms every message (approved by bob, priya and sam)
- AC-001 v1: Messages land in the right queue (approved by bob, priya and sam)
- AC-002 v1: Urgent messages are not missed (approved by bob, priya and sam)
- ASSET-001 v1: Guest message triage prompt (approved by priya and sam)
- EVAL-001 v1: Golden set (approved by bob and sam)

## In this folder
`spec.md`, `risk.md`, `assets/`, `golden.yaml`, `eval-report.md`,
`trace.json` and `manifest.json` (with a checksum of each file).
