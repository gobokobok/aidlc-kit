# Design decisions

Newest last. Each entry: date, decision, alternatives rejected, why.

## 2026-10-28: Artifact IDs are unique per feature, not repo-wide

- **Decision:** `REQ-003` is unique within its feature; the global key is
  `FEAT-001/REQ-003`. Parent links stay inside one feature.
- **Rejected:** one repo-wide sequence per type.
- **Why:** each feature lives on its own branch. A repo-wide counter would let
  two PMs on different branches both take `REQ-004` and collide at merge. A
  per-feature counter is only ever advanced on one branch. `next_id` takes
  every ID ever used (files plus audit log) so deleted IDs are not reissued.

## 2026-10-28: Fixed location per artifact type

- **Decision:** `discovery.md`, `requirements/REQ-xxx.md`, `criteria/AC-xxx.md`,
  `assets/ASSET-xxx.md`, `evals/EVAL-xxx.md`, `handoff/HND-xxx/handoff.md`,
  `decomposition/DEC-xxx.md`. The validator checks that folder, filename, `type`,
  `id` and `feature` agree. Asset IDs use the prefix `ASSET`.
- **Rejected:** discovering artifacts by scanning every `.md` for frontmatter.
- **Why:** frozen copies inside a handoff bundle would otherwise look like
  duplicate IDs, and a PM can tell from the path alone what a file is.

## 2026-10-28: Staleness uses direct parents only, and is written into `status`

- **Decision:** an artifact is stale when a *direct* parent's version is ahead
  of the version it recorded (the CLAUDE.md rule, as written). `aidlc validate
  --write` writes `stale`; a stale artifact that has caught up returns to
  `draft`, since it changed and needs a fresh review. CI runs validate without
  `--write` and fails when a stored status disagrees with the computed one.
  `trace.downstream()` gives the full transitive impact for `/change` to report.
- **Rejected:** marking every transitive descendant stale; keeping staleness
  out of `status` entirely.
- **Why:** direct-only keeps the rule simple to explain. Grandchildren are
  still caught: once the stale child is revised, its version moves and they go
  stale in turn, and the handoff gate refuses anything stale in between.

## 2026-10-28: When an edit creates a new version

- **Decision:** `apply_edit` bumps the version (and clears approvals) only if
  the current version has been reviewed: status `in_review`, `approved`,
  `rejected` or `stale`, or it holds an approval for the current version.
  Edits to an unreviewed draft keep the version number. (Updated in step 2:
  `stale` overwrites the earlier status, so a stale item counts as reviewed;
  an extra version is cheaper than an edit slipping past review.)
- **Rejected:** bumping on every save.
- **Why:** approvals and parent links pin a version, so a version must be
  frozen once anyone has reviewed it. Before that, bumping on every save only
  produces noise and spurious staleness in children.

## 2026-10-28: Separate `validate.py` and `config.py` modules

- **Decision:** repo-wide checks live in `aidlc/validate.py`; `aidlc.yaml`
  loading lives in `aidlc/config.py`. Neither is in the CLAUDE.md layout.
- **Rejected:** putting repo checks in `artifacts.py` or `cli.py`.
- **Why:** `artifacts.py` stays about one file at a time and `trace.py` about
  the graph; the CI `validate` job and the CLI both call `validate.py`.

## 2026-10-28: Missing parents are a warning on drafts, an error otherwise

- **Decision:** a non-discovery artifact with no parents is a warning while it
  is a draft and an error once submitted or approved.
- **Why:** soft gates: drafts are free, but nothing reaches review untraced.

## 2026-10-28: Risk and privacy assessment artifact shapes

- **Decision:** `risk.md` (RISK-001) and `privacy_assessment.md` (prefix `PIA`)
  live at the feature root, one of each per feature. Risk has no parents.
  A privacy assessment may link to discovery and risk, so revising the risk
  answers marks it stale. Handoff may link to both.
- **Rejected:** risk as a child of discovery.
- **Why:** the spec makes risk a root: a risk change alters gate requirements,
  not content. A privacy assessment, unlike content, is written *about* the
  risk answers, so it should be re-checked when they change.

## 2026-10-28: A lowered tier waits for approval (`approved_tier`)

- **Decision:** the risk artifact carries `approved_tier`, written when the risk
  profile becomes approved. The governing tier is the higher of
  `declared_tier` and `approved_tier` until the current version is approved.
  `declared_tier` can never be below the computed tier.
