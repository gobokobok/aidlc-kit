---
description: Write acceptance criteria with measurable AI thresholds
argument_hint: <requirement ID and what "done" means>
---
{{ rules_ref }}

Input from the PM: {{ args }}

1. Run `aidlc status`; read the requirement(s) concerned and the feature's
   `risk.md` (its tier sets minimum thresholds, listed under "What this tier requires").
2. Run `aidlc template criteria` and draft criteria anyone can check.
   Propose numeric thresholds (e.g. `accuracy=0.9`, `max_unsafe=0`) and explain
   them in plain words; never go below the tier minimum.
3. Save: `aidlc criteria --title "<title>" --parent REQ-xxx --threshold accuracy=0.9 --threshold max_unsafe=0 --body-file - <<'EOF'` ... `EOF`
4. Tell the PM what was saved, the thresholds, and the next step.
