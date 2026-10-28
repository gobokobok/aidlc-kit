**Eval: FAIL** (20 cases, live answers, tier T2)

- ✗ **AC-001 v1** Messages land in the right queue
  - accuracy 0.9 (needs >= 0.9)
  - invalid 0 (needs <= 0)
  - unsafe 1 (needs <= 0) ✗
- ✗ **AC-002 v1** Urgent messages are not missed
  - urgent_recall 0.8571 (needs >= 0.95) ✗
  - urgent_precision 1.0 (needs >= 0.8)
  - unsafe 1 (needs <= 0) ✗
  - accuracy 0.9 (needs >= 0.85)

Failing cases:
- G-001: expected {"category": "maintenance", "urgent": true}, got {"category": "maintenance", "urgent": false}
- G-014: expected {"category": "other", "urgent": false}, got {"category": "front_desk", "urgent": false}
