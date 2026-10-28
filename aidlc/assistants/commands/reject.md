---
description: Reject items, saying what must change
argument_hint: <item IDs and the reason>
---
{{ rules_ref }}

The reviewer wants to reject: {{ args }}

1. Make sure you know which items and why. If the reason is vague, help the
   reviewer say what must change in one or two sentences the author can act on.
2. Run `aidlc reject <ID> [<ID> ...] --reason "<reason>"`.
3. Tell the reviewer the author will see the reason in /status (and on the
   GitHub review request, if the repository is connected).
