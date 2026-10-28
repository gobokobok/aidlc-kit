from dataclasses import replace

import pytest

from aidlc import artifacts as art
from aidlc import workspace as ws
from aidlc.risk import Answers
from aidlc.validate import validate_repo
from aidlc.workspace import WorkspaceError

from conftest import T0, T1, approved_chain, config, make

T2_ANSWERS = Answers(("personal",), "suggest", "customer_facing", False)


@pytest.fixture
def feature(repo):
    f, _ = ws.create_feature(repo.root, config(), "Guest request triage", "alice", T2_ANSWERS,
                             "Guest messages may contain names.", T0)
    return f


def test_slugify():
    assert ws.slugify("Guest request triage!") == "guest-request-triage"
    assert ws.slugify("  ") == "feature"
    assert len(ws.slugify("x" * 100)) == 40


def test_next_feature_id_counts_branches(repo):
    assert ws.next_feature_id(repo.root) == "FEAT-001"
    repo(make("DISC-001", "discovery"))
    assert ws.next_feature_id(repo.root) == "FEAT-002"
    assert ws.next_feature_id(repo.root, ["feat/FEAT-007"]) == "FEAT-008"


def test_create_feature(repo, feature):
    assert feature.id == "FEAT-001"
    assert feature.path.name == "FEAT-001-guest-request-triage"
    profile = art.load(feature.path / "risk.md")
    assert (profile.id, profile.extra["declared_tier"], profile.owner) == ("RISK-001", "T2", "alice")
    assert "Computed tier: **Tier 2 (Medium)**" in profile.body
    assert "Every item also needs approval from: Risk." in profile.body
    assert ws.get_feature(repo.root, "FEAT-001").title == "Guest request triage"
    assert validate_repo(repo.root).ok


def test_create_feature_rejects_lower_tier(repo):
    with pytest.raises(WorkspaceError, match="not set it lower"):
        ws.create_feature(repo.root, config(), "X", "alice", T2_ANSWERS, "", T0, raise_to="T1")
    assert ws.list_features(repo.root) == []  # nothing written


def test_create_feature_can_raise_tier(repo):
    _, profile = ws.create_feature(repo.root, config(), "X", "alice", T2_ANSWERS, "", T0, raise_to="T3")
    assert profile.extra["declared_tier"] == "T3"


def test_create_chain_with_default_parents(repo, feature):
    disc = ws.create_artifact(repo.root, feature, "discovery", "Why", "alice", T0, body="## Problem\nSlow.")
    req = ws.create_artifact(repo.root, feature, "requirement", "Route it", "alice", T0)
    assert [p.id for p in req.parents] == [disc.id]
    assert disc.body == "\n## Problem\nSlow.\n"
    ac1 = ws.create_artifact(repo.root, feature, "criteria", "Accurate", "alice", T0,
                             extra={"thresholds": {"accuracy": 0.9}})
    ac2 = ws.create_artifact(repo.root, feature, "criteria", "Safe", "alice", T0, parent_ids=[req.id])
    asset = ws.create_artifact(repo.root, feature, "asset", "Prompt", "alice", T0)
    assert [p.id for p in asset.parents] == [ac1.id, ac2.id]
    assert (ac1.id, ac2.id) == ("AC-001", "AC-002")
    assert "## What it must do" in req.body  # template outline when no body given
    assert validate_repo(repo.root).ok


def test_create_needs_a_parent_when_ambiguous(repo, feature):
    ws.create_artifact(repo.root, feature, "discovery", "Why", "alice", T0)
    ws.create_artifact(repo.root, feature, "requirement", "A", "alice", T0)
    ws.create_artifact(repo.root, feature, "requirement", "B", "alice", T0)
    with pytest.raises(WorkspaceError, match="choose from REQ-001, REQ-002"):
        ws.create_artifact(repo.root, feature, "criteria", "C", "alice", T0)


def test_create_rejects_wrong_parent_type(repo, feature):
    ws.create_artifact(repo.root, feature, "discovery", "Why", "alice", T0)
    with pytest.raises(WorkspaceError, match="links to a requirement, not to DISC-001"):
        ws.create_artifact(repo.root, feature, "criteria", "C", "alice", T0, parent_ids=["DISC-001"])


def test_only_one_discovery(repo, feature):
    ws.create_artifact(repo.root, feature, "discovery", "Why", "alice", T0)
    with pytest.raises(WorkspaceError, match="already has a discovery"):
        ws.create_artifact(repo.root, feature, "discovery", "Again", "alice", T0)


def test_ids_from_audit_log_are_not_reused(repo, feature):
    ws.create_artifact(repo.root, feature, "discovery", "Why", "alice", T0)
    (repo.root / "audit").mkdir()
    (repo.root / "audit" / "log.jsonl").write_text(
        '{"feature": "FEAT-001", "id": "REQ-004"}\n{"feature": "FEAT-002", "id": "REQ-009"}\n')
    assert ws.create_artifact(repo.root, feature, "requirement", "R", "alice", T0).id == "REQ-005"


