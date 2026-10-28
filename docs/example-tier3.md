# The same feature at Tier 3

FEAT-001 (guest request triage) is Tier 2: the AI suggests, staff confirm.
This page shows what changes if the hotel decides the AI should **act on its
own**: send the dispatch and a first reply to the guest without a person
checking first. The messages below are the kit's real output for that change,
run against the worked example.

## What triggers it

The PM revises the risk profile with `/risk` and answers "Act on its own
without a person checking first":

> RISK-001 is now v2. The answers make it Tier 3 (High) because it acts on its
> own with personal data.

The rule is deterministic (`aidlc/risk.py`): acting autonomously on personal or
confidential data is Tier 3, so is any payment data or a regulated decision.
Everything already approved stays approved, but handoff waits.

## What changes

| | Tier 2 (as built) | Tier 3 |
|---|---|---|
| Who reviews every item | the routed roles plus Risk (sam) | plus the data owner (lee) |
| Extra document | none | a privacy assessment (PIA), approved |
| Accuracy minimum | 0.85 | **0.95** |
| Person checks the AI output | optional (we do it) | **required**, written in the prompt |
| Risk profile review | Risk | Risk, and the risk profile is challenged again as v2 |

## What the PM sees

`/eval` stops the old thresholds from passing:

> Evals fail: … AC-001 sets accuracy 0.9, below the Tier 3 (High) minimum of
> 0.95; tighten it with /change AC-001.

`/handoff` lists everything in the way and who can fix it:

> Not ready for handoff yet. What is in the way:
> ✗ Tier 3 (High) needs a privacy assessment. alice can write it with /privacy.
> ✗ ASSET-001: Tier 3 (High) needs a person to check the AI output, and no
>   human review step is described. alice can add it with
>   /change ASSET-001 --human-review-step.
> ✗ RISK-001 v2: is a draft that was never submitted. alice can send it for
>   review with /submit.
> ✗ REQ-001 v1: still needs Data owner approval, which Tier 3 (High) adds.
>   lee (Data owner) can approve it with /approve.
> … (the same for every other item)

## What it takes to get through

1. `/privacy` writes PIA-001 (data involved, purpose and basis, minimisation,
   retention and access, risks), linked to the discovery brief and the risk
   profile. It needs Risk and Data owner approval like everything else.
2. `/change AC-001` raises the accuracy threshold to 0.95. The recorded
   example already scores 1.0 on its 20 cases, so the new threshold would pass
   once the criterion is reapproved. Twenty cases is a small sample: at this
   tier the golden set should grow before the number means much.
3. `/change ASSET-001 --human-review-step "..."` names who checks the output
   and when. For an AI that acts on its own this is usually a sampling review
   after the fact, so the PM and the data owner should agree on what that
   means before writing it.
4. Risk (sam) approves RISK-001 v2, then the data owner (lee) approves every
   item, including the risk profile and the privacy assessment.
5. `/handoff` then builds the package as usual; Tier 3 adds the data owner to
   the people who must accept it.

Nothing here makes the data safer by itself. The kit makes sure the right
people looked, in writing, before handoff; the controls on the data are still
yours to build (see `limitations.md`).
