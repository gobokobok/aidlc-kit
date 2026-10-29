# Testing guide: run AIDLC Kit end to end in your organisation

**Goal:** find out whether the kit works for your company, with your people, in
VS Code, on a real feature. Allow half a day. Every test below has an expected
result; record pass or fail in section 9 and send it back.

**You will end with:** a real feature taken from idea to handoff and a
technical plan, reviewed by real people, with the audit trail and the viewer
site to show for it, and a list of what was rough.

## 1. Who takes part

| Test role | Needs | Example |
|---|---|---|
| **Admin** | admin rights on the new repository | whoever sets it up |
| **PM A** (author) | role `pm` | you |
| **PM B** (peer) | role `pm`; may also hold `ops_reviewer` | your colleague |
| **Reviewers** | `tech_reviewer`; `ops_reviewer`; `risk_reviewer` (needed from Tier 2 up) | engineering lead, ops lead, risk or compliance |
| **Engineer** | role `engineer` | someone from the engineering team |

Four to five real people is ideal. **Two GitHub accounts is the minimum**: one
writes everything, the other holds every reviewer role (this is how the kit's own
example was made). The second account also needs role `pm`, so discovery can get a PM-peer approval. It proves the mechanism but not the hand-offs between people,
so test sections 5 and 7 with real colleagues if you can.
Each person needs their **own** GitHub account and their own machine. Nobody
shares a login: the kit knows who approves from the GitHub login.

## 2. Before you start

- [ ] Python 3.12, Git, `pipx` and the GitHub CLI installed; `gh auth login` done by each person (`gh auth status` shows their own name).
- [ ] VS Code with **GitHub Copilot Chat** (or the Claude Code extension), or neither: the kit also runs from VS Code tasks.
- [ ] A new, empty GitHub repository in your organisation with default branch `main`, and everyone above added as a collaborator with **Write** access. Use a throwaway name such as `aidlc-pilot`.
- [ ] If you will record eval answers: an API key for your model provider, in an environment variable (for example `ANTHROPIC_API_KEY`), set **before** VS Code starts. Check without printing it: `[ -n "$ANTHROPIC_API_KEY" ] && echo set`. Expect a few cents to a few dollars for the whole test.
- [ ] A feature to test (next section).

**Windows:** the kit has not been tried on Windows. If something fails there,
note it: that is useful information. A Mac, Linux or WSL machine avoids it.

## 3. Choose the feature

The kit tests AI behaviour by sending a message and comparing the model's
**JSON answer** with an expected answer, so pick something that has a clear right
answer: sorting, routing, labelling, extracting fields, yes/no decisions.
Free-form writing cannot be scored this way.

- **Recommended: your own use case**, small enough for 15 to 20 test cases.
  Ask: what comes in, and what fixed fields should the AI return?
- **Quick start: the sample.** The hotel "guest request triage" example has
  every draft ready in `examples/guest-request-triage/drafts/` in the kit
  repository (discovery, three requirements, two criteria, the prompt and 20
  test cases). Paste each into the matching step.

## 4. Part A: install and set up (Admin, about an hour)

Follow [quickstart.md](quickstart.md). Then check:

| # | Check | Expected |
|---|---|---|
| A1 | `aidlc --help` in a new VS Code terminal | The command list appears; no "command not found" |
| A2 | `aidlc validate` after you edit `aidlc.yaml` | "All 0 artifact(s) are valid." and no warnings about missing roles. Fix any warning: it means a role nobody holds |
| A3 | Push to `main`; open the repository's **Actions** tab | `AIDLC validate`, `AIDLC eval` and `AIDLC audit` pass. `AIDLC site` passes only if Pages is on. `eval` says there are no golden sets yet: that is correct |
| A4 | Ruleset on `main` is active | A direct push to `main` by a non-admin is refused |
| A5 | In VS Code Copilot Chat, in **Agent mode**, type `/` | `/new-feature` and the other AIDLC commands are listed. If not, update VS Code and Copilot and reload the window; the **Tasks** route below still works |
| A6 | **Terminal, Run Task** | `AIDLC: /new-feature`, `/status` and the others are listed |
| A7 | Every other person: clone the repository, `gh auth login`, `aidlc --help` | Works, with no kit-specific setup beyond installing it |

