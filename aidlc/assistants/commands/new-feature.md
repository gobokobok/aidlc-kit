---
description: Open a new feature workspace and profile its risk
argument_hint: <feature name>
---
{{ rules_ref }}

The PM wants to start a feature: {{ args }}

1. If no name was given, ask for a short one.
2. Run `aidlc risk-questions --json` and ask the PM each question in plain
   language, one message with all four questions, offering the options as a
   short list. Then ask for one sentence on why the answers fit (rationale).
   Do not guess answers; if something is unclear, ask.
3. Run:
   `aidlc new-feature --title "<name>" --data-classes <a,b> --autonomy <value> --audience <value> --regulated-decision <yes|no> --rationale "<sentence>"`
   Add `--tier T<n>` only if the PM explicitly wants a higher tier than computed.
4. Tell the PM the feature ID, the tier and why, who checks the risk profile,
   and that the next step is /discover.
