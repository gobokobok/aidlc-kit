"""Reviews: submit, approve, reject, GitHub review sync, and the
`approvals_complete` check.

Approvals are recorded in each artifact's frontmatter, but a name in a file
can be typed by anyone. The check therefore only counts a recorded approval
when GitHub confirms that person approved the pull request at a commit where
the artifact had the same version.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime

from aidlc import artifacts as art
from aidlc import reviewers, risk
from aidlc.artifacts import Approval, Artifact
from aidlc.config import ANY_REVIEWER, Config, Tier
from aidlc.gitops import Review
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


def pr_title(feature: Feature, branch: str = "") -> str:
    if branch.startswith("decompose/"):
        return f"{feature.id}: technical plan for {feature.title}"
    return f"{feature.id}: {feature.title}"


def pr_body(feature: Feature, items: list[Artifact], config: Config, tier: Tier | None,
            plan: ReviewPlan, flags: list[str] | tuple[str, ...] = ()) -> str:
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
    if flags:
        lines += ["", "### Flagged for the reviewer", ""] + [f"- {f}" for f in flags]
    report = feature.path / "evals" / "report.md"
    lines += ["", "### Eval report", ""]
    lines.append(report.read_text(encoding="utf-8").strip() if report.is_file() else "_Not run yet._")
    lines += ["", "### Reviewers", "", reviewer_message(plan, tier), "",
              "Approve or reject in your IDE with `/approve` or `/reject`, or here on GitHub.",
              "", f"_Generated by {config.display_name}._"]
    return "\n".join(lines) + "\n"


# --- approve and reject ----------------------------------------------------

@dataclass(frozen=True)
class Decision:
    artifact: Artifact               # after the decision
    roles: tuple[str, ...]           # roles the reviewer acted for
    complete: bool                   # every required role is now satisfied


@dataclass(frozen=True)
class Outcome:
    done: list[Decision]
    skipped: list[tuple[str, str]]   # (artifact ID, plain reason)


def _targets(items: list[Artifact], ids: list[str] | None) -> tuple[list[Artifact], list[tuple[str, str]]]:
    if not ids:
        return [a for a in sorted(items, key=sort_key) if a.status == "in_review"], []
    by_id = {a.id: a for a in items}
    found = [by_id[i] for i in dict.fromkeys(ids) if i in by_id]
    return found, [(i, "there is no such item in this feature") for i in ids if i not in by_id]


def _reviewable(config: Config, a: Artifact, user: str, tier: Tier | None,
                approving: bool) -> tuple[list[str], str | None]:
    """Roles `user` can act for on `a`, or why they cannot review it."""
    if a.owner == user:
        return [], "you wrote it, so someone else has to review it"
    pending = reviewers.pending(config, a, tier)
    if a.status == "approved" and not pending and approving:
        return [], "it is already fully approved"
    reasons = {"draft": "it is a draft and has not been submitted for review",
               "stale": "it is out of date and has to be updated first",
               "rejected": "it was rejected and needs a new version first"}
    if a.status in reasons:
        return [], reasons[a.status]
    if approving and any(ap.by == user for ap in a.approved_current):
        return [], f"you already approved v{a.version}"
    checks = pending if approving else reviewers.role_checks(config, a, tier)
    roles = [c.role for c in checks if reviewers.holds(config, user, c.role, a.owner)]
    if not roles:
        needed = review_needs(pending) or "no further approvals"
        return [], f"it needs {needed}, and you do not have that role in aidlc.yaml"
    return roles, None


def review_needs(checks: list[reviewers.RoleCheck]) -> str:
    return join([reviewers.role_label(c.role) for c in checks])


def _settle(config: Config, a: Artifact, tier: Tier | None) -> Artifact:
    """Mark an in-review artifact approved once every role is satisfied.
    Approving the risk profile fixes its tier as the approved one."""
    if a.status != "in_review" or not reviewers.roles_complete(config, a, tier):
        return a
    extra = a.extra
    if a.type == "risk":
        extra = {**extra, "approved_tier": extra["declared_tier"]}
    return replace(a, status="approved", extra=extra)


def settle_all(config: Config, items: list[Artifact]) -> list[Artifact]:
    """Settle every item; the risk profile first, as its tier affects the rest."""
    current = {a.id: a for a in items}
    for a in sorted(items, key=lambda x: x.type != "risk"):
        current[a.id] = _settle(config, current[a.id], risk.feature_tier(list(current.values()), config))
    return [current[a.id] for a in items]


def _save_changed(before: list[Artifact], after: list[Artifact]) -> None:
    old = {a.id: a for a in before}
    for a in after:
        if a != old.get(a.id):
            art.save(a)


def approve(config: Config, items: list[Artifact], user: str, ids: list[str] | None,
            now: datetime) -> Outcome:
    tier = risk.feature_tier(items, config)
    targets, skipped = _targets(items, ids)
    current = {a.id: a for a in items}
    acted: dict[str, tuple[str, ...]] = {}
    for a in targets:
        roles, why = _reviewable(config, a, user, tier, approving=True)
        if why:
            skipped.append((a.id, why))
            continue
        current[a.id] = replace(a, approvals=a.approvals + (Approval(user, a.version, now),))
        acted[a.id] = tuple(roles)
    settled = settle_all(config, list(current.values()))
    _save_changed(items, settled)
    final = {a.id: a for a in settled}
    new_tier = risk.feature_tier(settled, config)
    done = [Decision(final[i], roles, reviewers.roles_complete(config, final[i], new_tier))
            for i, roles in acted.items()]
    return Outcome(done, skipped)


def reject(config: Config, items: list[Artifact], user: str, ids: list[str] | None,
           reason: str, now: datetime) -> Outcome:
    if not reason.strip():
        raise WorkspaceError("Say why, in a sentence, so the author knows what to change.")
    tier = risk.feature_tier(items, config)
    targets, skipped = _targets(items, ids)
    done = []
    for a in targets:
        roles, why = _reviewable(config, a, user, tier, approving=False)
        if why:
            skipped.append((a.id, why))
            continue
        note = {"by": user, "version": a.version, "at": art.format_ts(now), "reason": reason.strip()}
        after = replace(
            a, status="rejected",
            approvals=tuple(ap for ap in a.approvals if not (ap.by == user and ap.version == a.version)),
            extra={**a.extra, "rejections": [*a.extra.get("rejections", []), note]})
        art.save(after)
        done.append(Decision(after, tuple(roles), False))
    return Outcome(done, skipped)


# --- GitHub reviews ---------------------------------------------------------

VersionAt = Callable[[str, Artifact], int | None]  # (commit, artifact) -> its version there


def _parse_time(text: str, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return fallback


def sync_github_reviews(config: Config, items: list[Artifact], reviews: list[Review],
                        version_at: VersionAt, now: datetime) -> list[tuple[Artifact, str]]:
    """Record approvals given on the GitHub pull request screen. An approval
    counts for each item in review where the person holds a role still needed,
    at the version they saw. Returns (artifact, login) pairs recorded."""
    current = {a.id: a for a in items}
    recorded: list[tuple[str, str]] = []
    for r in sorted(reviews, key=lambda r: r.submitted_at):
        if r.state != "APPROVED":
            continue
        for aid in list(current):
            a = current[aid]
            tier = risk.feature_tier(list(current.values()), config)
            if (a.status not in ("in_review", "approved") or a.owner == r.login
                    or any(ap.by == r.login for ap in a.approved_current)
                    or not any(reviewers.holds(config, r.login, c.role, a.owner)
                               for c in reviewers.pending(config, a, tier))
                    or version_at(r.commit_id, a) != a.version):
                continue
            current[aid] = replace(a, approvals=a.approvals + (
                Approval(r.login, a.version, _parse_time(r.submitted_at, now)),))
            recorded.append((aid, r.login))
    settled = settle_all(config, list(current.values()))
    _save_changed(items, settled)
    final = {a.id: a for a in settled}
    return [(final[aid], login) for aid, login in recorded]


def changes_requested(reviews: list[Review]) -> list[Review]:
    """People whose latest review on GitHub asks for changes."""
    latest: dict[str, Review] = {}
    for r in sorted(reviews, key=lambda r: r.submitted_at):
        if r.state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[r.login] = r
    return [r for r in latest.values() if r.state == "CHANGES_REQUESTED"]


# --- approvals_complete -----------------------------------------------------

@dataclass(frozen=True)
class CheckResult:
    checked: list[str]
    problems: list[str]
    notes: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def approvals_check(
    config: Config,
    changed: list[Artifact],
    feature_items: dict[str, list[Artifact]],
    reviews: list[Review],
    version_at: VersionAt,
    base_approved_tier: dict[str, str | None],
) -> CheckResult:
    """For every non-draft artifact changed in the PR: every required role is
    satisfied on the current version by an approval GitHub confirms, and the
    approver is not the owner. `config` must come from the base branch, so a
    PR cannot grant itself reviewers."""
    problems: list[str] = []
    notes: list[str] = []
    checked: list[str] = []
    for a in sorted(changed, key=sort_key):
        if a.status == "draft":
            continue
        label = f"{a.feature}/{a.id} v{a.version}"
        checked.append(label)
        tier = risk.feature_tier(feature_items.get(a.feature, [a]), config)

        def confirmed(login: str) -> bool:
            return any(r.login == login and r.state == "APPROVED"
                       and version_at(r.commit_id, a) == a.version for r in reviews)

        backed = []
        for ap in a.approved_current:
            if ap.by == a.owner:
                problems.append(f"{label}: {ap.by} approved their own work.")
            elif not confirmed(ap.by):
                problems.append(f"{label}: the file records an approval by {ap.by}, but {ap.by} "
                                "has not approved this pull request on GitHub at this version.")
            else:
                backed.append(ap)
        checked_a = replace(a, approvals=tuple(backed))
        pending = reviewers.pending(config, checked_a, tier)
        for c in pending:
            who = ", ".join(c.candidates) or "nobody has this role in aidlc.yaml"
            extra = "" if c.reason == "routing" else f" ({config.tier(c.reason).display})"
            problems.append(f"{label}: still needs {reviewers.role_label(c.role)} approval{extra}: {who}.")
            for login in {r.login for r in reviews if r.state == "APPROVED"}:
                if (login not in {ap.by for ap in a.approved_current} and confirmed(login)
                        and reviewers.holds(config, login, c.role, a.owner)):
                    notes.append(f"{label}: {login} approved on GitHub; the PM's next /status records it.")
        if a.status in ("rejected", "stale"):
            problems.append(f"{label}: is {a.status}; it needs a new version before it can merge.")
        elif a.status == "in_review" and not pending:
            problems.append(f"{label}: has every approval but is still marked in review; "
                            "run /status to record it.")
        if a.type == "risk":
            before = base_approved_tier.get(a.feature)
            if a.extra.get("approved_tier") != before and (a.status != "approved" or pending):
                problems.append(f"{label}: approved_tier changed from {before} to "
                                f"{a.extra.get('approved_tier')} without an approved risk review.")
    return CheckResult(checked, problems, sorted(set(notes)))
