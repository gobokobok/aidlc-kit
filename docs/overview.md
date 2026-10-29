# AIDLC Kit: delivery summary

Version 0.1.0 · MIT licence · https://github.com/gobokobok/aidlc-kit

## What it is

AIDLC Kit lets a Product Manager take an AI feature from the first idea to an
engineering-ready handoff **from the IDE, in plain language, without ever
typing a Git command**. Underneath, it adds what an AI feature needs before
engineers build it: every item versioned and owned, the right people approving
the right things, the AI's behaviour tested against agreed cases, a full audit
trail, and one gate that decides when a feature may leave for engineering.

It is a small command-line tool plus generated files. It works with whichever
AI assistant a company already uses (GitHub Copilot, Claude Code, Cursor, or
any tool that reads `AGENTS.md`), or with VS Code tasks and no assistant at all.
No model vendor is required: saved answers let CI run the tests with no key.

## The daily flow

| Who | Does | In the IDE |
|---|---|---|
| **PM** | Opens a feature and answers four risk questions | `/new-feature` |
| | Writes why, what, and how we know it is done | `/discover`, `/requirement`, `/criteria` |
| | Defines the AI's prompt and writes test cases | `/asset`, `/eval` |
| | Asks for review and sees who still must approve | `/submit`, `/reviewers`, `/status` |
| **Reviewer** | Approves or rejects, from the IDE or the GitHub page | `/approve`, `/reject` |
| **PM** | Hands the finished feature to engineering | `/handoff` |
| **Engineer** | Turns the package into a technical plan with tasks | `/decompose` |
| **Anyone** | Reads status, trace, eval results and audit history | the viewer site |

Every command ends with one or two plain sentences: what happened and what
comes next. The kit saves each change as a Git commit, opens the review
request and records approvals; the PM sees none of it.

## What it enforces

- **Risk decides who reviews.** Four questions give a tier (1 to 3). Higher
  tiers add reviewers (a risk reviewer, a data owner), stricter accuracy
  minimums, a privacy assessment and a required human check of the AI output.
- **Reviews by role, not by hope.** `aidlc.yaml` says which roles approve which
  items. The author can never approve their own work. CI confirms each approval
  with GitHub instead of trusting a file.
- **Changes are tracked.** Editing an approved item creates a new version and
  marks everything built on it stale until it is updated.
- **The AI is tested.** A reviewed golden set of cases is run against the
  prompt; each criterion has thresholds (such as "urgent messages caught 95% of
  the time, no safety case wrong"). CI replays saved answers, so results are
  free and repeatable.
- **One hard gate.** Drafts are free. Handoff requires everything approved,
  nothing out of date and the evals passing, and says exactly what is missing
  and who can fix it.
- **An audit trail** that CI only appends to, and a **read-only site** showing
  each feature's stage, tier, who approved what, the trace from idea to tasks,
  eval results and history.

## What a company needs

A GitHub repository (organisation or personal), Python 3.12, the GitHub CLI
signed in per person, and a list of who holds which role. A model API key is
needed only by whoever records new eval answers. About an hour of set-up by one
person; `aidlc init --assistant <name>` writes everything else.

## Status and maturity

Built and tested: 360+ automated tests. The whole path (feature, review,
handoff, technical plan, audit, site) has run once on real GitHub, using two
accounts held by one person, with real Claude answers for the evals. A finished
example is in `examples/guest-request-triage`.

**Not yet proven:** the chat commands in real Copilot, Claude Code or Cursor
sessions (they are generated to the tools' documented formats and tested for
content); use on Windows; a real team with several people; models other than
Claude (the OpenAI and compatible adapters are tested with fakes only).

## What it does not do

It records and enforces **process**. It does not control what data an AI can
reach, replace an AI gateway or access controls, verify that a PM's risk
answers are true (a reviewer challenges them), or act as an identity system:
roles are configuration, and approvals are only as trustworthy as the GitHub
accounts and permissions behind them. See `docs/limitations.md`.

## Where to read more

[quickstart](quickstart.md) (start in your organisation) ·
[testing guide](testing-guide.md) (run it end to end with your team) ·
[workflow](workflow.md) · [architecture](architecture.md) ·
[trade-offs](trade-offs.md) · [limitations](limitations.md) · [demo script](demo.md)
