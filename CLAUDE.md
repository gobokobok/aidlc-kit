# CLAUDE.md: AIDLC Starter Kit

Build spec and working rules for whoever builds the kit (here: Claude Code).
Read fully before writing code. This file is not shipped: companies install the
kit as a package and `aidlc init` writes the files their own assistant needs.

## 1. Purpose

A starter kit that lets Product Managers take a feature from discovery to an
engineering-ready handoff **from their IDE, in plain language, without touching Git**,
using whichever AI assistant their company already has.
Underneath, the kit handles versioning, ownership, review and approval, audit
history, traceability, golden-set evaluation and the engineering handoff.

Build everything from scratch. Do not clone or vendor existing frameworks
(e.g. spec-kit, other AIDLC templates). Standard libraries and packages are fine.

Keep the product generic: no company names. Display name is set in `aidlc.yaml`
(default "AIDLC Kit").

## 2. Users

| Role | Does | Where |
|---|---|---|
| PM | Authors artifacts via chat commands | IDE (VS Code or similar) with any supported assistant |
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
7. Assistant-neutral. All rules live in a plain Python CLI; chat commands are
   thin wrappers generated per assistant from one neutral source (section 5a).
   No assistant, model or vendor is required: VS Code tasks or a terminal can
   drive the same workflow, and governance never depends on the model behaving.
8. Deterministic by default: evals run from cached model outputs in CI; live
   model calls are opt-in.

## 4. User journey (what the kit must support)

| # | Command | Purpose | Input | Output | Behind the scenes |
|---|---|---|---|---|---|
| 0 | `/new-feature` | Open a workspace and profile its risk | Name, owner, risk questionnaire answers | `features/FEAT-xxx/` incl. `risk.md` (RISK-xxx) | Branch `feat/FEAT-xxx` created, tier computed |
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
| — | `/risk` | Revise the risk profile | New questionnaire answers | New RISK version, tier recomputed | Commit |
| — | `/reviewers` | Who still has to approve what | — | Pending roles and people per artifact | Reads repo state + `aidlc.yaml` |

Every command ends by telling the PM, in one or two plain sentences, what
happened and what the next step is. Never show raw Git output unless asked.
How the PM invokes a command depends on their assistant (section 5a); the
names above are the same everywhere.

## 5. Repository layout

```
aidlc.yaml                  # kit config: display name, people, review routing,
                            #   risk tiers, thresholds defaults
CLAUDE.md                   # this build spec (not shipped)
README.md
aidlc/                      # Python package (what ships)
  cli.py                    # entry point: `aidlc <command>`
  assistants/               # neutral command prompts + rules, and the adapters
                            #   that render them per assistant (`aidlc init`)
  artifacts.py              # load/save/validate frontmatter, IDs, versions
  trace.py                  # parent links, staleness, trace graph
  gitops.py                 # all Git/gh calls live here and only here
  review.py                 # submit/approve/reject, approver != author
  risk.py                   # risk questionnaire, tier computation
  reviewers.py              # review routing, role resolution, CODEOWNERS generation
  audit.py                  # append-only audit log
  evals/runner.py           # golden-set runner
  evals/model.py            # cached + live model client
  handoff.py                # gate check + bundle builder
  decompose.py              # engineer decomposition scaffold
  site/build.py             # static viewer generator
  templates/                # artifact templates (markdown + frontmatter),
                            #   incl. risk.md and privacy_assessment.md
features/FEAT-001-guest-request-triage/   # worked example
audit/log.jsonl             # append-only, written only by CI on merge
site/                       # generated, not committed
docs/                       # architecture, workflow, trade-offs, limitations
tests/
.github/workflows/          # validate, eval, audit, deploy-site
.github/CODEOWNERS          # generated from aidlc.yaml by `aidlc sync-codeowners`
```

The kit repository does not commit generated assistant files; they are
produced in the adopting company's repository.

### 5a. Distribution and assistants

The kit ships as a Python package (`pip install aidlc-kit`). In the adopting
company's repository, whoever sets it up runs once:

```
aidlc init --assistant <name> [--assistant <name> ...]
```

`init` writes `aidlc.yaml` (if missing), `features/`, the CI workflows,
CODEOWNERS, and the files for each chosen assistant (`aidlc sync-ci` refreshes
the CI files after an upgrade). Rerunning it updates them. It never overwrites a company's
own instructions: in shared files it only replaces a marked AIDLC block.

