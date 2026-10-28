# Trade-offs

What was chosen, what it costs, and when you would choose differently.

## Git as the store, not a database

Every artifact is a file in the repository, and Git and GitHub hold the
history, the review and the access control.
- **Gain:** nothing new to host, back up or secure. Versions, authorship and
  review come free, and the record can be read without the kit.
- **Cost:** concurrency is whatever Git offers. Reading across features means
  reading files. A PM depends on the kit to hide Git, and when it cannot (a
  merge conflict) it stops and explains rather than guessing.
- **Choose a database instead** if many people edit the same item at the same
  time, or you need queries across thousands of items.

## A static viewer, not an app

The site is plain HTML generated from the repository after each merge.
- **Gain:** no server, no login of its own, nothing to attack, and it cannot
  disagree with `/status` because it uses the same code.
- **Cost:** it is read-only and only as fresh as the last merge to `main`.
  Work on a branch or an open PR does not appear. There is no search and no
  filtering.
- **Choose an app** if people need to act in the browser or see live state.

## Cached evals in CI, live evals on request

CI replays saved model answers; a live run is a deliberate act.
- **Gain:** CI is free, fast and the same every time, needs no secret, and a
  reviewer can read exactly what the model said. A model outage or price
  change cannot break a merge.
- **Cost:** the saved answers describe one model on one prompt on one day. If
  the provider changes the model behind a name, CI will not notice until
  someone runs `/eval --live` again. Changing the prompt, model or settings
  means paying for a new run.
- **Mitigation:** the cache key covers provider, model, settings and prompt
  text, so a stale answer is never silently reused: a changed prompt is a
  cache miss and a failing check.

## Assistant adapters over a plain CLI

The rules live in a Python CLI; each assistant gets thin generated files.
- **Gain:** no vendor is required, the rules do not depend on a model behaving,
  and wording stays the same everywhere. The kit works from a terminal with no
  assistant at all.
- **Cost:** each assistant has its own file format, which can change. The
  adapters follow documented formats and are tested for content, but none has
  yet been used in a real assistant session.
- **Rule of thumb:** governance is enforced by the CLI and CI. The assistant
  only supplies the words.

## Soft gates, one hard gate

Drafts, edits and reviews are free; only handoff is a hard gate.
- **Gain:** PMs can explore without ceremony, and the strict rules apply where
  the risk is: when the work leaves for engineering.
- **Cost:** a bad draft can sit in the repository for a long time, and nothing
  stops a team from building from an unapproved draft outside the kit.
- **Choose a harder gate** (for example required reviews on every commit) by
  tightening branch protection; the kit does not need to change.

## Self-declared risk, challenged by a reviewer

The tier comes from answers the PM gives. The kit computes it
deterministically, but it cannot know the answers are true.
- **Mitigation:** the risk profile is itself an artifact that the risk
  reviewer must approve at Tier 2 and 3, and the review request shows the
  answers next to the tier. A PM can raise the tier but not lower it, and a
  lower tier only counts once a new version is approved.
- **Not eliminated:** a PM who understates the risk and a reviewer who does
  not look will pass it. The kit records who approved what; it does not check
  the facts.

## Process enforcement here, platform controls elsewhere

The kit enforces process: who reviewed, which version, whether evals passed,
what was handed off. It does not enforce what the AI is allowed to touch.
- **Where those controls live:** role-based access to data, network and
  secrets, an AI gateway for logging, filtering and rate limits, and the
  data-protection work itself. The Tier 3 privacy assessment is a document a
  data owner approves, not a control.
- **Why not here:** a documented process on top of weak platform controls gives
  false comfort, and platform controls are already someone's job. The kit's
  value is making the human decisions visible and hard to skip.

## Roles and approvals in a file

`aidlc.yaml` says who can approve what, and CI reads it from the base branch
so a pull request cannot change its own reviewers.
- **Gain:** one place to read the rules, reviewed like any other change, with
  `CODEOWNERS` generated from it.
- **Cost:** it is configuration, not an identity system. It is only as
  trustworthy as GitHub accounts and repository permissions.
