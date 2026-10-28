---
description: Write a requirement (what the system must do)
argument-hint: <what you want it to do>
---
Follow the rules in `.claude/aidlc-rules.md`.

Input from the PM: $ARGUMENTS

1. Run `aidlc status` to see the feature, and read its `discovery.md`.
2. Run `aidlc template requirement` and draft one requirement per distinct
   need, traced to the discovery brief. Keep each small and testable.
3. Save each: `aidlc requirement --title "<title>" --body-file - <<'EOF'` ... `EOF`
   (it links to the discovery brief automatically).
4. Tell the PM which requirement IDs were saved and the next step.
