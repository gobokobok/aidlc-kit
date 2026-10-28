# AIDLC Kit

Take a feature from discovery to an engineering-ready handoff from your IDE,
in plain language, without touching Git.

> Work in progress. Build steps 1 and 2 of 8 are done: artifact model,
> validator, risk tiers, reviewer routing, CLI and slash commands.
> Full setup and demo instructions arrive with step 8.

## Commands so far

| Slash command | CLI | What it does |
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
| `/reviewers` | `aidlc reviewers` | Who still has to approve what |
| `/status` | `aidlc status` | Where the feature stands and what is next |

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/aidlc validate
```

See [CLAUDE.md](CLAUDE.md) for the build spec and
[docs/decisions.md](docs/decisions.md) for design decisions.
