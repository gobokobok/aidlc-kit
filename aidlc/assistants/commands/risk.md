---
description: Show or revise the feature's risk profile and tier
argument_hint: <what changed, or empty to show the profile>
---
{{ rules_ref }}

Input from the PM: {{ args }}

1. With no input, run `aidlc risk` and explain the tier and why in plain words.
2. Otherwise work out which answers changed (run `aidlc risk-questions` for
   the options; confirm with the PM if unsure) and run `aidlc risk` with only
   the changed flags (`--data-classes`, `--autonomy`, `--audience`,
   `--regulated-decision`, `--rationale`, or `--tier T<n>` to raise it).
3. Relay the result. If the tier went up, say what is now required. If it
   went down, say it only applies once the risk reviewer approves.