- **Rejected:** reading the previous approved tier from Git history.
- **Why:** keeps the rule checkable from the files alone, in the CLI, the
  validator and the viewer. Raising applies at once; lowering needs a new
  version approved by `risk_reviewer` (risk routing), as the spec requires.
  A hand edit of `approved_tier` shows up in the PR diff; step 3 CI can
  compare it with `main`.

## 2026-10-28: Risk profile always routes to risk_reviewer, even at Tier 1

- **Decision:** routing in `aidlc.yaml` is applied as written:
  `risk: [risk_reviewer]` for every tier.
- **Rejected:** skipping the risk reviewer at Tier 1.
- **Why:** a Tier 1 result comes from self-declared answers; the risk
  reviewer's challenge is what makes it trustworthy. Config stays the single
  source of truth: to relax it, change the routing.

## 2026-10-28: Unrouted types need one approval from anyone but the author

- **Decision:** types missing from `review_routing` (eval, decomposition,
  privacy assessment) require the pseudo-role `any_reviewer`, plus tier extras.
- **Why:** keeps the original "approver differs from author" rule for them
  without inventing routing the spec did not give.

## 2026-10-28: Validator warns about role approvals; CI and the gate enforce

- **Decision:** `validate` warns when an approved artifact lacks a role (for
  example after a tier rise) and errors only on hard inconsistencies
  (self-approval, approved with no other approver, declared tier below
  computed, missing `human_review_step` once submitted).
- **Why:** the spec says a tier rise should fail the handoff gate, not
  invalidate earlier approvals. Enforcement is `approvals_complete` (step 3)
  and the gate (step 5).

## 2026-10-28: Second PM and a data owner in the default config

- **Decision:** `aidlc.yaml` adds `dana: [pm]` and `lee: [data_owner]` to the
  people from the spec.
- **Why:** with one PM, `pm_peer` can never be satisfied, so no discovery could
  be approved; with no data owner, no Tier 3 feature could pass. The config
  check warns about both situations.

## 2026-10-28: `workspace.py` holds feature and artifact operations

- **Decision:** creating features and artifacts, editing, revising risk and
  working out the next step live in `aidlc/workspace.py` (files only).
  `cli.py` drives Git through `gitops.py` around those calls; `review.py`
  plans who to ask and writes the PR description.
- **Why:** keeps Git out of the logic so it is tested on plain folders, and
  keeps `cli.py` to argument parsing and plain-language output.

## 2026-10-28: `feature.yaml` per feature

- **Decision:** each feature folder has `feature.yaml` (id, title, owner,
  created_at), written by `/new-feature` and checked by the validator.
- **Why:** the feature's name and owner are not any one artifact's to hold.

## 2026-10-28: `/change` moves parent links to current versions

- **Decision:** editing an artifact relinks its parents to their current
  versions. `aidlc change <ID>` with no new text is how a stale item is
  brought up to date.
- **Rejected:** a separate relink command.
- **Why:** the PM edits in light of the current parents; any reviewed item
  becomes a new version anyway, so reviewers see the change.

## 2026-10-28: Direct edits in the IDE are turned into new versions

- **Decision:** before every command, pending work is auto-committed. If a
  file of an already reviewed version was edited by hand, it is first turned
  into a new version (approvals cleared) and the PM is told.
- **Why:** PMs will edit Markdown directly; otherwise an old approval would
  silently cover new content.

## 2026-10-28: `/privacy` command

- **Decision:** add `/privacy` (CLI `aidlc privacy`) to write the privacy
  assessment that Tier 3 requires.
- **Why:** the update requires the artifact but names no command to create it.

## 2026-10-28: Who is "me", and working without GitHub

- **Decision:** the current user is `$AIDLC_USER` if set, else `gh api user`.
  Without an `origin` remote, `/submit` marks items in review and says no
  review request could be sent.
- **Why:** `$AIDLC_USER` serves CI and tests; the local mode lets a team try
  the kit before connecting GitHub.

## 2026-10-28: Slash commands share one rules file

- **Decision:** `.claude/aidlc-rules.md` holds the rules every command follows
  (call the CLI, never Git; relay results in plain sentences; drafts via
  stdin). It sits outside `.claude/commands/` so it is not a command itself.

## 2026-10-28: Assistant-neutral: package + `aidlc init` + generated adapters

Supersedes "Slash commands share one rules file" above.

