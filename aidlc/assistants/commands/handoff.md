---
description: Hand the approved feature to engineering as one package
---
{{ rules_ref }}

1. Run `aidlc handoff`.
2. If it lists what is in the way, explain each item in plain words and say who
   can resolve it (the tool names them). Handoff is the one hard gate, so do
   not suggest ways around it.
3. If it built a package, tell the PM what it contains (specification, prompt,
   risk profile, golden set, trace), who was asked to accept it and why, and
   that the next step is for them to approve and then run /handoff again.
4. If it merged and tagged, tell the PM the tag, and that an engineer can now
   run /decompose.
