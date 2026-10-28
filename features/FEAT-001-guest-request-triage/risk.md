---
id: RISK-001
type: risk
feature: FEAT-001
title: Risk profile
version: 1
status: approved
owner: alice
parents: []
approvals:
  - {by: sam, version: 1, at: '2026-10-28T10:45:00Z'}
updated_at: 2026-10-28T09:07:00Z
data_classes:
  - personal
autonomy: suggest
audience: customer_facing
regulated_decision: false
declared_tier: T2
rationale: Guest messages can contain names and room numbers. The AI only suggests; staff confirm.
approved_tier: T2
---

# Risk profile

This profile decides the feature's risk tier and so who must review it.
It was generated from the intake questionnaire; revise it with /risk.

## Answers and tier
- What kinds of data will the AI see? Pick all that apply. **Personal data about people (names, contact details, room numbers)**
- What will the AI do with its output? **Suggest only; a person decides and acts**
- Who sees or is affected by the result? **Customers or guests**
- Does it affect pricing, eligibility, credit or a similar decision about a person? **No**
- Computed tier: **Tier 2 (Medium)**, because it handles personal data; it is customer-facing
- Rationale: Guest messages can contain names and room numbers. The AI only suggests; staff confirm.

## What this tier requires
- Every item also needs approval from: Risk.
- Criteria must set accuracy to at least 0.85.