## 5. Part B: the PM writes a feature (PM A, in VS Code)

The same step can be run by chat command or by task. The task route works
without any assistant: tasks that "save open file" take the file currently open
in the editor, so write the draft in a scratch file, keep it open, run the task.

| # | Do (chat, or task) | Expected |
|---|---|---|
| B1 | `/new-feature` and answer the four questions about data, autonomy, audience and regulated decisions. Choose answers that give **Tier 2** (for example personal data, AI only suggests, customer-facing) | "Opened FEAT-001 … It is Tier 2 (Medium) because …, so *(risk reviewer)* (Risk) will check the risk profile." The assistant never shows Git |
| B2 | `/discover` with your notes | "Saved DISC-001 … as a draft." |
| B3 | `/requirement` twice or three times | REQ-001…; each "linked to DISC-001" |
| B4 | `/criteria` with thresholds, for example `accuracy=0.9` and `max_unsafe=0` | AC-001 saved, linked to the requirements |
| B5 | `/asset` with the prompt, and say who checks the AI's output | ASSET-001 saved; the prompt sits in a fenced block under `## Prompt` and uses `{{ input }}` |
| B6 | `/eval` and give 15 to 20 cases, each with the input, the expected answer, the criteria it tests, and a `safety` tag on cases where a wrong answer is dangerous | "Saved the golden set: N cases, recorded as EVAL-001" |
| B7 | `/eval` again | It says there are no saved answers yet and asks before spending money. Say yes: "Asking *(provider)* for N case(s)…" then "Evals pass: …" or "Evals fail: …" |
| B8 | If it fails, read the failing cases in `evals/report.md`, improve the **prompt** (not the cases), `/change ASSET-001`, `/eval` again | A pass. A first-time fail is normal and is the point of the step |
| B9 | `/status` | Every item listed with version and status; ends with a plain next step |
| B10 | `/submit` | "Sent to *(names)* … included because this feature is Tier 2. Review request: *(link)*" and a pull request exists on GitHub |

**Check at B1 to B10:** the PM never typed a Git command and never saw Git
output. Note any moment where they had to leave the IDE, other than clicking the
review link.

## 6. Part C: review (reviewers, then PM A)

| # | Do | Expected |
|---|---|---|
| C1 | Reviewer opens the review link, then in their own VS Code (clone on `main`) runs `/reviewers --feature FEAT-001` | They see what is waiting and for which role. The kit fetches the review branch itself; they type no Git |
| C2 | Reviewer runs `/approve` (or `/approve REQ-001`) | The assistant summarises each item and asks to confirm, then: "Approved … as Ops/Tech/Risk. It is on the GitHub review request too." |
| C3 | A second reviewer **approves on the GitHub page** instead (Files changed, Review, Approve) | Accepted. PM A's next `/status` records it |
| C4 | PM A runs `/reviewers` | ✓ or … per role per item, matching who approved |
| C5 | A reviewer runs `/reject REQ-002` with a reason; PM A runs `/status` | The reason is shown to PM A. `/change REQ-002`, then `/submit`; the reviewer approves the new version |
| C6 | Check the pull request's checks | `approvals_complete` is red until every role has approved, then green |

## 7. Part D and E: handoff and engineering

