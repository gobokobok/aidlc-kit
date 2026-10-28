---
description: Write the discovery brief (why we are doing this)
argument-hint: <notes, interview findings, data, or a file path>
---
Follow the rules in `.claude/aidlc-rules.md`.

Input from the PM: $ARGUMENTS

1. Read what the PM gave you (and any files they point to).
2. Run `aidlc template discovery` and draft the brief under those headings in
   plain language. Only use facts from the input; list gaps as open questions.
3. Save it: `aidlc discover --title "<one-line title>" --body-file - <<'EOF'` ... `EOF`
   If a discovery brief already exists, the same command updates it.
4. Summarise the brief in two sentences and say the next step.
