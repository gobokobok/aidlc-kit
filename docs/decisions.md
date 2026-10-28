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
  the current version has been reviewed: status `in_review`, `approved` or
  `rejected`, or it holds an approval for the current version. Edits to an
  unreviewed draft keep the version number.
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