| # | Do | Expected |
|---|---|---|
| D1 | Before everything is approved, PM A runs `/handoff` | "Not ready for handoff yet." with a ✗ line per gap, each naming who can fix it |
| D2 | Approve the rest; `/handoff` | "I built HND-001 for engineering …" and asks the tech reviewer (and risk reviewer, at Tier 2) to accept it |
| D3 | The reviewers `/approve` the package; PM A runs `/handoff` again | "Handed off: FEAT-001 is merged and tagged FEAT-001/handoff-v1." Main now contains the feature; the audit job adds lines to `audit/log.jsonl` |
| E1 | Engineer pulls `main` and runs `/decompose` | "Started DEC-001 from HND-001 …" on a branch `decompose/FEAT-001` |
| E2 | Engineer edits the plan: components, interfaces, risks, and the tasks under `## Tasks`, each naming the criteria it satisfies. Add one task with no criterion on purpose | `/status` and the review request flag that task. Remove the flag by naming a criterion, or leave it for the reviewer to judge |
| E3 | `/submit`, reviewers `/approve`, then merge the pull request on GitHub (**Squash and merge**) | DEC-001 is on `main`; the audit log gains a line |

## 8. Part F: things that must be refused

Do these on a scratch branch or a second feature; none should get through.

| # | Try | Expected |
|---|---|---|
| F1 | PM A runs `/approve REQ-001` on their own item | "Skipped REQ-001: you wrote it, so someone else has to review it." |
| F2 | Approve a Tier 2 item with only the ops reviewer, then look at the pull request | `approvals_complete` stays red and names the missing role |
| F3 | Edit the prompt in `assets/ASSET-001.md` by hand in a pull request and push, without `/eval --live` | The `eval` check fails: the report no longer matches the saved answers |
| F4 | Edit a case in `evals/golden.yaml` by hand and push | `validate` fails: run `/eval` to record the change |
| F5 | Edit a line of `audit/log.jsonl` in a pull request | `validate` fails: "was changed in this pull request. Only CI writes it" |
| F6 | `/change REQ-001` on an approved requirement, then `/status` | REQ-001 is v2 with no approvals; criteria and the prompt built on it are **stale**; `/handoff` refuses until updated |
| F7 | `/risk` and answer "acts on its own" with personal data | "now Tier 3 (High)"; `/handoff` then also needs a privacy assessment, a human review step, a data owner's approval and a 0.95 accuracy minimum |
| F8 | Change `review_routing` in `aidlc.yaml` without running `aidlc sync-codeowners` | `validate` fails: CODEOWNERS does not match |

## 9. Part G: the viewer site, then report back

Open the Pages address (or run `aidlc site build` and open `site/index.html`).

| # | Check | Expected |
|---|---|---|
| G1 | Overview | The feature, its tier badge, stage bar, and handed-off marker |
| G2 | Feature page | Each item with ✓ or … per required role, and the names |
| G3 | Trace, Evals, Audit pages | Tasks trace to criteria; thresholds against results; one audit line per merged item. Check on a phone, and in dark mode |

**Send back, for each test:** pass or fail, the exact message if it differed, and
a screenshot for anything confusing. Also answer:

1. Did any PM have to use Git, a browser or a terminal when they should not have?
2. Which message or step was unclear?
3. Did the reviewers get what they needed to decide, in the IDE or on GitHub?
4. Which setup step cost the most time?
5. Would your PMs use this weekly? What stops them?

## Known limits to expect

The assistant chat commands have not been tried in real Copilot or Cursor
sessions, so a command may be missing or behave oddly: use the VS Code tasks and
report it. Windows is untried. The viewer site shows only what has been merged
to `main`. A reviewer who is not named in `aidlc.yaml` cannot approve for a role.
The kit proves who approved what, not that your data is safe.

## Troubleshooting

| You see | Do |
|---|---|
| `aidlc: command not found` in a task or the assistant | Install with `pipx`, then restart VS Code so it sees the new PATH |
| "Could not find who you are" | `gh auth login` |
| "no cached answer … a live run creates it" | Run `/eval --live`; check the API key variable is visible to VS Code |
| `AIDLC site` fails | Enable Pages (source: GitHub Actions) or delete `aidlc-site.yml` |
| A command says there are conflicts | The kit stops and explains; ask the admin; nothing is lost |
| "Several features are open" | Add `--feature FEAT-001` to the command |

## Clean up

Delete the throwaway repository, and remove the API key from your shell profile
if it was only for this test.