| `--assistant` | Writes | PM invokes |
|---|---|---|
| `claude` | `.claude/commands/*.md`, AIDLC block in `CLAUDE.md` | `/new-feature` |
| `copilot` | `.github/prompts/*.prompt.md`, AIDLC block in `.github/copilot-instructions.md` | `/new-feature` in Copilot Chat |
| `cursor` | `.cursor/commands/*.md`, `.cursor/rules/aidlc.mdc` | `/new-feature` |
| `agents` | AIDLC block in `AGENTS.md` (read by many assistants) | Plain request ("start a new feature") |
| `vscode` | AIDLC tasks in `.vscode/tasks.json` | Run Task, fill in input boxes |

All of these are rendered from one neutral source in `aidlc/assistants/`
(command prompts + shared working rules), so wording stays identical across
assistants. The neutral source names no assistant or vendor.

## 6. Artifact model

Markdown files with YAML frontmatter. Body is plain language for PMs.

```yaml
id: REQ-003
type: requirement        # discovery | requirement | criteria | asset | eval | handoff | decomposition
                         #   | risk | privacy_assessment
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

### 6a. Who reviews what: single source of truth is `aidlc.yaml`

```yaml
people:                       # who is in which role (GitHub usernames)
  alice: [pm]
  bob: [ops_reviewer]
  priya: [tech_reviewer]
  sam: [risk_reviewer]
  jonas: [engineer]

review_routing:               # which roles must approve which artifact type
  discovery:    [pm_peer]     # any other PM; at least one approver
  requirement:  [ops_reviewer, tech_reviewer]
  criteria:     [ops_reviewer, tech_reviewer]
  asset:        [tech_reviewer]
  risk:         [risk_reviewer]
  handoff:      [tech_reviewer]

risk_tiers:                   # see 6b
  T1: {label: Low,    extra_reviewers: [],                     required_artifacts: [],                      min_thresholds: {}, human_in_loop: false}
  T2: {label: Medium, extra_reviewers: [risk_reviewer],        required_artifacts: [],                      min_thresholds: {accuracy: 0.85}, human_in_loop: false}
  T3: {label: High,   extra_reviewers: [risk_reviewer, data_owner], required_artifacts: [privacy_assessment], min_thresholds: {accuracy: 0.95}, human_in_loop: true}
