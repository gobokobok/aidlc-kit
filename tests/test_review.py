from dataclasses import replace

import pytest

from aidlc import review
from aidlc.config import parse_config
from aidlc.workspace import Feature, WorkspaceError

from conftest import CONFIG_YAML, T0, config, make, make_risk


def in_review(*items):
    return [replace(a, status="in_review") for a in items]


def test_join():
    assert review.join(["a"]) == "a"
    assert review.join(["a", "b"]) == "a and b"
    assert review.join(["a", "b", "c"]) == "a, b and c"


def test_message_matches_spec_example():
    cfg = config()
    items = in_review(make("REQ-001", "requirement"))
    plan = review.plan_reviews(cfg, items, cfg.tier("T2"), "alice")
    assert review.reviewer_message(plan, cfg.tier("T2")) == (
        "Sent to bob (Ops) and priya (Tech). sam (Risk) is included because this feature is Tier 2.")


def test_plan_covers_every_item_and_role():
    cfg = config()
    items = in_review(make_risk(), make("DISC-001", "discovery"), make("REQ-001", "requirement"))
    plan = review.plan_reviews(cfg, items, cfg.tier("T2"), "alice")
    by_person = {r.person: r for r in plan.requests}
    assert set(by_person) == {"sam", "dana", "bob", "priya"}
    assert by_person["sam"].artifacts == ["RISK-001", "DISC-001", "REQ-001"]
    assert by_person["dana"].roles == ["pm_peer"]
    msg = review.reviewer_message(plan, cfg.tier("T2"))
    assert msg.startswith("Sent to dana (PM peer), bob (Ops) and priya (Tech). sam (Risk) is included")


def test_plan_skips_approved_roles_and_drafts():
    cfg = config()
    items = [
        replace(make("REQ-001", "requirement", approvals=(("bob", 1),)), status="in_review"),
        make("REQ-002", "requirement"),  # draft: not asked yet
    ]
    plan = review.plan_reviews(cfg, items, None, "alice")
    assert [(r.person, r.artifacts) for r in plan.requests] == [("priya", ["REQ-001"])]


def test_submitter_is_never_asked():
    cfg = config()
    items = in_review(make("REQ-001", "requirement", owner="alice"))
    plan = review.plan_reviews(cfg, items, None, "bob")
    assert [r.person for r in plan.requests] == ["priya"]
    assert plan.unfilled == ["ops_reviewer"]
    assert "Nobody in aidlc.yaml has the Ops role yet" in review.reviewer_message(plan, None)


def test_unrouted_and_unheld_roles_are_explained():
    cfg = config()
    items = in_review(make("PIA-001", "privacy_assessment"))
    plan = review.plan_reviews(cfg, items, cfg.tier("T3"), "alice")
    msg = review.reviewer_message(plan, cfg.tier("T3"))
    assert msg == ("Sent to sam (Risk) and lee (Data owner), included because this feature is Tier 3. "
                   "Anyone other than you can approve PIA-001.")
    no_owner, _ = parse_config(CONFIG_YAML.replace("  lee: [data_owner]\n", ""))
    plan = review.plan_reviews(no_owner, items, no_owner.tier("T3"), "alice")
    assert "Nobody in aidlc.yaml has the Data owner role yet" in review.reviewer_message(plan, no_owner.tier("T3"))


def test_mark_submitted(repo):
    root = repo(make("DISC-001", "discovery"), make("REQ-001", "requirement", status="approved",
                                                   parents=(("DISC-001", 1),), approvals=(("bob", 1),)))
    from aidlc.validate import load_repo
    items, _ = load_repo(root)
    submitted = review.mark_submitted(items)
    assert [a.id for a in submitted] == ["DISC-001"]
    assert {a.id: a.status for a in load_repo(root)[0]} == {"DISC-001": "in_review", "REQ-001": "approved"}


def test_stale_items_block_submit():
    with pytest.raises(WorkspaceError, match="REQ-001 is out of date"):
        review.mark_submitted([make("REQ-001", "requirement", status="stale")])


def test_pr_body_shows_answers_next_to_tier(tmp_path):
    cfg = config()
    feature = Feature("FEAT-001", "Guest request triage", "alice", T0, tmp_path)
    items = in_review(make_risk(), make("REQ-001", "requirement"))
    plan = review.plan_reviews(cfg, items, cfg.tier("T2"), "alice")
    body = review.pr_body(feature, items, cfg, cfg.tier("T2"), plan)
    assert "Risk: **Tier 2 (Medium)**" in body
    assert "Who sees or is affected by the result? **Customers or guests**" in body
    assert "Computed tier: **Tier 2 (Medium)**" in body
    assert "| REQ-001 | REQ-001 title | v1 | in_review | Ops, Tech, Risk |" in body
    assert "_Not run yet._" in body
