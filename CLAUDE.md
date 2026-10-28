# CLAUDE.md: AIDLC Starter Kit

Build spec and working rules for Claude Code. Read fully before writing code.

## 1. Purpose

A starter kit that lets Product Managers take a feature from discovery to an
engineering-ready handoff **from their IDE, in plain language, without touching Git**.
Underneath, the kit handles versioning, ownership, review and approval, audit
history, traceability, golden-set evaluation and the engineering handoff.

Build everything from scratch. Do not clone or vendor existing frameworks
(e.g. spec-kit, other AIDLC templates). Standard libraries and packages are fine.

Keep the product generic: no company names. Display name is set in `aidlc.yaml`
(default "AIDLC Kit").

## 2. Users

| Role | Does | Where |
|---|---|---|
| PM | Authors artifacts via chat commands | IDE (VS Code + Claude Code) |
| Reviewer | Approves or rejects; must differ from author | IDE command or GitHub PR screen |
| Engineer | Picks up handoff, decomposes into technical tasks | IDE |
| Viewer | Reads status, trace, audit, eval results | Deployed static site |

## 3. Principles

1. The PM never types a Git command and never needs to read Git output.
2. Every artifact has an ID, version, owner and status, and links to its parents.
3. Soft gates: drafts are free. **Handoff is the one hard gate**: everything in
   the feature approved, nothing stale, evals passing.
4. Approver ≠ author, always.
5. Audit history is append-only.
6. The model drafts; people decide. Generated content is a draft until approved.
7. Commands are thin wrappers over a plain Python CLI, so any IDE assistant or
   VS Code task can drive the same workflow (no lock-in to Claude Code).
8. Deterministic by default: evals run from cached model outputs in CI; live
   model calls are opt-in.

## 4. User journey (what the kit must support)

| # | Command | Purpose | Input | Output | Behind the scenes |
|---|---|---|---|---|---|
| 0 | `/new-feature` | Open a workspace | Name, owner | `features/FEAT-xxx/` | Branch `feat/FEAT-xxx` created |
| 1 | `/discover` | Agree on why | Notes, interviews, data | `discovery.md` | Commit |
| 2 | `/requirement` | Agree on what | Discovery brief | `requirements/REQ-xxx.md` | Commit, parent link |
| 3 | `/criteria` | Make done testable | Requirements | `criteria/AC-xxx.md` incl. AI thresholds | Commit, parent link |
| 4 | `/asset` | Define AI behaviour | Criteria | `assets/` prompt + config | Commit, parent link |
| 5 | `/eval` | Prove it meets criteria | Criteria, assets | `evals/golden.yaml`, `evals/report.json` | Runner executes |
| 6 | `/submit` | Ask for a decision | Feature set | Review request | Push, PR opened |
| 7 | `/approve` / `/reject` | Accountable sign-off | PR diff, eval report | Approval or reason | PR review, status updated |
| 8 | `/handoff` | One package for engineering | Approved artifacts | `handoff/HND-xxx/` bundle | Hard gate check, merge, tag |
| 9 | `/decompose` | Spec-driven technical plan | Handoff bundle | `decomposition/DEC-xxx.md` + tasks | Branch, PR |
| — | `/status` | Where am I, what's next | — | Plain-language summary | Reads repo state |
| — | `/change` | Edit an approved artifact | Artifact ID | New version; downstream marked stale | Commit |

Every command ends by telling the PM, in one or two plain sentences, what
happened and what the next step is. Never show raw Git output unless asked.

## 5. Repository layout

