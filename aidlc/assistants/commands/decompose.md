---
description: Turn a handed-off feature into a technical plan with tasks
argument_hint: <anything the engineer wants to emphasise, or empty>
---
{{ rules_ref }}

Input from the engineer: {{ args }}

1. Run `aidlc decompose`. It starts the plan from the handoff package, with a
   starter task for every criterion.
2. Read the package in the feature's `handoff/` folder (`spec.md`,
   `assets/`, `golden.yaml`, `trace.json`) and the plan the tool created.
3. Refine the plan with the engineer: name the real components, the
   interfaces and contracts (including the output format the prompt must
   produce), the data and who can see it, and the risks. Split, add or merge
   tasks. Every task must list the criteria it satisfies; a task with none is
   flagged, so either find the criterion or ask whether the task is needed.
   Keep the yaml task list under `## Tasks` valid.
4. Save the result: `aidlc decompose --body-file - <<'EOF'` ... `EOF`
   (the whole plan, keeping the template headings).
5. Tell the engineer how many tasks there are, any task or criterion the tool
   flagged, and that /submit opens the review request for the plan.
