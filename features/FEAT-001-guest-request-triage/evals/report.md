**Eval: PASS** (20 cases, live answers, tier T2)

- ✓ **AC-001 v1** Messages land in the right queue
  - accuracy 0.95 (needs >= 0.9)
  - invalid 0 (needs <= 0)
  - unsafe 0 (needs <= 0)
- ✓ **AC-002 v1** Urgent messages are not missed
  - urgent_recall 1.0 (needs >= 0.95)
  - urgent_precision 1.0 (needs >= 0.8)
  - unsafe 0 (needs <= 0)
  - accuracy 1.0 (needs >= 0.85)

Failing cases:
- G-019: expected {"category": "front_desk", "urgent": false}, got {"category": "other", "urgent": false}
