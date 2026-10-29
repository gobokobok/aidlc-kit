# Worked example: FEAT-001 Guest request triage

A frozen copy of a real run of the kit, kept here so the tests, the docs and
the viewer site have something real to read. It is laid out like an adopting
repository (`aidlc.yaml`, `features/`, `audit/`), so you can point the kit at it:

```bash
aidlc --root examples/guest-request-triage status
aidlc --root examples/guest-request-triage validate
aidlc --root examples/guest-request-triage site build --out /tmp/site
```

- `features/FEAT-001-guest-request-triage/`: the feature: risk profile,
  discovery, requirements, criteria, prompt, golden set with saved Claude
  answers, handoff package and technical plan.
- `audit/log.jsonl`: what CI recorded when the pull requests merged.
- `drafts/`: the plain-language drafts a PM typed in, for reuse.
- The commit and pull-request numbers in the audit log and manifest refer to
  the run's original repository, `gobokobok/aidlc-kit` (pull requests 1 and 2).

Two GitHub accounts belonging to one person played every role, so this shows
the mechanism, not independent review.
