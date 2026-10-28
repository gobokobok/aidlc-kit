from datetime import datetime, timezone
from pathlib import Path

import pytest

from aidlc import artifacts as art
from aidlc.artifacts import Approval, Artifact, ParentRef

T0 = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)


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
    (tmp_path / "aidlc.yaml").write_text("display_name: Test Kit\n")
    feature_dir = tmp_path / "features" / "FEAT-001-guest-triage"

    def write(*items: Artifact, folder: Path = feature_dir) -> Path:
        for a in items:
            art.save(a, folder / art.relative_path(a.type, a.id))
        return tmp_path

    write.root = tmp_path
    write.feature_dir = feature_dir
    return write


def approved_chain() -> list[Artifact]:
    """A small, fully valid and approved chain."""
    return [
        make("DISC-001", "discovery", status="approved", approvals=(("bob", 1),)),
        make("REQ-001", "requirement", status="approved",
             parents=(("DISC-001", 1),), approvals=(("bob", 1),)),
        make("AC-001", "criteria", status="approved", parents=(("REQ-001", 1),),
             approvals=(("bob", 1),), thresholds={"accuracy": 0.9, "max_unsafe": 0}),
    ]
