# AIDLC Kit

Take a feature from discovery to an engineering-ready handoff from your IDE,
in plain language, without touching Git, with whichever AI assistant you
already use, or none.

> Work in progress. Build steps 1 to 7 of 8 are done: artifact model,
> validator, risk tiers, reviewer routing, CLI, chat commands for several
> assistants, review and approval, CODEOWNERS, CI checks, the audit log,
> golden-set evals, the handoff gate and package, technical plans, a
> worked example, and the read-only viewer site.
> Full setup and demo instructions arrive with step 8.

**Worked example.** `features/FEAT-001-guest-request-triage/` is a complete
Tier 2 feature recorded on this repository: discovery, three requirements, two
criteria, a prompt, a 20-case golden set with saved Claude answers, reviews
including the risk reviewer, a handoff package, and a technical plan (see
[PR 1](https://github.com/gobokobok/aidlc-kit/pull/1) and
[PR 2](https://github.com/gobokobok/aidlc-kit/pull/2)). Two GitHub accounts
play all the roles, so it shows the mechanism, not independent review. CI
replays the saved answers and needs no API key. How the same feature changes at
Tier 3: `docs/example-tier3.md`.

## Set up a repository

```bash
pip install aidlc-kit            # not published yet; for now: pip install -e <path to this repo>
aidlc init --assistant copilot   # or claude, cursor, agents, vscode; repeat for several
gh auth login                    # once per person
```

| `--assistant` | What it writes |
|---|---|
| `claude` | `.claude/commands/`, AIDLC block in `CLAUDE.md` |
| `copilot` | `.github/prompts/`, AIDLC block in `.github/copilot-instructions.md` |
| `cursor` | `.cursor/commands/`, `.cursor/rules/aidlc.mdc` |
| `agents` | AIDLC block in `AGENTS.md`, for any assistant that reads it |
| `vscode` | AIDLC tasks in `.vscode/tasks.json`, for working with no assistant |

Your own content in shared files is kept; only the marked AIDLC block is
replaced when you run `init` again. `init` also writes the CI workflows and
the AIDLC part of `.github/CODEOWNERS`.

Then, on GitHub, protect `main`: require a pull request with 1 approval and
code owner review, require the checks `validate`, `eval` and `approvals_complete`,
and let GitHub Actions bypass the pull request rule so the `audit` job can
append to the audit log.

## Live evals (optional)

CI runs evals from saved model answers only: no API key, no cost. To create
those answers, someone runs `/eval --live` once per prompt change. Configure
the provider in `aidlc.yaml` and install its SDK:

```yaml
eval:
  provider: anthropic          # or openai, openai_compatible (with base_url)
  model: claude-opus-5-5
  api_key_env: ANTHROPIC_API_KEY
```

```bash
pip install 'aidlc-kit[anthropic]'   # or 'aidlc-kit[openai]'
```

## Commands so far

| Chat command | CLI | What it does |
|---|---|---|
| `/new-feature` | `aidlc new-feature` | Open a feature, answer the risk questions, get a tier |
| `/discover` | `aidlc discover` | Write the discovery brief |
| `/requirement` | `aidlc requirement` | Write a requirement |
| `/criteria` | `aidlc criteria` | Write acceptance criteria with thresholds |
| `/asset` | `aidlc asset` | Define the prompt and AI behaviour |
| `/privacy` | `aidlc privacy` | Write the privacy assessment (Tier 3) |
| `/risk` | `aidlc risk` | Show or revise the risk profile |
| `/change` | `aidlc change <ID>` | Edit an item; reviewed items get a new version |
| `/eval` | `aidlc golden`, `aidlc eval [--live]` | Save the golden set and test the prompt against the criteria |
| `/submit` | `aidlc submit` | Send drafts for review and ask the right people |
| `/handoff` | `aidlc handoff` | Check the hard gate, build the package for engineering, then merge and tag it |
| `/decompose` | `aidlc decompose` | Engineer: start the technical plan from the package, with tasks tied to criteria |
| `/approve` | `aidlc approve [ID ...]` | Reviewer: approve what is waiting for your role |
| `/reject` | `aidlc reject ID --reason ...` | Reviewer: reject and say what must change |
| `/reviewers` | `aidlc reviewers` | Who still has to approve what |
| `/status` | `aidlc status` | Where the feature stands and what is next |

## The viewer site

`aidlc site build --out site` writes a read-only site: every feature with its
risk tier badge and stage, who still has to approve each item (✓ approved, …
waiting), what blocks handoff, the trace from discovery to tasks, eval
results, and the audit timeline. It is plain HTML with light and dark mode and
works on a phone; open `site/index.html`. The `AIDLC site` workflow publishes
it to GitHub Pages after each merge to `main` (set Pages > Source to
"GitHub Actions" once).

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/aidlc validate
```

See [CLAUDE.md](CLAUDE.md) for the build spec (it is not shipped) and
[docs/decisions.md](docs/decisions.md) for design decisions.
