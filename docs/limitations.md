# Limitations

An honest list, so you can decide whether the kit fits.

## What the kit does not do

- **It records and enforces process. It does not replace data controls.** It
  cannot stop an AI from reading data it should not, and a privacy assessment
  is a document, not a safeguard. Keep your access controls, gateway and
  data-protection work.
- **Roles and tiers are configuration, not an identity system.** Whoever is
  listed under a role in `aidlc.yaml` can approve for it, and the tier comes
  from answers the PM gives. There is no SSO and no identity check beyond the
  GitHub account.
- **Approvals depend on GitHub permissions.** Anyone with admin rights on the
  repository can change the rules, bypass a ruleset or edit `aidlc.yaml`.
  In the worked example the repository admin is also a reviewer.
- **Evals are as good as the golden set.** The example has 20 cases, which
  is enough to show the mechanism and not enough to trust a model. A passing
  eval says the prompt did well on those cases, not that it is safe.
- **Saved answers go out of date.** They record one model on one day. A model
  that changes behind the same name is not noticed until someone runs a live
  eval again.

## Workflow limits

- **Concurrency.** Git is the store. Two people editing the same item, or two
  PMs opening features at the same moment, can conflict; the kit stops and
  explains, and CI rejects duplicate IDs at merge, but it does not prevent the
  collision earlier.
- **One repository.** The kit works inside one repository. Features that span
  repositories, or a company-wide view across many, are not supported.
- **A setup step remains.** Someone installs the kit, runs `aidlc init`,
  protects `main`, and each person runs `gh auth login` once. PMs never type
  Git commands after that, but they do need a working GitHub login.
- **The site shows `main` only.** Open pull requests and branches do not
  appear until they are merged.
- **Handoff is a merge.** Handing off merges the feature into `main` and tags
  it. Further changes start a fresh branch and a new package.
- **A technical plan needs the risk reviewer at Tier 2 and 3**, because plans
  are not in the default routing. Add `decomposition:` to `review_routing` if
  that is more than you want.
- **English only** in the shipped prompts and templates.

## What is not verified

- **The assistant adapters.** The chat commands for Claude Code, Copilot and
  Cursor, the `AGENTS.md` block and the VS Code tasks were generated to each
  tool's documented format and tested for content, and every command is
  checked to call a real `aidlc` command. None has been used in a real
  assistant session: the worked example was driven through the CLI.
- **One repository, one team.** The full path (review, handoff, decomposition,
  audit, site) has run on real GitHub once, for the worked example, with two
  accounts belonging to one person. That shows the mechanism, not how it
  holds up with a team.
- **Personal-repository workarounds.** GitHub does not let GitHub Actions
  bypass rules in a personal repository, so the audit job uses a deploy key.
  An organisation should use the Actions bypass instead. The audit job was not
  re-run under the final protection setting.
- **A rare failure not explained.** `/submit` once failed at "ask reviewers"
  right after opening the pull request and worked on a rerun. It now retries
  once; the cause was not found.
- **Branch protection was not seen blocking a merge.** The checks passed on
  the example's pull requests, and the repository admin can bypass the
  ruleset, so GitHub was never observed refusing one.
- **Live providers.** Only the Anthropic provider has run against a real
  model. The OpenAI and OpenAI-compatible providers are tested with fakes.
