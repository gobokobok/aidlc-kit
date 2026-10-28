from aidlc import trace

from conftest import make


def chain(disc_version=1, req_links_to=1):
    return trace.index([
        make("DISC-001", "discovery", version=disc_version),
        make("REQ-001", "requirement", parents=(("DISC-001", req_links_to),)),
        make("REQ-002", "requirement", parents=(("DISC-001", req_links_to),)),
        make("AC-001", "criteria", parents=(("REQ-001", 1),)),
    ])


def test_not_stale_when_versions_match():
    by_id = chain()
    assert not any(trace.is_stale(a, by_id) for a in by_id.values())


def test_stale_when_parent_moves_on():
    by_id = chain(disc_version=2)
    assert trace.is_stale(by_id["REQ-001"], by_id)
    (ref, current), = trace.stale_parents(by_id["REQ-001"], by_id)
    assert (ref.id, ref.version, current) == ("DISC-001", 1, 2)


def test_staleness_is_direct_only():
    # AC-001 still matches REQ-001 v1; it goes stale once REQ-001 is revised.
    by_id = chain(disc_version=2)
    assert not trace.is_stale(by_id["AC-001"], by_id)


def test_missing_parent_is_not_stale():
    by_id = trace.index([make("REQ-001", "requirement", parents=(("DISC-009", 1),))])
    assert not trace.is_stale(by_id["REQ-001"], by_id)


def test_expected_status():
    by_id = chain(disc_version=2)
    assert trace.expected_status(by_id["REQ-001"], by_id) == "stale"
    caught_up = make("REQ-001", "requirement", status="stale", parents=(("DISC-001", 2),))
    assert trace.expected_status(caught_up, by_id) == "draft"
    approved = make("DISC-001", "discovery", version=2, status="approved")
    assert trace.expected_status(approved, by_id) == "approved"


def test_children_and_downstream():
    by_id = chain()
    assert trace.children(by_id)["DISC-001"] == ["REQ-001", "REQ-002"]
    assert trace.downstream("DISC-001", by_id) == ["AC-001", "REQ-001", "REQ-002"]
    assert trace.downstream("AC-001", by_id) == []
