# Setup

Done once per repository by whoever sets it up (a few minutes), plus one
`gh auth login` per person. PMs do not need to know Git.

## What you need

- Python 3.12 and Git.
- The GitHub CLI, `gh`, signed in as yourself: `gh auth login`. The kit reads
  your username from it; that is how it knows who is approving.
- A GitHub repository for the work, and every person in `aidlc.yaml` as a
  collaborator with write access.

## 1. Install the kit

The package is not on PyPI yet. Install it from GitHub:

```bash
pip install git+https://github.com/gobokobok/aidlc-kit
```

For live evals, add the extra for your provider: `pip install 'aidlc-kit[anthropic]'`
or `'aidlc-kit[openai]'` (with the same `git+` address in front for now).

## 2. Set up the repository

Run this in the repository, naming each assistant your team uses:

```bash
aidlc init --assistant claude --assistant vscode
```

`init` writes `aidlc.yaml`, a `features/` folder, the CI workflows, the AIDLC
part of `.github/CODEOWNERS`, and the files each assistant needs. Run it again
any time; it updates the same files. It never overwrites your own content: in
shared files such as `CLAUDE.md` or `AGENTS.md` it only replaces the block
between the AIDLC markers.

Until the kit is on PyPI, tell CI how to install it, or the workflows will
fail on `pip install aidlc-kit==0.1.0`:

```bash
aidlc init --assistant claude --install "pip install git+https://github.com/gobokobok/aidlc-kit@<commit or tag>"
```

Pin to a commit or tag so a later change to the kit cannot change your CI.
`aidlc sync-ci --install "…"` rewrites the workflows after an upgrade.

| `--assistant` | Writes | The PM starts with |
|---|---|---|
| `claude` | `.claude/commands/*.md`, AIDLC block in `CLAUDE.md` | `/new-feature` |
| `copilot` | `.github/prompts/*.prompt.md`, AIDLC block in `.github/copilot-instructions.md` | `/new-feature` in Copilot Chat |
| `cursor` | `.cursor/commands/*.md`, `.cursor/rules/aidlc.mdc` | `/new-feature` |
| `agents` | AIDLC block in `AGENTS.md` (read by many assistants) | "start a new feature" |
| `vscode` | AIDLC tasks in `.vscode/tasks.json` | Run Task, then fill in the input boxes |

All of them are rendered from one neutral source, so the wording is the same.
The files follow each tool's documented format and are checked by tests, but
they have not yet been used in real assistant sessions; if one does not
behave, the CLI underneath works on its own.

### No assistant at all

The kit does not need one. In VS Code, run **Terminal → Run Task** and pick an
AIDLC task, or use a terminal: `aidlc new-feature`, `aidlc discover`,
`aidlc requirement`, and so on. `aidlc --help` lists everything; the chat
commands are wrappers over these.

## 3. Put your team in `aidlc.yaml`

Replace the example people with your team's GitHub usernames and roles, then
check it:

```bash
aidlc validate
```

```yaml
people:
  carol: [pm]
  dev:   [pm]               # a second PM, so discovery can get a PM peer
  erin:  [ops_reviewer]
  frank: [tech_reviewer, kit_admin]
  grace: [risk_reviewer]
  heidi: [data_owner]       # needed by Tier 3 features
  ivan:  [engineer]
review_routing:             # which roles must approve which type
  requirement: [ops_reviewer, tech_reviewer]
risk_tiers:                 # excerpt: when you set this, define T1, T2 and T3 together
  T2: {label: Medium, extra_reviewers: [risk_reviewer], min_thresholds: {accuracy: 0.85}}
```

`validate` warns when a role is required but nobody holds it, or when there is
no second PM for `pm_peer`. After changing people or routing, run
`aidlc sync-codeowners` and commit the result; CI fails if `CODEOWNERS` drifts.
Roles are configuration, not an identity system: whoever you list under a role
can approve for it. A small team can give several roles to one person, but the
author can never approve their own work.

## 4. Protect `main`

The kit's rules are only as strong as the branch protection behind them. On
GitHub, create a ruleset for `main` that:

- requires a pull request with 1 approval and **code owner** review;
- requires the status checks `validate`, `eval` and `approvals_complete`;
- blocks deletion and force-pushes.

The `audit` job pushes `audit/log.jsonl` straight to `main`, so it must be
allowed to bypass the pull request rule:

- **In an organisation:** add **GitHub Actions** as a bypass actor.
- **In a personal repository** GitHub does not allow that. Create a deploy key
  with write access, store its private key as the repository secret
  `AIDLC_AUDIT_KEY`, and add **Deploy keys** as a bypass actor. The audit
  workflow uses the key when the secret exists.

Repository admins can bypass a ruleset if you list them. Leave admins out if
you want every change, including the owner's, to go through review.

## 5. The viewer site (optional)

The `AIDLC site` workflow publishes a read-only site after each merge to
`main`. In **Settings → Pages**, set **Source** to **GitHub Actions**. Pages for
private repositories needs a paid GitHub plan, and the published site is
public if the repository is public. Build it locally with
`aidlc site build --out site`.

## 6. Live evals (optional)

CI never calls a model: it replays the saved answers in `evals/cache/`. To
create them, someone runs `/eval --live` once per prompt or model change.
Configure a provider in `aidlc.yaml`:

```yaml
eval:
  provider: anthropic        # or openai, openai_compatible (with base_url)
  model: <model id>
  api_key_env: ANTHROPIC_API_KEY
```

Put the key in an environment variable of that name on the machine that runs
the eval, never in the repository. `openai_compatible` with `base_url` covers
Azure OpenAI, a gateway or a local model. Commit the new files in
`evals/cache/`: they are the record of what the model answered.

## Upgrading

Install the new version, then run `aidlc sync-ci --install "…"` and
`aidlc init --assistant …` again. Both only change files the kit owns.
