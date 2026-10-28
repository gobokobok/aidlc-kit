---
description: Build the golden set and test the prompt against the criteria
argument_hint: <what to test, or empty to run the existing golden set>
---
{{ rules_ref }}

Input from the PM: {{ args }}

1. Run `aidlc status`, and read the feature's criteria (their thresholds), the
   asset (its prompt and output format), `discovery.md` and `risk.md`.
2. If there is no `evals/golden.yaml` yet, or the PM wants more cases, draft
   cases as a YAML list, each with `id` (G-001, G-002, ...), `input`,
   `expected` (the fields the prompt must return), `criteria` (the AC IDs it
   tests) and optional `tags`. Cover every criterion with normal cases, edge
   cases and tricky phrasings; tag cases where a wrong answer could hurt
   someone with `safety`. Around 20 cases is a good start.
   The expected answers are the PM's call: take them from the PM and the
   documents, ask when unsure, and never fill them in by running the model.
   Show the cases to the PM before saving.
3. Save them: `aidlc golden --file - <<'EOF'` ... `EOF`
4. Run `aidlc eval`. If cases have no saved answer yet, explain that a live run
   asks the model configured in aidlc.yaml and costs money, and run
   `aidlc eval --live` only once the PM agrees.
5. Relay the result per criterion in plain words, and what the failing cases
   have in common. If it fails, suggest whether to change the prompt
   (/change on the asset) or a case, and let the PM decide.
