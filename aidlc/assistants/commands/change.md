---
description: Edit an artifact; reviewed items get a new version and downstream items go stale
argument_hint: <artifact ID and what to change>
---
{{ rules_ref }}

Input from the PM: {{ args }}

1. Find the artifact (`aidlc status`) and read its file.
2. Draft the edited text, keeping the template headings. Show the PM the
   change if it is more than a small fix.
3. Save: `aidlc change <ID> [--title "..."] [--threshold name=value] [--human-review-step "..."] --summary "<what changed>" --body-file - <<'EOF'` ... `EOF`
   To bring a stale item up to date with no text change, run `aidlc change <ID>`.
   For the risk profile use /risk instead.
4. Say the new version and which items are now out of date.
