---
description: Approve items waiting for your review
argument_hint: <item IDs, or empty for everything waiting for you>
---
{{ rules_ref }}

The reviewer wants to approve: {{ args }}

0. If several features are open for review, or the reviewer names one (such as
   FEAT-002), add `--feature FEAT-002` to every command below. The tool opens
   the feature's review branch itself; never run `git` for the reviewer.
1. Run `aidlc reviewers` to see what is waiting for them and which role they
   review as.
2. Read each item they are about to approve (its file under `features/`) and,
   for criteria and assets, the eval report in the feature's `evals/` folder if
   there is one. Summarise each in two or three plain sentences, and point out
   anything incomplete or inconsistent with what it builds on. For the risk
   profile, show the answers next to the tier and flag any answer that seems
   doubtful: challenging the answers is the risk reviewer's job.
3. Ask the reviewer to confirm. Approve only what they confirm:
   `aidlc approve <ID> [<ID> ...]`.
4. Relay what was approved, what is now fully approved, and who is still needed.
