# Workflow

Commands are named the same everywhere. How you start one depends on your
assistant: type `/new-feature` in Claude Code, Cursor or Copilot Chat; ask
"start a new feature" in an assistant that reads `AGENTS.md`; or run the task
from VS Code. Each one runs the matching `aidlc` command, which ends with one
or two plain sentences saying what happened and what is next. Raw Git output
is never shown unless you ask for it (`aidlc --verbose …`).

## PM journey

| Step | Command | What you give | What you get |
|---|---|---|---|
| 0 | `/new-feature` | A name and four answers about risk | A workspace, a risk profile (RISK-001) and a tier |
| 1 | `/discover` | Notes, interviews, data | The discovery brief |
| 2 | `/requirement` | What the system must do | A requirement, linked to the brief |
| 3 | `/criteria` | How you would know it is done | Criteria with thresholds (for example accuracy 0.90) |
| 4 | `/asset` | The prompt and who checks its output | The prompt asset |
| 5 | `/eval` | Test cases (the golden set) | A report: each threshold met or not |
| 6 | `/submit` | | A review request, and a message saying who was asked and why |
| 7 | `/handoff` | | The gate, then a package, then the merge |

### 0. Open the feature and profile its risk

`/new-feature` asks what data the AI will see, what it does with its output,
who is affected and whether it decides anything regulated. The kit computes
the tier. Example: "It is Tier 2 (Medium) because it handles personal data and
it is customer-facing, so the risk reviewer will check the risk profile."
You can raise the tier; you cannot lower it. Revise the answers later with
`/risk`.

### 1 to 4. Write the chain

Each item links to the one it builds on: requirement to discovery, criteria to
requirements, prompt to criteria. You write in plain language; the kit adds
IDs, versions and links, and saves each change as one commit. Drafts are free:
nobody reviews anything yet.

### 5. Prove it

Write test cases as messages with the answer you expect, each linked to the
criteria it tests. `/eval` runs them from saved model answers; if the prompt
changed, someone runs `/eval --live` once to record new answers (it asks the
configured model and costs money, so the assistant asks you first). The report shows
each threshold against the result and lists failing cases.

### 6. Ask for a decision

`/submit` sends everything that is still a draft and opens one review request.
It tells you who was asked and why, for example: "Sent to bob (Ops) and priya
(Tech). sam (Risk) is included because this feature is Tier 2."
`/reviewers` shows at any time who still has to approve what.

### 7. Hand off

`/handoff` is the one hard gate. Everything must be approved by every required
role, nothing out of date, evals passing, and whatever the tier demands (a
privacy assessment and a human review step at Tier 3). If something is in the
way, it lists each item and who can fix it. When the gate is clear it builds
the package and asks the reviewers to accept it; run `/handoff` again once they
have, and it merges and tags the feature.

### When something changes

`/change REQ-002` edits an item. If it was already reviewed, the item becomes a
new version with no approvals, and everything built on it is marked stale until
updated. A rejected item comes back with the reviewer's reason; revise it with
`/change` and `/submit` again. `/status` always says where you are and what is
next.

## Reviewer journey

1. A review request names you: by GitHub notification, or `/reviewers` and
   `/status` in the IDE.
2. `/approve` approves everything waiting for a role you hold. Name items to
   approve only some: `/approve REQ-001`. `/reject REQ-001 --reason "…"` sends
   it back with your reason.
3. Or approve on the GitHub pull request screen. The kit records it in the
   files the next time the PM runs `/status`, `/reviewers` or `/submit`.
4. You cannot approve what you wrote. A person who holds several roles
   satisfies all of them with one approval.

At Tier 2 and 3 the risk reviewer approves everything in the feature, and is
expected to challenge the risk answers first. At Tier 3 the data owner does
too.

## Engineer journey

After the handoff is merged and tagged:

1. `/decompose` creates the branch `decompose/FEAT-001` from `main` and builds a
   technical plan (DEC-001) from the package: components, interfaces and
   contracts, data, risks, and one starter task per criterion plus a regression
   task for the golden set.
2. Refine it. Tasks live in a yaml list under `## Tasks`, and each task names
   the criteria it satisfies. A task with no criterion, or a criterion no task
   covers, is flagged (not blocked) in `/status` and in the review request, and
   a reviewer decides. An unknown criterion is an error.
3. `/submit` opens a review request from that branch. The golden set in the
   package is the regression gate for the implementation.

## Under the hood

- One branch per feature (`feat/FEAT-001`); every save is one commit, such as
  `[FEAT-001][REQ-003 v2] Tighten routing wording`, authored as you.
- Before any command the kit commits pending work and pulls with rebase. On a
  conflict it stops and explains in plain language. It never force-pushes.
- Who you are comes from your GitHub login (`gh auth login`).