```
aidlc.yaml                  # kit config: display name, roles, thresholds defaults
CLAUDE.md
README.md
.claude/commands/*.md       # slash commands (thin: call the CLI, then explain)
aidlc/                      # Python package
  cli.py                    # entry point: `aidlc <command>`
  artifacts.py              # load/save/validate frontmatter, IDs, versions
  trace.py                  # parent links, staleness, trace graph
  gitops.py                 # all Git/gh calls live here and only here
  review.py                 # submit/approve/reject, approver != author
  audit.py                  # append-only audit log
  evals/runner.py           # golden-set runner
  evals/model.py            # cached + live model client
  handoff.py                # gate check + bundle builder
  decompose.py              # engineer decomposition scaffold
  site/build.py             # static viewer generator
  templates/                # artifact templates (markdown + frontmatter)
features/FEAT-001-guest-request-triage/   # worked example
audit/log.jsonl             # append-only, written only by CI on merge
site/                       # generated, not committed
docs/                       # architecture, workflow, trade-offs, limitations
tests/
.github/workflows/          # validate, eval, audit, deploy-site
.github/CODEOWNERS
```

## 6. Artifact model

Markdown files with YAML frontmatter. Body is plain language for PMs.

```yaml
id: REQ-003
type: requirement        # discovery | requirement | criteria | asset | eval | handoff | decomposition
feature: FEAT-001
title: Route maintenance requests to engineering queue
version: 2               # integer, bumped on every change after first approval
status: draft            # draft | in_review | approved | rejected | stale
owner: alice             # GitHub username
parents:
  - {id: DISC-001, version: 1}
approvals:
  - {by: bob, version: 2, at: 2026-10-29T10:00:00Z}
updated_at: 2026-10-29T09:12:00Z
```

Rules:
- IDs are sequential per type, assigned by the CLI. Never reuse an ID.
- **Staleness:** an artifact is `stale` if any parent's current version is greater
  than the version recorded in its `parents`. Computed, not hand-set; the
  validator writes it.
- Approval is valid only for the version approved. Editing an approved artifact
  bumps the version and clears its approval.
- `approvals[].by` must not equal `owner` (enforced in CLI and CI).

Criteria artifacts carry machine-readable thresholds used by the eval runner:

```yaml
thresholds:
  accuracy: 0.90
  max_unsafe: 0
```

## 7. Git automation (gitops.py)

- One branch per feature: `feat/FEAT-xxx`. Created on `/new-feature`.
- Every artifact save = one commit, message format:
  `[FEAT-001][REQ-003 v2] <short summary>` (author = current Git user).
- `/submit` pushes and opens or updates a PR via `gh`, body generated from the
  feature's artifacts and eval report.
- `/approve` = `gh pr review --approve` plus recording the approval in
  frontmatter on the reviewer's behalf. GitHub also blocks self-approval.
- `/handoff` runs the gate, then merges the PR (squash) and tags
  `FEAT-001/handoff-v<n>`.
- Before any operation: auto-commit pending work, pull with rebase, and on
  conflict stop and explain in plain language. Never force-push.
- One-time setup (documented): `gh auth login`, Python 3.12. This is the only
  Git-adjacent thing a PM does, once.

## 8. Review, approval, audit

- `.github/CODEOWNERS` defines reviewers per path.
- Branch protection on `main` (documented, set manually): PR required, 1 approval,
  required checks `validate` and `eval`.
- CI `validate`: frontmatter schema, ID uniqueness, parent links resolve,
  staleness recomputed, approver ≠ owner, handoff gate if a handoff bundle is present.
- CI `audit` (on merge to `main`): appends one JSON line per changed artifact to
  `audit/log.jsonl`: `{at, feature, id, version, status, actor, approvers, commit, pr}`.
  CI check fails if any existing line in the log was modified or deleted.

## 9. Golden-set evaluation

- `evals/golden.yaml`: list of cases `{id, input, expected, tags}`, each case
  linked to one or more criteria IDs.
- Runner: render prompt from the asset, call model, parse structured output,
  score against `expected`, compare metrics to criteria thresholds.
- Model client modes:
  - `cached` (default, CI): reads `evals/cache/<hash>.json`; hash = sha256 of
    model + prompt version + rendered input. Missing cache entry = test error, not a pass.
  - `live`: Anthropic API via `ANTHROPIC_API_KEY`; writes cache entries.
