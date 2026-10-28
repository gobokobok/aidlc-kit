"""Review requests: what to submit, who to ask and why, the PR description.

Approve and reject arrive in build step 3.
"""

from dataclasses import dataclass, field, replace

from aidlc import artifacts as art
from aidlc import reviewers, risk
from aidlc.artifacts import Artifact
from aidlc.config import ANY_REVIEWER, Config, Tier
from aidlc.workspace import Feature, WorkspaceError, sort_key


@dataclass
class ReviewRequest:
    person: str
    roles: list[str] = field(default_factory=list)
    tier_roles: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewPlan:
    requests: list[ReviewRequest]
    unfilled: list[str]          # roles that nobody in aidlc.yaml holds
    open_to_anyone: list[str]    # artifacts any other person may approve


def join(words: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def mark_submitted(items: list[Artifact]) -> list[Artifact]:
    """Move drafts to in_review and save them. Stale items cannot be
    submitted: they must be brought up to date first."""
    stale = [a.id for a in items if a.status == "stale"]
    if stale:
        raise WorkspaceError(
            f"{join(stale)} {'is' if len(stale) == 1 else 'are'} out of date because something "
            "they build on changed. Update with /change first, then /submit.")
    submitted = []
    for a in sorted(items, key=sort_key):
        if a.status == "draft":
            updated = replace(a, status="in_review")
            art.save(updated)
            submitted.append(updated)
    return submitted


def plan_reviews(config: Config, items: list[Artifact], tier: Tier | None, submitter: str) -> ReviewPlan:
    """Who has to be asked, for which roles, across everything in review."""
    requests: dict[str, ReviewRequest] = {}
    unfilled: list[str] = []
    anyone: list[str] = []
    for a in sorted(items, key=sort_key):
        if a.status != "in_review":
            continue
        for check in reviewers.pending(config, a, tier):
            if check.role == ANY_REVIEWER:
                anyone.append(a.id)
                continue
            people = [p for p in check.candidates if p != submitter]
            if not people and check.role not in unfilled:
                unfilled.append(check.role)
            for person in people:
                req = requests.setdefault(person, ReviewRequest(person))
                target = req.tier_roles if check.reason != "routing" else req.roles
                if check.role not in target:
                    target.append(check.role)
                if a.id not in req.artifacts:
                    req.artifacts.append(a.id)
    return ReviewPlan(list(requests.values()), unfilled, anyone)


def _who(req: ReviewRequest) -> str:
    roles = list(dict.fromkeys(req.roles + req.tier_roles))
    return f"{req.person} ({', '.join(reviewers.role_label(r) for r in roles)})"


def reviewer_message(plan: ReviewPlan, tier: Tier | None) -> str:
    """e.g. 'Sent to bob (Ops) and priya (Tech). sam (Risk) is included
    because this feature is Tier 2.'"""
    main = [r for r in plan.requests if not r.tier_roles]
    extra = [r for r in plan.requests if r.tier_roles]
    because = f"because this feature is Tier {tier.rank}" if tier else "because of its risk tier"
    parts = []
    if main:
        parts.append(f"Sent to {join([_who(r) for r in main])}.")
        if extra:
            verb = "is" if len(extra) == 1 else "are"
            parts.append(f"{join([_who(r) for r in extra])} {verb} included {because}.")
    elif extra:
        parts.append(f"Sent to {join([_who(r) for r in extra])}, included {because}.")
    if plan.open_to_anyone:
        parts.append(f"Anyone other than you can approve {join(plan.open_to_anyone)}.")
    if plan.unfilled:
        labels = join([reviewers.role_label(r) for r in plan.unfilled])
        parts.append(f"Nobody in aidlc.yaml has the {labels} role yet, so ask whoever "
                     "looks after that file to add someone.")
    return " ".join(parts) or "Nobody else needs to approve anything right now."


def pr_title(feature: Feature) -> str:
    return f"{feature.id}: {feature.title}"


def pr_body(feature: Feature, items: list[Artifact], config: Config, tier: Tier | None,
            plan: ReviewPlan) -> str:
    """The review request: risk answers next to the tier, then each item."""
    lines = [f"## {feature.id}: {feature.title}", ""]
    lines.append(f"Risk: **{tier.display}**" if tier else "Risk: **no valid risk profile yet**")
    profile = next((a for a in items if a.type == "risk"), None)
    if profile and tier:
        lines += ["", f"### Risk profile ({profile.id} v{profile.version})",
                  "Reviewers: please challenge these answers, not just the tier.", ""]
        lines += risk.describe(profile, config)
    lines += ["", "### Items", "", "| Item | Title | Version | Status | Still needs |",
              "|---|---|---|---|---|"]
    for a in sorted(items, key=sort_key):
        pending = [reviewers.role_label(c.role) for c in reviewers.pending(config, a, tier)]
        lines.append(f"| {a.id} | {a.title} | v{a.version} | {a.status} | "
                     f"{', '.join(pending) if pending else '—'} |")
    report = feature.path / "evals" / "report.md"
    lines += ["", "### Eval report", ""]
    lines.append(report.read_text(encoding="utf-8").strip() if report.is_file() else "_Not run yet._")
    lines += ["", "### Reviewers", "", reviewer_message(plan, tier), "",
              "Approve or reject in your IDE with `/approve` or `/reject`, or here on GitHub.",
              "", f"_Generated by {config.display_name}._"]
    return "\n".join(lines) + "\n"
