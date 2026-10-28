# Five-minute demo

Shows a feature that went from idea to an engineering handoff, who approved
each step, and the one gate that stops a feature that is not ready. It uses
the worked example in this repository, so nothing is staged.

## Before you start (once, two minutes)

```bash
git clone https://github.com/gobokobok/aidlc-kit demo && cd demo
python3.12 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/aidlc --help
```

Have `gh auth login` done, and open these in tabs:

- the viewer site: https://gobokobok.github.io/aidlc-kit/
- the feature's review request: https://github.com/gobokobok/aidlc-kit/pull/1

## The script

**0:00. The problem and the answer.**
"A PM can take an AI feature from an idea to an engineering handoff from the
IDE, in plain language, with no Git. Underneath, every step is versioned, has
an owner, is reviewed by the right people, and leaves an audit trail."
Open the site. Point at the card: FEAT-001, a **Tier 2** badge, and the stage
bar running from Risk to Plan.

**0:45. Risk decides who reviews.** Open the feature. Read the risk profile:
personal data, customer-facing, the AI only suggests, so Tier 2. Scroll to the
items. "Every item shows who must approve it. ✓ means approved for this exact
version, … means still waiting. The risk reviewer appears on everything
because Tier 2 adds that role. At Tier 3 the data owner would be added too."

**1:45. Traceability.** Open **Trace**. "Each task points to the criterion it
satisfies, each criterion to a requirement, each requirement to the
discovery brief. If anything upstream changes, everything built on it goes
stale until someone updates it."

**2:30. Proof the AI meets the bar.** Open **Evals**. "Twenty test messages.
Each criterion has thresholds, for example urgent messages must be caught at
least 95% of the time and no safety case may be wrong. These answers are
saved from a real model run, so CI replays them for free and gets the same
result every time." Point at the model name and the first prompt's failed run
in the history if asked: the prompt was fixed, not the test cases.

**3:15. The same facts from the terminal.**

```bash
.venv/bin/aidlc status
.venv/bin/aidlc reviewers
```

`status` lists every item with its version and status and ends with "Handed off
as HND-001 and planned." `reviewers` shows the ✓ per role for each item. Say:
"A PM sees this from the chat window too: the same commands, in plain words."

**3:45. The gate.** Start a new feature and try to hand it off immediately:

```bash
.venv/bin/aidlc new-feature --title "Demo: refund triage" \
  --data-classes personal --autonomy suggest --audience customer_facing \
  --regulated-decision no --rationale "Messages hold names."
.venv/bin/aidlc handoff
```

The kit opens FEAT-002 as Tier 2, then refuses the handoff and lists what is
in the way and who can fix it, for example:
"✗ Feature: there is no discovery yet. gobokobok can add it with /discover."
"Handoff is the one hard gate: drafts are free, but nothing leaves for
engineering until everything is approved, up to date and the evals pass."

**4:30. What GitHub shows.** Open pull request 1. "The reviews are real GitHub
reviews, and the `approvals_complete` check confirmed each approval with
GitHub rather than trusting the file. Merges go through branch protection."
Open `audit/log.jsonl` in the repository: "One line per item when it reached
`main`: who, which version, which approvers, which roles, which commit."

**4:50. Close.** "Any assistant, or none; one command-line tool holds the
rules. The caveat to say out loud: this proves the process was followed, not
that the data controls underneath are sound."

## Clean up

```bash
git switch main
git branch -D feat/FEAT-002
```

## If something goes wrong

- The site tab is blank: build it locally with `.venv/bin/aidlc site build`
  and open `site/index.html`.
- `aidlc new-feature` says it cannot find who you are: run `gh auth login`.
- You are short on time: skip the terminal part and keep the site, the gate
  and the pull request.
