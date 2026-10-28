from dataclasses import replace
from datetime import timezone

import pytest

from aidlc import artifacts as art
from aidlc.artifacts import ArtifactError, apply_edit, check_meta, next_id

from conftest import T1, make

VALID = """---
id: REQ-003
type: requirement
feature: FEAT-001
title: Route maintenance requests to engineering queue
version: 2
status: draft
owner: alice
parents:
  - {id: DISC-001, version: 1}
approvals:
  - {by: bob, version: 2, at: 2026-10-29T10:00:00Z}
updated_at: 2026-10-29T09:12:00Z
---

Plain-language body.
"""


def errors(meta, where="x"):
    return [i.message for i in check_meta(meta, where) if i.severity == "error"]


def valid_meta():
    raw, _ = art.split_frontmatter(VALID)
    import yaml
    return yaml.safe_load(raw)


def test_parse_spec_example():
    a = art.parse(VALID)
    assert a.id == "REQ-003"
    assert a.version == 2
    assert a.parents[0].id == "DISC-001"
    assert a.approvals[0].by == "bob"
    assert a.approvals[0].at.tzinfo == timezone.utc
    assert a.body == "\nPlain-language body.\n"


def test_round_trip_is_stable():
    a = art.parse(VALID)
    text = art.dumps(a)
    assert art.parse(text) == a
    assert art.dumps(art.parse(text)) == text
    assert "  - {id: DISC-001, version: 1}" in text
    assert "  - {by: bob, version: 2, at: '2026-10-29T10:00:00Z'}" in text
    assert "updated_at: 2026-10-29T09:12:00Z" in text


def test_extra_fields_are_preserved():
    a = make("AC-001", "criteria", thresholds={"accuracy": 0.9, "max_unsafe": 0})
    b = art.parse(art.dumps(a))
    assert b.extra == {"thresholds": {"accuracy": 0.9, "max_unsafe": 0}}


def test_no_frontmatter_is_an_error():
    with pytest.raises(ArtifactError, match="frontmatter"):
        art.parse("# Just a heading\n")


def test_broken_yaml_is_an_error():
    with pytest.raises(ArtifactError, match="not valid YAML"):
        art.parse("---\nid: [unclosed\n---\n")


def test_valid_meta_has_no_errors():
    assert errors(valid_meta()) == []


@pytest.mark.parametrize("key", art.CORE_KEYS)
def test_each_core_field_is_required(key):
    meta = valid_meta()
    del meta[key]
    assert any("missing required" in e and key in e for e in errors(meta))


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [
        ("type", "story", "type"),
        ("id", "REQ3", "id"),
        ("id", "AC-001", "does not match type"),
        ("feature", "F1", "feature"),
        ("title", "  ", "title"),
        ("version", 0, "version"),
        ("version", True, "version"),
        ("version", "2", "version"),
        ("status", "done", "status"),
        ("owner", "not a user!", "owner"),
        ("updated_at", "yesterday", "updated_at"),
        ("updated_at", "2026-10-29T09:12:00", "updated_at"),  # no timezone
        ("parents", [{"id": "DISC-001"}], "parent #1"),
        ("parents", "DISC-001", "parents must be a list"),
        ("approvals", [{"by": "bob", "version": 1}], "approval #1"),
    ],
)
def test_bad_field_values(key, value, fragment):
    meta = valid_meta()
    meta[key] = value
    assert any(fragment in e for e in errors(meta)), errors(meta)


@pytest.mark.parametrize(
    ("thresholds", "ok"),
    [
        ({"accuracy": 0.9, "max_unsafe": 0}, True),
        ({"accuracy": 1.5}, False),
        ({"max_unsafe": -1}, False),
        ({"accuracy": "high"}, False),
        ({"Accuracy": 0.9}, False),
        ([0.9], False),
    ],
)
def test_thresholds(thresholds, ok):
    meta = valid_meta()
    meta["thresholds"] = thresholds
    assert (errors(meta) == []) is ok


def test_empty_parents_and_approvals_are_allowed():
    meta = valid_meta()
    meta["parents"] = None
    meta["approvals"] = []
    assert errors(meta) == []
    assert art.from_meta(meta).parents == ()


def test_next_id_is_sequential_and_never_reuses():
    assert next_id("requirement", []) == "REQ-001"
    assert next_id("requirement", ["REQ-001", "REQ-002", "AC-009"]) == "REQ-003"
    # REQ-002 was deleted, but REQ-004 existed once (e.g. seen in the audit log).
    assert next_id("requirement", ["REQ-001", "REQ-003", "REQ-004"]) == "REQ-005"
    assert next_id("criteria", ["REQ-007"]) == "AC-001"


def test_relative_paths():
    assert art.relative_path("discovery", "DISC-001") == "discovery.md"
    assert art.relative_path("requirement", "REQ-002") == "requirements/REQ-002.md"
    assert art.relative_path("handoff", "HND-001") == "handoff/HND-001/handoff.md"


def test_feature_dir_names():
    assert art.feature_id_from_dir("FEAT-001-guest-request-triage") == "FEAT-001"
    assert art.feature_id_from_dir("FEAT-012") == "FEAT-012"
    assert art.feature_id_from_dir("guest-triage") is None
    assert art.feature_id_from_dir("FEAT-001-Bad_Name") is None


def test_edit_of_unreviewed_draft_keeps_version():
    a = make("REQ-001", "requirement")
    b = apply_edit(a, T1, title="New title")
    assert (b.version, b.status, b.title, b.updated_at) == (1, "draft", "New title", T1)


def test_edit_of_approved_bumps_version_and_clears_approval():
    a = make("REQ-001", "requirement", status="approved", approvals=(("bob", 1),))
    b = apply_edit(a, T1, body="changed")
    assert (b.version, b.status, b.approvals) == (2, "draft", ())


@pytest.mark.parametrize("status", ["in_review", "rejected"])
def test_edit_after_review_bumps_version(status):
    b = apply_edit(make("REQ-001", "requirement", status=status), T1)
    assert (b.version, b.status) == (2, "draft")


def test_edit_of_stale_approved_bumps_version():
    a = make("REQ-001", "requirement", status="stale", approvals=(("bob", 1),))
    b = apply_edit(a, T1)
    assert (b.version, b.status, b.approvals) == (2, "draft", ())


def test_edit_of_stale_unreviewed_draft_keeps_version():
    b = apply_edit(make("REQ-001", "requirement", status="stale"), T1)
    assert (b.version, b.status) == (1, "draft")


def test_approved_current_only_counts_current_version():
    a = make("REQ-001", "requirement", version=2, approvals=(("bob", 1), ("dan", 2)))
    assert [ap.by for ap in a.approved_current] == ["dan"]
    assert replace(a, version=3).approved_current == ()
