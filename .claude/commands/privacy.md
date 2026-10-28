---
description: Write the privacy assessment (required at higher risk tiers)
argument-hint: <what data the feature uses and how>
---
Follow the rules in `.claude/aidlc-rules.md`.

Input from the PM: $ARGUMENTS

1. Read `risk.md` and `discovery.md` for the feature.
2. Run `aidlc template privacy` and draft each section from the input. Mark
   anything you do not know as a question for the data owner; do not invent.
3. Save: `aidlc privacy --title "Privacy assessment" --body-file - <<'EOF'` ... `EOF`
4. Tell the PM it was saved and that the data owner and risk reviewer will check it.
