from aidlc import artifacts as art
from aidlc.cli import main
from aidlc.validate import refresh_statuses, validate_repo

from conftest import approved_chain, make


def messages(root, severity="error"):
    return [f"{i.where}: {i.message}" for i in validate_repo(root).issues if i.severity == severity]


def test_valid_chain_passes(repo):
    root = repo(*approved_chain())
    report = validate_repo(root)
    assert report.ok, messages(root)
    assert len(report.artifacts) == 3
    assert report.warnings == []


def test_empty_repo_passes(tmp_path):
    assert validate_repo(tmp_path).ok


def test_self_approval_is_rejected(repo):
    root = repo(make("DISC-001", "discovery", status="approved", approvals=(("alice", 1),)))
    errs = messages(root)
    assert any("approved their own artifact" in e for e in errs)
    assert any("nobody other than the owner" in e for e in errs)


def test_approved_needs_approval_for_current_version(repo):
    root = repo(make("DISC-001", "discovery", version=2, status="approved", approvals=(("bob", 1),)))
    assert any("nobody other than the owner approved v2" in e for e in messages(root))
    assert any("no longer counts" in w for w in messages(root, "warning"))


def test_approval_for_future_version_is_rejected(repo):
    root = repo(make("DISC-001", "discovery", approvals=(("bob", 3),)))
    assert any("does not exist yet" in e for e in messages(root))


def test_unresolved_parent(repo):
    root = repo(make("REQ-001", "requirement", parents=(("DISC-001", 1),)))
    assert any("DISC-001, which does not exist" in e for e in messages(root))


def test_parent_version_ahead_of_parent(repo):
    root = repo(
        make("DISC-001", "discovery"),
        make("REQ-001", "requirement", parents=(("DISC-001", 4),)),
    )
    assert any("only at v1" in e for e in messages(root))


def test_parent_of_wrong_type(repo):
    root = repo(
        make("DISC-001", "discovery"),
        make("AC-001", "criteria", parents=(("DISC-001", 1),), thresholds={"accuracy": 0.9}),
    )
    assert any("cannot have a discovery" in e for e in messages(root))


def test_missing_parent_is_warning_for_draft_error_otherwise(repo):
    root = repo(make("REQ-001", "requirement"))
    assert messages(root) == []
    assert any("has no parent" in w for w in messages(root, "warning"))
    repo(make("REQ-001", "requirement", status="in_review"))
    assert any("has no parent" in e for e in messages(root))


def test_stale_mismatch_is_an_error_until_written(repo):
    chain = approved_chain()
    chain[0] = make("DISC-001", "discovery", version=2, status="approved", approvals=(("bob", 2),))
    root = repo(*chain)
    assert any("FEAT-001/REQ-001: is out of date because DISC-001 is now v2" in e for e in messages(root))

    changes = refresh_statuses(root)
    assert [(c.artifact.id, c.old, c.new) for c in changes] == [("REQ-001", "approved", "stale")]
    assert validate_repo(root).ok
    req = art.load(repo.feature_dir / "requirements" / "REQ-001.md")
    assert req.status == "stale"
    assert req.version == 1  # staleness does not touch content or version
    # AC-001 is not directly affected until REQ-001 is revised.
    assert art.load(repo.feature_dir / "criteria" / "AC-001.md").status == "approved"


def test_stale_that_caught_up_returns_to_draft(repo):
    root = repo(
        make("DISC-001", "discovery", version=2),
        make("REQ-001", "requirement", status="stale", parents=(("DISC-001", 2),)),
    )
    assert any("is marked stale but is up to date" in e for e in messages(root))
    assert [c.new for c in refresh_statuses(root)] == ["draft"]
    assert validate_repo(root).ok


def test_type_must_match_folder(repo):
    root = repo.root
    a = make("REQ-001", "requirement")
    art.save(a, repo.feature_dir / "criteria" / "REQ-001.md")
    assert any("stored as a criteria" in e for e in messages(root))


def test_filename_must_match_id(repo):
    root = repo.root
    art.save(make("DISC-001", "discovery"), repo.feature_dir / "discovery.md")
    art.save(make("REQ-002", "requirement", parents=(("DISC-001", 1),)),
             repo.feature_dir / "requirements" / "REQ-001.md")
    assert any("location says REQ-001" in e for e in messages(root))


def test_feature_field_must_match_folder(repo):
    root = repo(make("DISC-001", "discovery", feature="FEAT-002"))
    assert any("says `feature: FEAT-002`" in e for e in messages(root))


def test_bad_feature_folder_name(repo):
    root = repo(make("DISC-001", "discovery"), folder=repo.root / "features" / "guest-triage")
    assert any("feature folder name" in e for e in messages(root))


def test_duplicate_feature_ids(repo):
    repo(make("DISC-001", "discovery"))
    root = repo(make("DISC-001", "discovery"), folder=repo.root / "features" / "FEAT-001-other")
    assert any("FEAT-001 is already used" in e for e in messages(root))


def test_unparseable_file_is_reported_with_path(repo):
    path = repo.feature_dir / "requirements" / "REQ-001.md"
    path.parent.mkdir(parents=True)
    path.write_text("no frontmatter here\n")
    errs = messages(repo.root)
    assert errs == ["features/FEAT-001-guest-triage/requirements/REQ-001.md: "
                    "file does not start with a `---` frontmatter block"]


def test_criteria_without_thresholds_warns(repo):
    root = repo(
        make("DISC-001", "discovery"),
        make("REQ-001", "requirement", parents=(("DISC-001", 1),)),
        make("AC-001", "criteria", parents=(("REQ-001", 1),)),
    )
    assert any("no thresholds" in w for w in messages(root, "warning"))


def test_bad_config_is_reported(repo):
    (repo.root / "aidlc.yaml").write_text("thresholds:\n  accuracy: 2\n")
    assert any("aidlc.yaml" in e for e in messages(repo.root))


def test_cli_validate(repo, capsys):
    root = repo(*approved_chain())
    assert main(["--root", str(root), "validate"]) == 0
    assert "All 3 artifact(s) are valid." in capsys.readouterr().out

    repo(make("DISC-001", "discovery", version=2, status="approved", approvals=(("bob", 2),)))
    assert main(["--root", str(root), "validate"]) == 1
    assert "Found 1 problem(s)" in capsys.readouterr().out

    assert main(["--root", str(root), "validate", "--write"]) == 0
    out = capsys.readouterr().out
    assert "Marked FEAT-001/REQ-001 as stale (was approved)." in out
