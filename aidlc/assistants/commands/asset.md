---
description: Define the AI behaviour (prompt and configuration)
argument_hint: <what the AI should do>
---
{{ rules_ref }}

Input from the PM: {{ args }}

1. Run `aidlc status`; read the criteria and `risk.md`.
2. Run `aidlc template asset` and draft the prompt, the exact output format,
   and how the output is checked. The prompt goes in a fenced block under
   `## Prompt`, with `{{ '{{ input }}' }}` where each case's input goes, and must
   ask for one JSON object whose fields match what the criteria check. Ask the
   PM which model to use if aidlc.yaml sets none, and pass it with `--set-model`. If the tier needs a person in the loop, ask
   the PM who checks the AI output and how, and pass it as `--human-review-step`.
3. Save: `aidlc asset --title "<title>" [--parent AC-xxx ...] [--set-model <model>] [--human-review-step "<who checks what>"] --body-file - <<'EOF'` ... `EOF`
   Without `--parent` it links to every criterion in the feature.
4. Tell the PM what was saved and that the next step is /eval.
