# AIDLC Kit

Take a feature from discovery to an engineering-ready handoff from your IDE,
in plain language, without touching Git, with whichever AI assistant you
already use, or none.

> Work in progress. Build steps 1 to 3 of 8 are done: artifact model,
> validator, risk tiers, reviewer routing, CLI, chat commands for several
> assistants, review and approval, CODEOWNERS, CI checks and the audit log.
> Full setup and demo instructions arrive with step 8.

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
code owner review, require the checks `validate` and `approvals_complete`,
and let GitHub Actions bypass the pull request rule so the `audit` job can
append to the audit log.

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
| `/submit` | `aidlc submit` | Send drafts for review and ask the right people |
| `/approve` | `aidlc approve [ID ...]` | Reviewer: approve what is waiting for your role |
| `/reject` | `aidlc reject ID --reason ...` | Reviewer: reject and say what must change |
| `/reviewers` | `aidlc reviewers` | Who still has to approve what |
| `/status` | `aidlc status` | Where the feature stands and what is next |

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/aidlc validate
```

See [CLAUDE.md](CLAUDE.md) for the build spec (it is not shipped) and
[docs/decisions.md](docs/decisions.md) for design decisions.