- **Decision:** the kit ships as a Python package. In the adopting repository,
  `aidlc init --assistant <name>` (repeatable) writes `aidlc.yaml` if missing,
  `features/`, and the files each chosen assistant reads: Claude Code,
  GitHub Copilot in VS Code, Cursor, `AGENTS.md`, or VS Code tasks for no
  assistant at all. All are rendered from one neutral source in
  `aidlc/assistants/` (11 command prompts + working rules) that names no
  vendor; a test enforces that, and that every prompt calls a real CLI
  command. Shared files (`CLAUDE.md`, `AGENTS.md`,
  `.github/copilot-instructions.md`, `.vscode/tasks.json`) are never
  overwritten: only a marked AIDLC block, or tasks labelled `AIDLC:`, are
  replaced. The kit repository commits no generated assistant files, and
  its own `CLAUDE.md` is the build spec, which does not ship.
- **Rejected:** a template repository companies copy (it would carry our
  build spec and our assistant's files); hand-maintained files per assistant
  (wording drifts apart).
- **Why:** companies use whatever assistant they already have. All rules
  live in the CLI, so governance is identical everywhere and never depends
  on the model behaving; only drafting quality varies.
- **Formats** (checked 2026-10-28): Copilot prompt files in
  `.github/prompts/*.prompt.md` with `description`, `argument-hint`,
  `agent: agent`; Cursor commands as plain Markdown in `.cursor/commands/`
  with always-on rules in `.cursor/rules/*.mdc`. Cursor documents no argument
  placeholder, so non-Claude prompts describe the PM's input in words.
- **Not yet:** live evals are still specified per provider in step 4; `init`
  will also write CODEOWNERS and CI workflows from step 3.

## 2026-10-28: Approvals count only when GitHub confirms them

- **Decision:** `/approve` records the approval in the artifact's frontmatter,
  pushes, then submits a GitHub review. `approvals_complete` counts a recorded
  approval only if that login has an APPROVED review on the PR at a commit
  where the artifact had the same version. Roles come from `aidlc.yaml` on the
  base branch. Changing `approved_tier` needs an approved risk review in the
  same PR.
- **Rejected:** trusting frontmatter alone (anyone can type a name); trusting
  Git commit authors (also forgeable); counting only reviews on the latest
  commit (every later push would wipe approvals of untouched items).
- **Why:** GitHub authenticates reviewers; the file is the readable record
  and the review is the proof.

## 2026-10-28: Approvals given on the GitHub screen are synced by the PM's commands

- **Decision:** `/status`, `/reviewers` and `/submit` read the PR's reviews and
  record any approvals given on the GitHub screen into the files (for items
  the person can still approve, at the version they saw), then push. GitHub
  "request changes" reviews are shown to the PM, not turned into rejections.
- **Rejected:** a CI bot committing to the PR branch (pushes by the default CI
  token do not re-run the required checks, leaving the PR stuck).
- **Why:** keeps the files the single readable record without bot pushes;
  until synced, `approvals_complete` notes that the approval exists.

## 2026-10-28: Approving an item marks it approved only when every role is in

- **Decision:** each `/approve` adds the reviewer's approval; the item becomes
  `approved` once all effective roles are satisfied. Approving the risk profile
  writes `approved_tier`, then other items are re-settled under the new tier.
  While a higher tier still governs, lowering it needs that tier's reviewers
  (at Tier 3: risk reviewer and data owner).
- **Why:** status then means what it says, and the audit log's `status` and
  `roles_satisfied` agree.

## 2026-10-28: `/reject` requires IDs and a reason; it stores `rejections`

- **Decision:** rejections are kept as a list in frontmatter
  (`{by, version, at, reason}`), the reviewer's own approval of that version is
  withdrawn, and GitHub gets a "request changes" review. The author sees the
  reason in `/status`. Rejecting needs explicit IDs.
- **Why:** a reason is the point of a rejection, and a default of "reject
  everything" is too easy to trigger by accident.

## 2026-10-28: Kit-managed blocks in CODEOWNERS; `kit_admin`

- **Decision:** `sync-codeowners` writes only a marked block in
  `.github/CODEOWNERS`, so a company's own code owners stay. The validate job
  fails if the block differs from what `aidlc.yaml` produces. People with the
  optional role `kit_admin` own `aidlc.yaml` and `.github/`.
- **Why:** `aidlc.yaml` decides who reviews what; changing it should itself
  need review.

## 2026-10-28: Audit log written by CI after merge

- **Decision:** the `audit` workflow runs on every push to `main`, appends one
  line per changed artifact (deletions as `status: deleted`), commits as
  github-actions[bot] and pushes to `main`, rebasing once if needed. PRs may not
  touch the log; on `main` earlier lines must be an exact prefix.
  Runs are serialised with a concurrency group; the bot's own commit changes no
  artifacts, so it records nothing and does not loop.
- **Trade-off:** `main` must let GitHub Actions bypass the PR rule. That is a
  setup step the docs must spell out (limitations).

## 2026-10-28: The golden set is a reviewed artifact

- **Decision:** `evals/golden.yaml` holds the cases; `evals/EVAL-001.md` records
  its sha256 and links to the criteria it covers and the assets it runs.
  Changing the file without recording it is a validation error; recording a
  reviewed golden set makes a new version.
- **Why:** the cases define "correct", so they need the same review and
  traceability as the criteria; the hash stops a quiet edit after approval.

## 2026-10-28: Cache key and what counts as current

- **Decision:** the cache key is sha256 of provider, model, max_tokens,
  effort, temperature, asset ID@version and the fully rendered system and user
  prompt (the spec's "model + prompt version + rendered input", made stricter).
  A report is current only for the asset and criteria versions, golden sha and
  tier it ran with. CI re-runs every golden set from cache and fails if the
  committed report differs, so a report cannot be hand-edited to pass.

## 2026-10-28: Tier minimums apply even when a criterion is silent

- **Decision:** a criterion threshold looser than the tier's `min_thresholds`
  fails the eval with a message saying how to fix it; a tier minimum the
  criterion does not mention is added to its checks. Criteria without
  thresholds use the `aidlc.yaml` defaults. A criterion with no cases fails.

## 2026-10-28: Live providers through official SDKs, as optional extras

- **Decision:** `eval.provider` is `anthropic`, `openai` or `openai_compatible`
  (with `base_url` for Azure OpenAI, gateways or local servers). Each provider
  module imports its vendor SDK only when called (`aidlc-kit[anthropic]`,
  `aidlc-kit[openai]`). Vendor names appear only in `aidlc/evals/providers/`
  and the assistant adapters (enforced by a test).
- **Anthropic specifics:** sampling parameters are not sent (the Messages API
  rejects them since 2026-10-21); server-side refusal fallbacks are enabled
  (`fallbacks: "default"`) and answers served by a fallback model are flagged in
  the report, since they may not reflect the configured model.
- **Rejected:** raw HTTP clients (we would re-implement retries and error
  types); a required vendor dependency.
- **Not verified:** no live call has been made; providers are tested against
  stand-in SDK modules.

## 2026-10-28: Expected answers come from people, not the model

- **Decision:** the `/eval` prompt tells the assistant to take expected values
  from the PM and the documents and never to fill them in by running the
  model; live runs (which cost money) need the PM's go-ahead.
- **Why:** a golden set copied from model output only proves the model agrees
  with itself.

## 2026-10-28: `/handoff` is two passes, and the package is itself reviewed

- **Decision:** the first `/handoff` checks the gate, then builds `handoff/HND-xxx/`
  (spec.md, risk.md, frozen assets, golden.yaml, eval-report.md, trace.json,
  manifest.json) and records it as an artifact in review. Routing for `handoff`
  plus the tier extras (at Tier 2: Tech and Risk) accept it with `/approve`. The
  second `/handoff` squash-merges and tags.
- **Rejected:** merging in the same command that builds it (nobody would have
  seen the package); a separate approval mechanism (the existing one gives
  roles, GitHub confirmation and audit for free).
- **Why:** the spec routes `handoff` to a reviewer; the package is the thing
  engineering will build from, so it is the thing reviewers should accept.

## 2026-10-28: One gate, used by the CLI and by CI

- **Decision:** `handoff.gate` is a pure function returning blockers, each with
  who can resolve it. `/handoff` runs it with the feature's validation errors;
  CI `validate` runs it for any package that is in review or approved for
  the current content. A package for older content is stale and skipped.
- **Why:** the hard gate cannot be bypassed by editing files or skipping the
  command, and a PM sees the same wording in the IDE and in the CI log.

## 2026-10-28: The package is frozen by checksums; handed-off state lives in tags

- **Decision:** `manifest.json` records a sha256 for every file in the package
  except `handoff.md` (whose status changes) and itself; validate fails when a
  file differs or disappears. Which HND packages were handed off is read from
  tags `FEAT-001/handoff-v<n>` (local or remote), not from a state file.
- **Why:** a tag cannot drift from the merge it marks, and there is no second
  record to keep in sync.

## 2026-10-28: Merge and tidy-up

- **Decision:** `gh pr merge --squash` without `--delete-branch` (the GitHub
  setting for deleting merged branches does that); the local feature branch is
  deleted only when its feature folder is identical to `main`'s, so a later
  change starts from a fresh branch. A tag is annotated and pushed on its own.
  Without GitHub, the same flow squash-merges locally. If GitHub refuses (a
  required check or approval is missing), the PM is told to look at the review
  request and nothing is tagged.
- **Rejected:** merging with `--admin` or `--auto` (the point is that GitHub's
  protection still applies).

## 2026-10-28: Technical plan: own branch, flags not blocks, scaffold from the package

- **Decision:** `/decompose` creates `decompose/FEAT-xxx` from `main`, scaffolds
  `DEC-xxx` from the package (components from requirements, one starter task per
  criterion, a regression-gate task), and `/submit` opens a PR from that branch.
  Untraced tasks and uncovered criteria are warnings shown in `/status` and in
  the review request; unknown criteria are errors. The engineer role is not
  enforced: anyone can start a plan, and the review decides.
- **Rejected:** blocking submit on untraced tasks (a reviewer may accept an
  infrastructure task that maps to no criterion; they should see it flagged, not
  have it silently dropped).
- **Open point:** `decomposition` is not in the review routing, so it needs any
  other person plus the tier's extra reviewers (at Tier 2, the risk reviewer
  must accept a technical plan). Add `decomposition:` to `review_routing` if
  that is more than you want.

## 2026-10-28: The worked example is recorded for real, on GitHub, with two accounts

- **Decision:** FEAT-001 was written through the real CLI on the real repository
  (`gobokobok/aidlc-kit`): a feature branch, PR 1 for the feature and its
  handoff package, PR 2 for the technical plan, squash-merged, tagged
  `FEAT-001/handoff-v1`, with the audit job writing `audit/log.jsonl` on `main`.
  The drafts the PM fed in are kept in `examples/guest-request-triage/`.
- **Decision:** two GitHub accounts, both controlled by the same person, stand in
  for all roles: `gobokobok` (pm, engineer) writes everything, `alexdanm-oss`
  (pm, ops, tech, risk, data owner, kit admin) approves. One approval satisfies
  every role that account holds. This shows the mechanism, not independent
  review. With a real team, spread the roles across people.
- **Decision:** the saved model answers are from `claude-sonnet-5-5` through the
  Anthropic provider (20 calls per run). The first run failed two cases
  (a leak not marked urgent; a local-area question sent to front desk) because
  the prompt did not match REQ-002 and did not define `other`. The prompt was
  fixed, the golden set was not touched, the second run passed 20 of 20, and
  the answers from the first prompt were removed from the cache. The failed run
  stays in Git history. The prompt was shaped after seeing the failure; that is
  ordinary prompt work, but it means 20 of 20 is not a blind score.
- **Rejected:** a scripted stand-in recorded as if it were a model. An earlier
  attempt did this offline; it was thrown away once a real key was available,
  because cache entries must only ever hold answers a model gave.
- **Observed on real GitHub:** `approvals_complete` passed using the reviews API,
  the audit job appended to `main` without help, and the `tests` workflow of the
  kit failed on both PRs while the example was incomplete. `submit` failed once
  at "ask reviewers" right after the PR was created and worked on rerun; the
  cause was not found, so `request_reviewers` now retries once after two seconds.
- **Not done:** branch protection is not enabled on `main`, so the required
  checks and code-owner review were demonstrated by the checks passing, not by
  GitHub blocking a merge.

## 2026-10-28: Branch protection on main, with a deploy key for the audit job

- **Decision:** `main` has a ruleset (`protect-main`): pull request required with
  1 approval and code-owner review, required checks `validate`, `eval`,
  `approvals_complete` and `tests`, no deletion, no force-push.
- **Decision:** the audit job pushes `audit/log.jsonl` to `main`. GitHub does not
  let GitHub Actions bypass rules in a personal repository (only in an
  organisation), so the audit workflow checks out with the deploy key stored in
  the secret `AIDLC_AUDIT_KEY` when it exists, and that deploy key is a bypass
  actor. Without the secret the job pushes as GitHub Actions, which is what an
  organisation setup uses. A push with the key to the protected branch was
  tested by hand; the workflow itself has not yet run under protection.
- **Decision:** repository admins can bypass the ruleset ("always"), so the
  owner can still push directly. That is convenient while building and weakens
  the guarantee for the owner; set it to "pull request" to require a PR for
  everyone.
- **Rejected:** a personal access token in the workflow (it would act as the
  owner and carry far more access than the audit job needs); skipping
  protection (the point is that checks and approvals can block a merge).

## 2026-10-28: Viewer site

- **Decision:** `aidlc site build` renders plain HTML with Jinja2 into a folder
  (default `site/`, not committed), from the same functions the CLI uses
  (`validate`, the handoff gate, reviewer roles, the eval report, the audit
  log), so the site cannot disagree with `/status`. Pages: features overview,
  feature detail (stages, blockers, risk profile, items with ✓ or … per
  required reviewer role), trace graph, eval results, audit timeline.
- **Decision:** the site is built from `main` only. Work on a branch or an open
  PR does not appear until it is merged. Handoff state comes from the
  `FEAT-xxx/handoff-vN` tags, so the Pages job checks out full history.
- **Decision:** no JavaScript and no framework. The trace graph is inline SVG
  with the same information as a text list of chains under it, for phones and
  screen readers. Colour is never the only signal: statuses are words, and
  reviewer markers are ✓ and … plus the role name.
- **Decision:** artifact text is escaped by the template engine; the site
  shows titles, statuses and approvals, not the bodies of artifacts. Item IDs
  link to the file on GitHub when `--source-url` is given.
- **Decision:** styling follows the owner's "Monochrome Console" guideline
  (one blue accent, hairline cards, Schibsted Grotesk and Fragment Mono from
  Google Fonts with system fallbacks). The fonts are the only outside request;
  a site served inside a closed network falls back to system fonts.
- **Rejected:** a single-page app (a backend-free read-only view does not need
  one); rendering artifact bodies as Markdown (needs a Markdown library or a
  hand-rolled renderer and widens what can be injected); committing the built
  site (it is generated output).
- **Fixed on the way:** `.gitignore` listed `site/`, which also hid
  `aidlc/site/`; it is now `/site/`.
- **Verified on GitHub:** Pages was enabled with source "GitHub Actions"; the `AIDLC site` workflow built and deployed after the push, and the live feature page matches the local build (https://gobokobok.github.io/aidlc-kit/).

## 2026-10-29: Split the product from the live test run

- **Decision:** this repository is the product only: package, templates,
  docs, tests, `LICENSE` (MIT), tag `v0.1.0`. The live run of FEAT-001 (made on
  this repository, pull requests 1 and 2) is kept as a frozen snapshot in
  `examples/guest-request-triage/`, laid out like an adopting repository so the
  kit can be pointed at it with `--root`. The kit's own CI is only the tests
  workflow; the validate, eval, approvals, audit and site workflows, the
  generated `CODEOWNERS`, the personal `aidlc.yaml` and the audit deploy key
  belong in an adopting repository, not in the product.
- **Decision:** a second repository, `aidlc-demo`, is set up the way a company
  would (install from the tag, `aidlc init`) and runs the example live. It
  also tests the adoption path, which has not been tried on real GitHub.
- **Rejected:** one repository doing both jobs (a fork inherits real names,
  live audit history and secrets-shaped setup, and the kit's tests depended on
  a live example); rewriting history (the history is already public and
  records how the kit was built).
- **Consequence:** the commit and pull-request numbers in the snapshot's audit
  log and manifest point at this repository's history, as the snapshot's README
  says. The old Pages site stays up, at its last build, until the demo
  repository publishes its own.

## 2026-10-29: A reviewer's clone opens the review branch itself

- **Found while writing the test guide:** a reviewer who clones the repository
  sits on `main`, where an unmerged feature does not exist, so `/approve` said
  "There is no feature yet". Every reviewer on another machine would have needed
  `git fetch` and `git switch`, against the rule that people never type Git.
- **Decision:** when a feature is named (`--feature FEAT-001`) and is not in the
  working folder, or no feature is there and exactly one review branch is open,
  the kit fetches `feat/FEAT-001` from GitHub and opens it. With several open
  features and none named it stops and lists them. The assistants' approve
  command passes `--feature` when several are open.
- **Not changed:** with one feature already on `main` (for example one handed
  off) and a second open on GitHub, a command that names no feature still acts
  on the one on `main`. Name the feature with `--feature`.
- **Verified:** with a second clone of a real Git remote and a fake GitHub
  (tests), not yet with two real machines.
