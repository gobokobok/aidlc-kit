"""Approve, reject, GitHub review sync and the approvals_complete check."""

from dataclasses import replace

import pytest

from aidlc import artifacts as art
from aidlc import review
from aidlc.gitops import Review
from aidlc.validate import load_repo, validate_repo
from aidlc.workspace import WorkspaceError

from conftest import T1, config, make, make_risk


def submitted(*items):
    return [replace(a, status="in_review") for a in items]


@pytest.fixture
def feature(repo):
    """A Tier 2 feature with everything in review."""
    items = submitted(
        make_risk(),
        make("DISC-001", "discovery"),
        make("REQ-001", "requirement", parents=(("DISC-001", 1),)),
    )
    repo(*items)
    return repo


def load(repo):
    return {a.id: a for a in load_repo(repo.root)[0]}


# --- approve ---------------------------------------------------------------

def test_approve_records_roles_and_completes(feature):
    items = list(load(feature).values())
    out = review.approve(config(), items, "bob", ["REQ-001"], T1)
    (d,) = out.done
    assert d.roles == ("ops_reviewer",) and not d.complete
    req = load(feature)["REQ-001"]
    assert [(ap.by, ap.version) for ap in req.approvals] == [("bob", 1)]
    assert req.status == "in_review"
    review.approve(config(), list(load(feature).values()), "priya", None, T1)
    out = review.approve(config(), list(load(feature).values()), "sam", None, T1)
    assert {x.artifact.id for x in out.done} == {"RISK-001", "DISC-001", "REQ-001"}
    after = load(feature)
    assert after["REQ-001"].status == "approved"
    assert after["RISK-001"].status == "approved"
    assert after["RISK-001"].extra["approved_tier"] == "T2"
    assert after["DISC-001"].status == "in_review"  # still needs a PM peer
    assert validate_repo(feature.root).ok


def test_approve_skip_reasons(feature):
    items = list(load(feature).values())
    out = review.approve(config(), items, "alice", None, T1)
    assert out.done == [] and all("you wrote it" in why for _, why in out.skipped)
    out = review.approve(config(), items, "jonas", ["REQ-001", "NOPE-1"], T1)
    assert dict(out.skipped) == {
        "NOPE-1": "there is no such item in this feature",
        "REQ-001": "it needs Ops, Tech and Risk, and you do not have that role in aidlc.yaml"}
    review.approve(config(), items, "bob", ["REQ-001"], T1)
    out = review.approve(config(), list(load(feature).values()), "bob", ["REQ-001"], T1)
    assert out.skipped == [("REQ-001", "you already approved v1")]


def test_cannot_approve_drafts_or_stale(repo):
    repo(make("DISC-001", "discovery"), make("REQ-001", "requirement", status="stale"))
    out = review.approve(config(), list(load(repo).values()), "bob", ["DISC-001", "REQ-001"], T1)
    assert dict(out.skipped) == {
        "DISC-001": "it is a draft and has not been submitted for review",
        "REQ-001": "it is out of date and has to be updated first"}


def test_approving_lowered_tier_settles_other_items(repo):
    # Approved at T3; the new version says T1. Until sam approves, T3 rules apply.
    low = dict(data_classes=["internal"], audience="internal")
    repo(replace(make_risk("T1", version=2, approved_tier="T3", **low), status="in_review"),
         replace(make("DISC-001", "discovery", approvals=(("dana", 1),)), status="in_review"))
    assert load(repo)["DISC-001"].status == "in_review"  # T3 also needs Risk and Data owner
    # Lowering is judged by the tier that still governs: T3 needs Data owner too.
    review.approve(config(), list(load(repo).values()), "sam", ["RISK-001"], T1)
    assert load(repo)["RISK-001"].status == "in_review"
    review.approve(config(), list(load(repo).values()), "lee", ["RISK-001"], T1)
    after = load(repo)
    assert after["RISK-001"].extra["approved_tier"] == "T1"
    assert after["DISC-001"].status == "approved"  # at T1 the PM peer is enough


# --- reject ----------------------------------------------------------------

def test_reject_records_reason_and_removes_own_approval(feature):
    review.approve(config(), list(load(feature).values()), "bob", ["REQ-001"], T1)
    with pytest.raises(WorkspaceError, match="Say why"):
        review.reject(config(), list(load(feature).values()), "bob", ["REQ-001"], " ", T1)
    out = review.reject(config(), list(load(feature).values()), "bob", ["REQ-001"], "Too vague.", T1)
    assert [d.artifact.id for d in out.done] == ["REQ-001"]
    req = load(feature)["REQ-001"]
    assert req.status == "rejected" and req.approvals == ()
    assert req.extra["rejections"] == [{"by": "bob", "version": 1, "at": "2026-10-29T10:00:00Z",
                                        "reason": "Too vague."}]
    assert validate_repo(feature.root).ok
    edited = art.apply_edit(req, T1)
    assert (edited.version, edited.status) == (2, "draft")


def test_self_rejection_is_invalid(repo):
    rj = [{"by": "alice", "version": 1, "at": "2026-10-29T10:00:00Z", "reason": "x"}]
    repo(make("DISC-001", "discovery", status="rejected", rejections=rj))
    assert any("rejected their own" in i.message for i in validate_repo(repo.root).errors)


