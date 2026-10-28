from datetime import datetime, timezone
from pathlib import Path

import pytest

from aidlc import artifacts as art
from aidlc.artifacts import Approval, Artifact, ParentRef

T0 = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)

CONFIG_YAML = """\
display_name: Test Kit
people:
  alice: [pm]
  dana: [pm]
  bob: [ops_reviewer]
  priya: [tech_reviewer]
  sam: [risk_reviewer]
  lee: [data_owner]
  jonas: [engineer]
review_routing:
  discovery: [pm_peer]
  requirement: [ops_reviewer, tech_reviewer]
  criteria: [ops_reviewer, tech_reviewer]
  asset: [tech_reviewer]
  risk: [risk_reviewer]
  handoff: [tech_reviewer]
risk_tiers:
  T1: {label: Low, extra_reviewers: [], required_artifacts: [], min_thresholds: {}, human_in_loop: false}
  T2: {label: Medium, extra_reviewers: [risk_reviewer], required_artifacts: [], min_thresholds: {accuracy: 0.85}, human_in_loop: false}
  T3: {label: High, extra_reviewers: [risk_reviewer, data_owner], required_artifacts: [privacy_assessment], min_thresholds: {accuracy: 0.95}, human_in_loop: true}
thresholds:
  accuracy: 0.90
  max_unsafe: 0
"""

# Questionnaire answers that compute to Tier 2.
T2_ANSWERS = dict(
    data_classes=["personal"], autonomy="suggest", audience="customer_facing",
    regulated_decision=False, rationale="Guest messages may contain names and room numbers.",
)


def config():
    from aidlc.config import parse_config
    cfg, issues = parse_config(CONFIG_YAML)
    assert not issues, issues
    return cfg


def make_risk(tier: str = "T2", **kw) -> Artifact:
    fields = {**T2_ANSWERS, "declared_tier": tier}
    for key in list(kw):
        if key in T2_ANSWERS or key in ("declared_tier", "approved_tier"):
            fields[key] = kw.pop(key)
    return make("RISK-001", "risk", **kw, **fields)


def make(
    id: str,
    type: str,
    *,
    feature: str = "FEAT-001",
    version: int = 1,
    status: str = "draft",
    owner: str = "alice",
    parents: tuple[tuple[str, int], ...] = (),
    approvals: tuple[tuple[str, int], ...] = (),
    **extra,
) -> Artifact:
    return Artifact(
        id=id,
        type=type,
        feature=feature,
        title=f"{id} title",
        version=version,
        status=status,
        owner=owner,
        parents=tuple(ParentRef(p, v) for p, v in parents),
        approvals=tuple(Approval(by, v, T1) for by, v in approvals),
        updated_at=T0,
        extra=extra,
        body=f"\n# {id}\n\nBody text.\n",
    )


@pytest.fixture
def repo(tmp_path: Path):
    """Factory writing artifacts into a throwaway repo. Returns the root."""
    (tmp_path / "aidlc.yaml").write_text(CONFIG_YAML)
    feature_dir = tmp_path / "features" / "FEAT-001-guest-triage"

    def write(*items: Artifact, folder: Path = feature_dir) -> Path:
        for a in items:
            art.save(a, folder / art.relative_path(a.type, a.id))
        return tmp_path

    write.root = tmp_path
    write.feature_dir = feature_dir
    return write


def approved_chain() -> list[Artifact]:
    """A small Tier 2 chain, fully valid with every required role approved."""
    team = (("bob", 1), ("priya", 1), ("sam", 1))
    return [
        make_risk(status="approved", approvals=(("sam", 1),), approved_tier="T2"),
        make("DISC-001", "discovery", status="approved", approvals=(("dana", 1), ("sam", 1))),
        make("REQ-001", "requirement", status="approved",
             parents=(("DISC-001", 1),), approvals=team),
        make("AC-001", "criteria", status="approved", parents=(("REQ-001", 1),),
             approvals=team, thresholds={"accuracy": 0.9, "max_unsafe": 0}),
    ]
