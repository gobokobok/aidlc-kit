"""The worked example (FEAT-001) in this repository: it must pass the same
checks CI runs, and the Tier 3 page must describe what the kit really does."""

import io
import json
from pathlib import Path

import pytest

from aidlc import audit, decompose, handoff, reviewers, risk, workspace
from aidlc.cli import main
from aidlc.config import load_config
from aidlc.evals import runner
from aidlc.validate import validate_repo

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def example():
    feature = workspace.list_features(ROOT)[0]
    return feature, workspace.artifacts_of(ROOT, feature)


def cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return main(["--root", str(ROOT), *argv], out=out, stdin=io.StringIO("")), out.getvalue()


def test_example_validates_and_every_item_is_approved(example):
    report = validate_repo(ROOT)
    assert report.ok and not [i for i in report.issues if i.severity == "warning"]
    _, items = example
    assert {a.id for a in items} == {
        "RISK-001", "DISC-001", "REQ-001", "REQ-002", "REQ-003", "AC-001", "AC-002",
        "ASSET-001", "EVAL-001", "HND-001", "DEC-001"}
    assert {a.status for a in items} == {"approved"}


def test_example_is_tier_2_with_the_risk_reviewer_in_every_approval(example):
    feature, items = example
    config, _ = load_config(ROOT)
    profile = next(a for a in items if a.type == "risk")
    tier = risk.effective_tier(profile, config)
    assert tier.name == "T2" and "risk_reviewer" in tier.extra_reviewers
    risk_reviewers = {p for p, roles in config.people.items() if "risk_reviewer" in roles}
    for a in items:
        assert a.owner not in {x.by for x in a.approvals}
        assert risk_reviewers & {x.by for x in a.approvals}, a.id
        assert all(c.satisfied for c in reviewers.role_checks(config, a, tier)), a.id


def test_example_golden_set_and_cached_evals(example):
    feature, _ = example
    cases, problems = runner.parse_golden((feature.path / "evals" / "golden.yaml").read_text())
    assert not problems and len(cases) == 20
    assert {c for case in cases for c in case.criteria} == {"AC-001", "AC-002"}
    report = json.loads((feature.path / "evals" / "report.json").read_text())
    assert report["pass"] and report["provider"] == "scripted-example"
    code, out = cli("eval", "--check", "--all")   # re-runs from the saved answers only
    assert code == 0, out


def test_example_handoff_package_is_intact_and_decomposition_is_clean(example):
    feature, items = example
    package = next(a for a in items if a.type == "handoff")
    assert handoff.verify_bundle(package.path.parent) == []
    manifest = json.loads((package.path.parent / "manifest.json").read_text())
    assert manifest["tier"] == "T2" and manifest["eval"]["pass"]
    plan = next(a for a in items if a.type == "decomposition")
    assert [p.id for p in plan.parents] == ["HND-001"]
    assert decompose.check(plan, {a.id for a in items if a.type == "criteria"}) == []


def test_example_audit_log_covers_every_item(example):
    _, items = example
    entries = audit.read_entries(ROOT)
    assert {e["id"] for e in entries} == {a.id for a in items}
    assert {e["tier"] for e in entries} == {"T2"}
    assert all("risk_reviewer" in e["roles_satisfied"] for e in entries)
    assert audit.check_log(None, (ROOT / audit.LOG).read_text()) == []


def test_example_codeowners_match_the_config():
    assert cli("sync-codeowners", "--check")[0] == 0


# --- docs/example-tier3.md ---------------------------------------------------

def test_tier3_page_matches_the_rules():
    page = (ROOT / "docs" / "example-tier3.md").read_text()
    config, _ = load_config(ROOT)
    t2, t3 = config.tier("T2"), config.tier("T3")
    before = risk.Answers(("personal",), "suggest", "customer_facing", False)
    after = risk.Answers(("personal",), "act_autonomously", "customer_facing", False)
    assert risk.compute_tier(before)[0] == "T2" and risk.compute_tier(after)[0] == "T3"
    assert t3.min_thresholds["accuracy"] == 0.95 and t2.min_thresholds["accuracy"] == 0.85
    assert t3.extra_reviewers == ("risk_reviewer", "data_owner") and t3.required_artifacts == ("privacy_assessment",)
    assert t3.human_in_loop and not t2.human_in_loop
    for claim in ("0.95", "0.85", "privacy assessment", "Data owner", "human review step"):
        assert claim in page
