# AIDLC Kit

Take a feature from discovery to an engineering-ready handoff from your IDE,
in plain language, without touching Git, with whichever AI assistant you
already use, or none.

Underneath, the kit handles versioning, ownership, review and approval, an audit
trail, traceability, golden-set evaluation of the AI behaviour, and the handoff
to engineering. Product Managers write; named reviewers approve; one gate
decides whether a feature is ready to leave.

**Status:** version 0.1, all eight build steps done. It is not on PyPI yet, and
it has run end to end on one real repository, with two accounts belonging to
one person (see [limitations](docs/limitations.md)).

- **Live example:** https://gobokobok.github.io/aidlc-kit/
- **Docs:** [overview](docs/overview.md) · [quickstart](docs/quickstart.md) · [testing guide](docs/testing-guide.md) · [architecture](docs/architecture.md) · [workflow](docs/workflow.md) · [setup](docs/setup.md) · [trade-offs](docs/trade-offs.md) · [limitations](docs/limitations.md) · [demo script](docs/demo.md) · [decisions](docs/decisions.md)

## Set up a repository

Three steps. Python 3.12 and the GitHub CLI are needed.

```bash
pip install git+https://github.com/gobokobok/aidlc-kit@v0.1.0      # 1. install
aidlc init --assistant claude --assistant vscode \
  --install "pip install git+https://github.com/gobokobok/aidlc-kit@v0.1.0"   # 2. set up this repository
gh auth login                                                       # 3. once per person
```

`--assistant` can be `claude`, `copilot`, `cursor`, `agents` or `vscode`; repeat
it for several. `init` writes `aidlc.yaml`, the CI workflows, `CODEOWNERS` and
the files each assistant needs, and never overwrites your own content in shared
files.

| `--assistant` | What it writes |
|---|---|
| `claude` | `.claude/commands/`, AIDLC block in `CLAUDE.md` |
| `copilot` | `.github/prompts/`, AIDLC block in `.github/copilot-instructions.md` |
| `cursor` | `.cursor/commands/`, `.cursor/rules/aidlc.mdc` |
| `agents` | AIDLC block in `AGENTS.md`, for any assistant that reads it |
| `vscode` | AIDLC tasks in `.vscode/tasks.json`, for working with no assistant |

Then put your team in `aidlc.yaml` and protect `main`. The kit is not on PyPI, so
`--install` tells CI where to get it. Start with [docs/quickstart.md](docs/quickstart.md);
the details are in [docs/setup.md](docs/setup.md).

## Try it: a five-minute demo

The repository contains a finished example, **FEAT-001 Guest request triage**:
discovery, three requirements, two criteria, a prompt, a 20-case golden set with
saved Claude answers, reviews including the risk reviewer, a handoff package and
a technical plan ([PR 1](https://github.com/gobokobok/aidlc-kit/pull/1),
[PR 2](https://github.com/gobokobok/aidlc-kit/pull/2)); a frozen copy is in
[examples/guest-request-triage](examples/guest-request-triage). To see it:

1. Open the [viewer site](https://gobokobok.github.io/aidlc-kit/): the Tier 2
   badge, the stage bar, who approved each item.
2. Open **Trace** and **Evals** on the feature page.
3. Clone the repository and run `aidlc --root examples/guest-request-triage status`
   and `… reviewers`.
4. Start a new feature and run `aidlc handoff` to see the gate refuse it and say
   who can fix each thing.

The full script, with timings and commands, is [docs/demo.md](docs/demo.md). How
the same feature changes at Tier 3 is in [docs/example-tier3.md](docs/example-tier3.md).

## Commands

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
| — | `aidlc validate` | Check every item; `--write` records computed stale statuses |
| — | `aidlc site build` | Build the read-only viewer site |

Every chat command is a thin wrapper over the `aidlc` command beside it, so a
terminal or a VS Code task does the same thing. `aidlc --help` lists them all.

## Live evals (optional)

CI runs evals from saved model answers only: no API key, no cost. To create
those answers, someone runs `/eval --live` once per prompt change. Configure
the provider in `aidlc.yaml` and install its SDK:

```yaml
eval:
  provider: anthropic          # or openai, openai_compatible (with base_url)
  model: <model id>
  api_key_env: ANTHROPIC_API_KEY
```

```bash
pip install 'aidlc-kit[anthropic]'   # or 'aidlc-kit[openai]'
```

## The viewer site

`aidlc site build --out site` writes a read-only site: every feature with its
risk tier badge and stage, who still has to approve each item (✓ approved, …
waiting), what blocks handoff, the trace from discovery to tasks, eval results,
and the audit timeline. It is plain HTML with light and dark mode and works on
a phone. The `AIDLC site` workflow publishes it to GitHub Pages after each merge
to `main` (set Pages > Source to "GitHub Actions" once).

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/aidlc validate
```

[CLAUDE.md](CLAUDE.md) is the build spec used to build the kit; it is not part of
the package. [docs/decisions.md](docs/decisions.md) logs the design decisions.