```

Rules:
- `pm_peer` is a special role: any person with role `pm` other than the author.
- A required role is satisfied when at least one person holding that role has an
  approval on the current version of the artifact. Author never counts.
- Effective required roles for an artifact = `review_routing[type]` plus the
  feature's tier `extra_reviewers`.
- `.github/CODEOWNERS` is **generated** from `people` and `review_routing` by
  `aidlc sync-codeowners`. CI fails if the committed file differs from the generated one.
- GitHub branch protection only enforces "1 approval + code owners". The role-based
  rule is enforced by the CI check `approvals_complete`, which must be a required
  status check on `main`.
- `/submit` tells the PM in plain language who was asked to review and why
  (for example: "Sent to bob (Ops) and priya (Tech). sam (Risk) is included
  because this feature is Tier 2.").
- `/reviewers` shows who must still approve what for the current feature.

### 6b. Risk profile (artifact type `risk`, ID prefix RISK)

Created automatically by `/new-feature` through a short guided questionnaire in
plain language. Revisable with `/risk`.

```yaml
id: RISK-001
type: risk
feature: FEAT-001
version: 1
status: draft
owner: alice
data_classes: [personal]        # public | internal | confidential | personal | payment
autonomy: suggest               # suggest | act_with_approval | act_autonomously
audience: customer_facing       # internal | customer_facing
regulated_decision: false       # affects pricing, eligibility, credit or similar
declared_tier: T2               # computed by the CLI
rationale: "Guest messages may contain names and room numbers."
```

Tier is computed by the CLI (deterministic, in `risk.py`):
- T3 if `payment` in data_classes, or `regulated_decision` is true, or
  `autonomy` is `act_autonomously` with `personal` or `confidential` data.
- T2 if `personal` or `confidential` in data_classes, or `audience` is
  `customer_facing`, or `autonomy` is `act_with_approval`.
- Otherwise T1.

Controls:
- The author can raise the tier but cannot lower it after the risk artifact has
  been approved. Lowering requires a new version approved by `risk_reviewer`.
- At T2 and T3 the risk artifact itself requires `risk_reviewer` approval
  (routing for type `risk`). The reviewer is expected to challenge the answers.
  The review request must show the questionnaire answers next to the computed tier.
- If the tier rises after other artifacts were approved, the handoff gate fails
  until the new tier's requirements are met. Risk is a root artifact: a risk
  change does not mark content artifacts stale, it changes gate requirements.

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
  Git-adjacent thing a PM does, once. Installing the kit and `aidlc init` are
  done once per repository by whoever sets it up.

## 8. Review, approval, audit

- `.github/CODEOWNERS` is generated from `people` and `review_routing` in
  `aidlc.yaml` by `aidlc sync-codeowners` (see 6a). CI fails if the committed
  file differs from the generated one.
- Branch protection on `main` (documented, set manually): PR required, 1 approval
  + code owners, required checks `validate`, `eval` and `approvals_complete`.
- CI `approvals_complete`: for every non-draft artifact in the PR, all effective
  required roles are satisfied on the current version, and approver is not the owner.
  An approval written in a file counts only if GitHub confirms that person
  approved the PR at a commit where the artifact had that version, and roles
  are read from `aidlc.yaml` on the base branch, so a PR cannot grant itself
  reviewers. Approvals given on the GitHub screen are recorded into the files
  by the PM's next `/status`, `/reviewers` or `/submit`.
- Optional role `kit_admin` owns `aidlc.yaml` and `.github/` in CODEOWNERS.
- The `audit` job pushes to `main`, so `main`'s protection must let GitHub
  Actions bypass the pull request rule (documented setup step).
- CI `validate`: frontmatter schema, ID uniqueness, parent links resolve,
  staleness recomputed, approver ≠ owner, handoff gate if a handoff bundle is present.
- CI `audit` (on merge to `main`): appends one JSON line per changed artifact to
  `audit/log.jsonl`: `{at, feature, id, version, status, actor, approvers, tier,
  roles_satisfied, commit, pr}`.
  CI check fails if any existing line in the log was modified or deleted.

## 9. Golden-set evaluation

- `evals/golden.yaml`: list of cases `{id, input, expected, tags}`, each case
  linked to one or more criteria IDs.
- The golden set is recorded as an `eval` artifact (`evals/EVAL-xxx.md`) holding
  the file's sha256, so reviewers approve exactly the cases that run; a
  changed `golden.yaml` must be recorded again (validator).
- Runner: render prompt from the asset, call model, parse structured output,
  score against `expected`, compare metrics to criteria thresholds. The prompt
  is the fenced block under `## Prompt` in the asset (optional `## System`),
  with `{{ input }}` for the case input; model settings live in the asset's
  frontmatter (`model`, `max_tokens`, `effort`, `temperature`) or `eval:` in
  `aidlc.yaml`. Metrics per criterion: `accuracy`, `<field>_accuracy`,
  `<field>_recall`/`_precision` for true/false fields, `unsafe` (failed cases
  tagged `safety`), `invalid`. `max_<metric>` thresholds are upper bounds.
- Answers produced by a provider's fallback model (after a refusal) are flagged
  in the report.
- The runner reads `min_thresholds` for the feature's risk tier. If a criterion's
  threshold is below the tier minimum, the eval fails with a clear message.
- If `human_in_loop` is true for the tier, the asset must declare a human-review
  step (checked by the validator).
- Model client modes:
  - `cached` (default, CI): reads `evals/cache/<hash>.json`; hash = sha256 of
    model + prompt version + rendered input. Missing cache entry = test error, not a pass.
  - `live`: calls the provider configured in `aidlc.yaml` (`anthropic`,
    `openai`, or any OpenAI-compatible endpoint such as Azure OpenAI or a
    local model); API key from an environment variable named in config;
    writes cache entries. No provider is required for cached mode.
- Output `evals/report.json` + human summary in `evals/report.md`:
  per-metric value vs threshold, pass/fail, failing cases listed.
- CI `eval` job runs cached mode on every PR and blocks merge on fail, and on a
  committed report that does not match a fresh cached run.
- A test with a fake model proves the runner logic without any API.

## 10. Handoff and decomposition

`/handoff` hard gate: all artifacts in the feature `approved`, none `stale`,
latest eval report passing and newer than the asset version, and:
- risk profile approved with a tier
- all `required_artifacts` for the tier exist and are approved
- all role-based approvals satisfied for every artifact
- `human_in_loop` declared if the tier demands it

On fail, list each unmet requirement in plain language, with who can resolve it.

Bundle `handoff/HND-xxx/`:
- `spec.md`: one readable document compiled from discovery, requirements, criteria
- `risk.md`: the approved risk profile
- `assets/`: frozen copy of prompts and config at approved versions
- `golden.yaml` + `eval-report.md`
- `trace.json`: full graph criterion → requirement → discovery, with versions
- `manifest.json`: IDs, versions, approvers, risk tier, commit SHA

