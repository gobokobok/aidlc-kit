from aidlc import reviewers
from aidlc.reviewers import holders, required_roles, role_checks, role_label

from conftest import config, make


def test_role_labels():
    assert role_label("ops_reviewer") == "Ops"
    assert role_label("tech_reviewer") == "Tech"
    assert role_label("risk_reviewer") == "Risk"
    assert role_label("data_owner") == "Data owner"
    assert role_label("pm_peer") == "PM peer"


def test_pm_peer_is_any_other_pm():
    cfg = config()
    assert holders(cfg, "pm_peer", author="alice") == ("dana",)
    assert holders(cfg, "pm_peer", author="dana") == ("alice",)
    assert holders(cfg, "pm_peer", author="bob") == ("alice", "dana")


def test_author_never_holds_a_role():
    cfg = config()
    assert "bob" not in holders(cfg, "ops_reviewer", author="bob")
    assert not reviewers.holds(cfg, "bob", "any_reviewer", author="bob")


def test_required_roles_add_tier_extras():
    cfg = config()
    assert required_roles(cfg, "requirement", cfg.tier("T1")) == [
        ("ops_reviewer", "routing"), ("tech_reviewer", "routing")]
    assert required_roles(cfg, "requirement", cfg.tier("T3")) == [
        ("ops_reviewer", "routing"), ("tech_reviewer", "routing"),
        ("risk_reviewer", "T3"), ("data_owner", "T3")]


def test_tier_extra_already_routed_is_not_duplicated():
    cfg = config()
    assert required_roles(cfg, "risk", cfg.tier("T2")) == [("risk_reviewer", "routing")]


def test_unrouted_type_needs_any_other_reviewer():
    cfg = config()
    assert required_roles(cfg, "eval", None) == [("any_reviewer", "routing")]
    a = make("EVAL-001", "eval", approvals=(("jonas", 1),))
    assert reviewers.roles_complete(cfg, a, None)


def test_role_checks_count_only_current_version_and_role_holders():
    cfg = config()
    a = make("REQ-001", "requirement", version=2,
             approvals=(("bob", 1), ("priya", 2), ("dana", 2)))
    checks = {c.role: c for c in role_checks(cfg, a, cfg.tier("T2"))}
    assert not checks["ops_reviewer"].satisfied          # bob approved v1 only
    assert checks["ops_reviewer"].candidates == ("bob",)
    assert checks["tech_reviewer"].approved_by == ("priya",)
    assert not checks["risk_reviewer"].satisfied         # dana is not a risk reviewer
    assert [c.role for c in reviewers.pending(cfg, a, cfg.tier("T2"))] == ["ops_reviewer", "risk_reviewer"]


def test_self_approval_never_satisfies_a_role():
    cfg = config()
    a = make("REQ-001", "requirement", owner="bob", approvals=(("bob", 1), ("priya", 1)))
    assert [c.role for c in reviewers.pending(cfg, a, None)] == ["ops_reviewer"]