- Output `evals/report.json` + human summary in `evals/report.md`:
  per-metric value vs threshold, pass/fail, failing cases listed.
- CI `eval` job runs cached mode on every PR and blocks merge on fail.
- A test with a fake model proves the runner logic without any API.

## 10. Handoff and decomposition

`/handoff` hard gate: all artifacts in the feature `approved`, none `stale`,
latest eval report passing and newer than the asset version. On fail, list
exactly what blocks it, in plain language.

Bundle `handoff/HND-xxx/`:
- `spec.md`: one readable document compiled from discovery, requirements, criteria
- `assets/`: frozen copy of prompts and config at approved versions
- `golden.yaml` + `eval-report.md`
- `trace.json`: full graph criterion → requirement → discovery, with versions
- `manifest.json`: IDs, versions, approvers, commit SHA

`/decompose` (engineer): reads the bundle and produces `DEC-xxx.md`:
components, interfaces and contracts, data, risks, and a task list where every
task references the criteria it satisfies. Tasks with no criterion are flagged.
The golden set becomes the regression gate for the implementation.

## 11. Viewer site

Static HTML generated by `aidlc/site/build.py` (Jinja2), deployed to GitHub Pages
by CI on every push to `main`. Pages:
- Features overview: status per stage, blocking items
- Feature detail: artifacts with version, owner, status, approvals
- Trace graph: discovery → requirements → criteria → assets → evals → tasks
- Audit timeline from `audit/log.jsonl`
- Eval results per feature

Read-only. No backend. Light and dark mode. Works on phone width.

## 12. Worked example

`FEAT-001 Guest request triage`: classify incoming hotel guest messages into
`housekeeping | maintenance | food_and_beverage | front_desk | other`, flag
urgent ones. Include a full chain: discovery, 2-3 requirements, criteria with
thresholds, prompt asset, ~20 golden cases with committed cache, an approved
review, a handoff bundle and one decomposition. The example must pass CI.

## 13. Documentation (docs/)

- `architecture.md`: components, data model, diagram
- `workflow.md`: PM journey and engineer journey, step by step
- `trade-offs.md`: Git as store vs database; static viewer vs app; cached vs
  live evals; Claude Code commands vs plain CLI; soft vs hard gates
- `limitations.md`: honest list (concurrency, setup step, single repo, no SSO,
  approvals depend on GitHub permissions)
- `demo.md`: a 5-minute demo script

README: what it is, 3-step setup, demo walkthrough, links to site and docs.

## 14. Engineering conventions

- Python 3.12, few dependencies: PyYAML, Jinja2, anthropic (optional), pytest.
- All Git and `gh` calls go through `gitops.py`; tests mock it.
- Type hints; small pure functions; no global state.
- Tests for: frontmatter validation, staleness, approver ≠ owner, handoff gate,
  audit append-only check, eval scoring, site build.
- No secrets in the repo. No personal data in examples.
- Log significant design decisions in `docs/decisions.md` (date, decision,
  alternatives rejected, why).

## 15. Build order

1. Skeleton, `aidlc.yaml`, artifact model + validator + tests
2. CLI commands + slash commands + `gitops.py`
3. Review, approval, audit, CODEOWNERS, CI `validate` and `audit`
4. Eval runner, cache, CI `eval`
5. Handoff gate + bundle, `/decompose`
6. Worked example end to end
7. Viewer site + Pages deploy
8. Docs, README, demo script

After each step: run tests, commit, and state what works and what is next.

## 16. Definition of done

- A PM can run `/new-feature` through `/handoff` without seeing Git.
- CI blocks merge on invalid artifacts, stale links, self-approval or failing evals.
- Audit log is append-only and enforced.
- Example feature passes CI and appears on the deployed site.
- Docs cover architecture, workflow, trade-offs and limitations.