`/decompose` (engineer): reads the bundle and produces `DEC-xxx.md`:
components, interfaces and contracts, data, risks, and a task list where every
task references the criteria it satisfies. Tasks with no criterion are flagged.
The golden set becomes the regression gate for the implementation.

## 11. Viewer site

Static HTML generated by `aidlc/site/build.py` (Jinja2), deployed to GitHub Pages
by CI on every push to `main`. Pages:
- Features overview: status per stage, blocking items, risk tier badge
- Feature detail: artifacts with version, owner, status, approvals, and the
  required reviewer roles with a satisfied or pending marker
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

FEAT-001 is Tier 2 (customer-facing, guest messages may contain personal data).
Include an approved RISK-001 and show a risk reviewer in the approvals. Add a
short second example in `docs/` showing how the same feature would change at
Tier 3 (extra privacy assessment, stricter threshold).

## 13. Documentation (docs/)

- `architecture.md`: components, data model, diagram, intake risk step,
  reviewer routing model
- `workflow.md`: PM journey and engineer journey, step by step, incl. the
  intake risk step and reviewer routing
- `setup.md`: installing the kit and `aidlc init` for each supported assistant,
  plus the no-assistant path (VS Code tasks, terminal)
- `trade-offs.md`: Git as store vs database; static viewer vs app; cached vs
  live evals; assistant adapters vs plain CLI; soft vs hard gates;
  self-declared risk (mitigated by risk reviewer challenge, not eliminated);
  process enforcement here versus platform controls (RBAC, data access, AI
  gateway) elsewhere
- `limitations.md`: honest list (concurrency, setup step, single repo, no SSO,
  approvals depend on GitHub permissions; roles and tiers are configuration,
  not an identity system; the kit records and enforces process, it does not
  replace technical data controls)
- `demo.md`: a 5-minute demo script

README: what it is, 3-step setup (install, `aidlc init --assistant <name>`,
`gh auth login`), demo walkthrough, links to site and docs.

## 14. Engineering conventions

- Python 3.12, few dependencies: PyYAML, Jinja2, pytest; provider SDKs only as
  optional extras for live evals.
- All Git and `gh` calls go through `gitops.py`; tests mock it.
- Type hints; small pure functions; no global state.
- Tests for: frontmatter validation, staleness, approver ≠ owner, handoff gate,
  audit append-only check, eval scoring, site build, tier computation, role
  resolution (including `pm_peer`), required roles with tier extras, CODEOWNERS
  generation and drift check, tier lowering blocked, extended handoff gate,
  assistant adapters (rendering, `init` idempotent, company content preserved,
  neutral source names no vendor, every command calls a real CLI command).
- No secrets in the repo. No personal data in examples.
- Log significant design decisions in `docs/decisions.md` (date, decision,
  alternatives rejected, why).

## 15. Build order

1. Skeleton, `aidlc.yaml`, artifact model + validator + tests; `risk` type,
   risk and reviewer config schema, validation
2. CLI commands + `gitops.py`; `/new-feature` questionnaire, `/risk`,
   `/reviewers`, `/submit` reviewer messaging; neutral command source,
   assistant adapters and `aidlc init`
3. Review, approval, audit, `sync-codeowners`, CI `validate`, `approvals_complete`
   and `audit` (with tier and role fields); `init` also writes CODEOWNERS and
   the CI workflows
4. Eval runner, cache, CI `eval`, tier minimum thresholds, live-eval providers
5. Handoff gate (extended for risk) + bundle, `/decompose`
6. Worked example end to end (Tier 2, plus Tier 3 variant in docs)
7. Viewer site + Pages deploy, tier badges and reviewer markers
8. Docs, README, demo script

After each step: run tests, commit, and state what works and what is next.

## 16. Definition of done

- A PM can run `/new-feature` through `/handoff` without seeing Git, from any
  supported assistant (Claude Code, Copilot, Cursor, AGENTS.md readers) or from
  VS Code tasks with no assistant at all.
- Nothing shipped requires a particular AI vendor; cached evals need no API key.
- CI blocks merge on invalid artifacts, stale links, self-approval or failing evals.
- Audit log is append-only and enforced.
- Example feature passes CI and appears on the deployed site.
- Docs cover architecture, workflow, trade-offs and limitations.
- Reviewers are resolved from `aidlc.yaml` and CODEOWNERS is generated from it.
- A Tier 2 or Tier 3 feature cannot reach handoff without the risk reviewer's approval.
- A PM can see at any time who still has to approve what.
