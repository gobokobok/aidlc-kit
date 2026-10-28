import json
from pathlib import Path

import pytest

from aidlc import audit, blocks, ci
from aidlc.config import parse_config
from aidlc.reviewers import codeowners
from aidlc.validate import load_feature

from conftest import CONFIG_YAML, T1, approved_chain, config, make

ROOT = Path(__file__).resolve().parents[1]


def line(**over):
    base = {f: None for f in audit.FIELDS}
    return json.dumps({**base, **over})


# --- audit log -------------------------------------------------------------

def test_append_only_accepts_new_lines():
    old = line(id="REQ-001") + "\n"
    assert audit.check_log(old, old + line(id="REQ-002") + "\n") == []
    assert audit.check_log(None, line(id="REQ-001") + "\n") == []


@pytest.mark.parametrize("new", [
    line(id="REQ-009") + "\n" + line(id="REQ-002") + "\n",   # first line edited
    line(id="REQ-002") + "\n",                                # first line removed
    "",                                                       # log emptied
])
def test_append_only_rejects_edits_and_deletions(new):
    old = line(id="REQ-001") + "\n" + line(id="REQ-002") + "\n"
    problems = audit.check_log(old, new)
    assert problems and "append-only" in problems[0]


def test_new_lines_must_be_complete_json():
    assert audit.check_log("", "not json\n") == [f"{audit.LOG} line 1 is not valid JSON."]
    assert "missing: tier, roles_satisfied" in audit.check_log("", json.dumps(
        {f: 1 for f in audit.FIELDS if f not in ("tier", "roles_satisfied")}) + "\n")[0]


def test_frozen_log_in_pull_requests():
    assert audit.check_log("a\n", "a\n", frozen=True) == []
    assert "was changed in this pull request" in audit.check_log("a\n", "a\nb\n", frozen=True)[0]


def test_pr_from_subject():
    assert audit.pr_from_subject("FEAT-001: Guest triage (#12)") == 12
    assert audit.pr_from_subject("[AIDLC] Audit") is None


def test_build_entries_with_tier_roles_and_deletions(repo):
    root = repo(*approved_chain())
    feature_dir = "features/FEAT-001-guest-triage"
    old_text = (repo.feature_dir / "criteria" / "AC-001.md").read_text()
    (repo.feature_dir / "criteria" / "AC-001.md").unlink()
    changed = [f"{feature_dir}/requirements/REQ-001.md", f"{feature_dir}/criteria/AC-001.md", "README.md"]
    entries = audit.build_entries(
        changed, lambda d: load_feature(root / d, root)[1], lambda p: old_text if "AC-001" in p else None,
        config(), "priya", "abc123", 7, T1)
    by_id = {e["id"]: e for e in entries}
    assert set(by_id) == {"REQ-001", "AC-001"}
    assert by_id["REQ-001"] == {
        "at": "2026-10-29T10:00:00Z", "feature": "FEAT-001", "id": "REQ-001", "version": 1,
        "status": "approved", "actor": "priya", "approvers": ["bob", "priya", "sam"], "tier": "T2",
        "roles_satisfied": ["ops_reviewer", "tech_reviewer", "risk_reviewer"], "commit": "abc123", "pr": 7}
    assert by_id["AC-001"]["status"] == "deleted"


def test_audit_ids_are_never_reused(repo):
    from aidlc import workspace
    repo(make("DISC-001", "discovery"))
    audit.append(repo.root, [json.loads(line(feature="FEAT-001", id="REQ-003"))])
    feature = workspace.list_features(repo.root)[0]
    assert "REQ-003" in workspace.used_ids(repo.root, feature, [])


# --- CODEOWNERS ------------------------------------------------------------

def test_codeowners_from_routing():
    text = codeowners(config())
    assert "/features/*/discovery.md @alice @dana\n" in text      # pm_peer: every PM
    assert "/features/*/requirements/ @bob @priya\n" in text
    assert "/features/*/risk.md @sam\n" in text
    assert "evals" not in text                                    # unrouted: anyone may approve
    assert "/aidlc.yaml" not in text                              # no kit_admin in this config


def test_codeowners_kit_admin_owns_config():
    cfg, _ = parse_config(CONFIG_YAML.replace("  jonas: [engineer]", "  jonas: [engineer, kit_admin]"))
    text = codeowners(cfg)
    assert "/aidlc.yaml @jonas\n" in text and "/.github/ @jonas\n" in text


def test_codeowners_block_keeps_company_lines():
    theirs = "/src/ @platform-team\n"
    once = blocks.upsert(theirs, codeowners(config()), blocks.HASH_MARKERS)
    assert once.startswith(theirs)
    assert blocks.extract(once, blocks.HASH_MARKERS) == codeowners(config()).strip()


def test_kit_repo_ci_and_codeowners_are_in_sync():
    """The kit's own CI is what `aidlc sync-ci --install 'pip install -e .'` writes."""
    cfg, _ = parse_config((ROOT / "aidlc.yaml").read_text())
    for rel, content in ci.workflows("pip install -e .").items():
        assert (ROOT / rel).read_text() == content, rel
    assert blocks.extract((ROOT / ci.CODEOWNERS_PATH).read_text(), blocks.HASH_MARKERS) == codeowners(cfg).strip()


# --- workflows -------------------------------------------------------------

def test_workflows_have_required_job_names_and_keep_github_expressions():
    flows = ci.workflows("pip install aidlc-kit==9.9")
    assert set(flows) == {".github/workflows/aidlc-validate.yml", ".github/workflows/aidlc-approvals.yml",
                          ".github/workflows/aidlc-audit.yml"}
    text = "\n".join(flows.values())
    for job in ("  validate:", "  approvals_complete:", "  audit:"):
        assert job in text
    assert "@@INSTALL@@" not in text and text.count("pip install aidlc-kit==9.9") == 3
    assert "${{ github.event.pull_request.number }}" in text
    assert "--force" not in text