def test_edit_approved_bumps_and_marks_children_stale(repo):
    root = repo(*approved_chain())
    feature = ws.list_features(root)[0]
    edit = ws.edit_artifact(root, feature, "DISC-001", T1, body="New brief")
    assert (edit.after.version, edit.after.status, edit.after.approvals) == (2, "draft", ())
    assert [(c.artifact.id, c.new) for c in edit.status_changes] == [("REQ-001", "stale")]
    assert edit.downstream == ["AC-001", "REQ-001"]
    # Changing the stale requirement relinks it to DISC-001 v2.
    edit2 = ws.edit_artifact(root, feature, "REQ-001", T1)
    assert edit2.after.parents[0].version == 2
    assert (edit2.after.version, edit2.after.status) == (2, "draft")
    assert [(c.artifact.id, c.new) for c in edit2.status_changes] == [("AC-001", "stale")]


def test_risk_is_not_edited_with_change(repo, feature):
    with pytest.raises(WorkspaceError, match="/risk"):
        ws.edit_artifact(repo.root, feature, "RISK-001", T1, body="x")


def test_revise_risk_raises_tier(repo, feature):
    rev = ws.revise_risk(repo.root, config(), feature, T1, {"data_classes": ["payment"]})
    assert (rev.tier_before.name, rev.tier_after.name, rev.computed) == ("T2", "T3", "T3")
    assert rev.after.extra["audience"] == "customer_facing"  # unchanged answers kept


def test_lowering_after_approval_waits_for_risk_reviewer(repo, feature):
    path = feature.path / "risk.md"
    approved = art.load(path)
    approved = replace(approved, status="approved", approvals=(art.Approval("sam", 1, T1),),
                       extra={**approved.extra, "approved_tier": "T2"})
    art.save(approved)
    rev = ws.revise_risk(repo.root, config(), feature, T1,
                         {"data_classes": ["internal"], "audience": "internal"})
    assert rev.computed == "T1"
    assert rev.after.extra["declared_tier"] == "T1"
    assert (rev.after.version, rev.after.status) == (2, "draft")
    assert rev.tier_after.name == "T2"  # lowering is blocked until approved
    assert "Still governed by the approved **Tier 2 (Medium)**" in rev.after.body


def test_deliberate_raise_is_kept_but_computed_tier_can_drop(repo, feature):
    ws.revise_risk(repo.root, config(), feature, T1, {}, raise_to="T3")
    rev = ws.revise_risk(repo.root, config(), feature, T1, {"rationale": "Clarified."})
    assert rev.after.extra["declared_tier"] == "T3"  # raise is sticky
    # Without a raise, answers that compute lower lower the declared tier.
    rev = ws.revise_risk(repo.root, config(), feature, T1, {"data_classes": ["payment"]}, raise_to="T3")
    rev = ws.revise_risk(repo.root, config(), feature, T1, {"data_classes": ["internal"], "audience": "internal"})
    assert rev.after.extra["declared_tier"] == "T1"


def test_revise_rejects_bad_answers(repo, feature):
    with pytest.raises(WorkspaceError, match="autonomy"):
        ws.revise_risk(repo.root, config(), feature, T1, {"autonomy": "sometimes"})


def test_hand_edit_of_reviewed_artifact_becomes_new_version(repo):
    root = repo(*approved_chain())
    path = repo.feature_dir / "requirements" / "REQ-001.md"
    head = path.read_text()
    path.write_text(head.replace("Body text.", "Edited by hand."))
    bumped = ws.normalize_hand_edits(root, [(path, head)], T1)
    assert [(a.id, a.version, a.status) for a in bumped] == [("REQ-001", 2, "draft")]
    assert art.load(path).approvals == ()


def test_hand_edit_of_draft_or_status_only_is_left_alone(repo):
    root = repo(make("DISC-001", "discovery"))
    path = repo.feature_dir / "discovery.md"
    head = path.read_text()
    path.write_text(head.replace("Body text.", "Draft tweak."))
    assert ws.normalize_hand_edits(root, [(path, head)], T1) == []
    approved = approved_chain()[1]
    repo(approved)
    head = path.read_text()
    art.save(replace(approved, status="stale"), path)  # e.g. validate --write
    assert ws.normalize_hand_edits(root, [(path, head)], T1) == []


def test_next_step(repo, feature):
    cfg = config()
    items = ws.artifacts_of(repo.root, feature)
    tier = cfg.tier("T2")
    assert "/discover" in ws.next_step(items, tier, cfg)
    for a_type in ("discovery", "requirement", "criteria", "asset"):
        ws.create_artifact(repo.root, feature, a_type, a_type, "alice", T0)
    items = ws.artifacts_of(repo.root, feature)
    assert ws.next_step(items, tier, cfg) == "Run /submit to ask for a review."
    assert "privacy assessment" in ws.next_step(items, cfg.tier("T3"), cfg)
    in_review = [replace(a, status="in_review") for a in items]
    assert "/reviewers" in ws.next_step(in_review, tier, cfg)


def test_template_body():
    assert ws.template_body("criteria").startswith("# Title\n\n## Done means")
    with pytest.raises(WorkspaceError):
        ws.template_body("risk")