# --- GitHub reviews --------------------------------------------------------

def gh_review(login, state="APPROVED", commit="c1", at="2026-10-29T11:00:00Z", body=""):
    return Review(login, state, commit, at, body)


def versions(table):
    """version_at backed by {(commit, id): version}."""
    return lambda commit, a: table.get((commit, a.id))


def test_sync_records_github_approvals_at_the_seen_version(feature):
    items = list(load(feature).values())
    seen = versions({("c1", "REQ-001"): 1, ("c1", "DISC-001"): 1, ("c1", "RISK-001"): 1})
    recorded = review.sync_github_reviews(config(), items, [gh_review("bob"), gh_review("jonas")], seen, T1)
    assert [(a.id, who) for a, who in recorded] == [("REQ-001", "bob")]  # jonas holds no role
    assert [ap.by for ap in load(feature)["REQ-001"].approvals] == ["bob"]
    # Running again records nothing new.
    assert review.sync_github_reviews(config(), list(load(feature).values()), [gh_review("bob")], seen, T1) == []


def test_sync_ignores_approval_of_an_older_version(feature):
    items = list(load(feature).values())
    stale_view = versions({("c0", "REQ-001"): 0})
    assert review.sync_github_reviews(config(), items, [gh_review("bob", commit="c0")], stale_view, T1) == []


def test_changes_requested_uses_latest_review():
    reviews = [gh_review("bob", "CHANGES_REQUESTED", at="1", body="Fix it"), gh_review("bob", at="2"),
               gh_review("sam", "CHANGES_REQUESTED", at="3", body="Too risky")]
    assert [(r.login, r.body) for r in review.changes_requested(reviews)] == [("sam", "Too risky")]


# --- approvals_complete ----------------------------------------------------

def check(items, reviews, table, base_tier=None):
    by_feature = {"FEAT-001": items}
    return review.approvals_check(config(), items, by_feature, reviews, versions(table), base_tier or {})


def approved(a, *people):
    return replace(a, status="approved", approvals=tuple(art.Approval(p, a.version, T1) for p in people))


def test_check_passes_with_confirmed_approvals():
    items = [approved(make_risk(approved_tier="T2"), "sam"),
             approved(make("REQ-001", "requirement"), "bob", "priya", "sam")]
    table = {("c1", "REQ-001"): 1, ("c1", "RISK-001"): 1}
    result = check(items, [gh_review(p) for p in ("bob", "priya", "sam")], table, {"FEAT-001": "T2"})
    assert result.ok, result.problems
    assert result.checked == ["FEAT-001/RISK-001 v1", "FEAT-001/REQ-001 v1"]


def test_check_rejects_forged_approval():
    items = [make_risk(), approved(make("REQ-001", "requirement"), "bob", "priya", "sam")]
    result = check(items, [gh_review("priya"), gh_review("sam")], {("c1", "REQ-001"): 1})
    assert any("records an approval by bob, but bob has not approved this pull request" in p
               for p in result.problems)
    assert any("still needs Ops approval: bob" in p for p in result.problems)


def test_check_rejects_approval_given_for_an_older_version():
    req = approved(make("REQ-001", "requirement", version=2), "bob", "priya")
    result = check([req], [gh_review("bob", commit="old"), gh_review("priya", commit="new")],
                   {("old", "REQ-001"): 1, ("new", "REQ-001"): 2})
    assert any("bob has not approved this pull request on GitHub at this version" in p for p in result.problems)


def test_check_flags_self_approval_pending_and_bad_statuses():
    items = [
        replace(make("REQ-001", "requirement", approvals=(("alice", 1),)), status="in_review"),
        make("REQ-002", "requirement", status="rejected"),
        make("REQ-003", "requirement"),  # draft: not checked
    ]
    result = check(items, [gh_review("alice")], {("c1", "REQ-001"): 1})
    text = "\n".join(result.problems)
    assert "REQ-001 v1: alice approved their own work." in text
    assert "REQ-001 v1: still needs Ops approval: bob." in text
    assert "REQ-002 v1: is rejected" in text
    assert "REQ-003" not in text


def test_check_notes_github_approvals_not_yet_recorded():
    req = replace(make("REQ-001", "requirement", approvals=(("priya", 1),)), status="in_review")
    result = check([req], [gh_review("bob"), gh_review("priya")], {("c1", "REQ-001"): 1})
    assert result.notes == ["FEAT-001/REQ-001 v1: bob approved on GitHub; the PM's next /status records it."]


def test_check_complete_but_still_in_review_is_a_problem():
    req = replace(make("REQ-001", "requirement", approvals=(("bob", 1), ("priya", 1))), status="in_review")
    result = check([req], [gh_review("bob"), gh_review("priya")], {("c1", "REQ-001"): 1})
    assert result.problems == ["FEAT-001/REQ-001 v1: has every approval but is still marked in review; "
                               "run /status to record it."]


def test_check_blocks_hand_edited_approved_tier():
    # A PR that lowers approved_tier by hand, with no approved risk review.
    profile = replace(make_risk("T1", data_classes=["internal"], audience="internal", approved_tier="T1"),
                      status="in_review")
    result = check([profile], [], {}, {"FEAT-001": "T3"})
    assert any("approved_tier changed from T3 to T1 without an approved risk review" in p for p in result.problems)
