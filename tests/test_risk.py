import pytest

from aidlc import risk
from aidlc.risk import Answers, compute_tier

from conftest import config, make, make_risk


def answers(classes=("internal",), autonomy="suggest", audience="internal", regulated=False):
    return Answers(tuple(classes), autonomy, audience, regulated)


@pytest.mark.parametrize(
    ("a", "tier"),
    [
        (answers(), "T1"),
        (answers(classes=("public", "internal")), "T1"),
        (answers(classes=("personal",)), "T2"),
        (answers(classes=("confidential",)), "T2"),
        (answers(audience="customer_facing"), "T2"),
        (answers(autonomy="act_with_approval"), "T2"),
        (answers(autonomy="act_autonomously"), "T1"),  # autonomous, but nothing sensitive
        (answers(classes=("payment",)), "T3"),
        (answers(regulated=True), "T3"),
        (answers(classes=("personal",), autonomy="act_autonomously"), "T3"),
        (answers(classes=("confidential",), autonomy="act_autonomously"), "T3"),
    ],
)
def test_compute_tier(a, tier):
    assert compute_tier(a)[0] == tier


def test_tier_reasons_are_plain_language():
    tier, reasons = compute_tier(answers(classes=("personal",), audience="customer_facing"))
    assert tier == "T2"
    assert reasons == ["it handles personal data", "it is customer-facing"]


def test_questionnaire_covers_every_answer_field():
    assert [q.key for q in risk.QUESTIONS] == ["data_classes", "autonomy", "audience", "regulated_decision"]
    assert {o.value for o in risk.QUESTIONS[0].options} == set(risk.DATA_CLASSES)


def errors(a):
    return [i.message for i in risk.check_fields(a, config(), "x") if i.severity == "error"]


def test_valid_profile():
    assert errors(make_risk()) == []


def test_author_may_raise_tier():
    assert errors(make_risk("T3")) == []


def test_declared_tier_below_computed_is_blocked():
    errs = errors(make_risk("T1"))
    assert any("lower than the computed T2" in e for e in errs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("data_classes", []),
        ("data_classes", ["secret"]),
        ("autonomy", "maybe"),
        ("audience", "everyone"),
        ("regulated_decision", "no"),
        ("declared_tier", "T9"),
        ("approved_tier", "high"),
    ],
)
def test_bad_answers(field, value):
    assert errors(make_risk(**{field: value}))


def test_missing_rationale_warns():
    issues = risk.check_fields(make_risk(rationale=""), config(), "x")
    assert [i.severity for i in issues] == ["warning"]


def test_lowered_tier_waits_for_approval():
    cfg = config()
    # Approved at T3, author's new draft says T2: T3 still governs.
    draft = make_risk("T2", version=2, approved_tier="T3")
    assert risk.effective_tier(draft, cfg).name == "T3"
    # Once the new version is approved (risk_reviewer via routing) T2 applies.
    approved = make_risk("T2", version=2, status="approved", approved_tier="T2",
                         approvals=(("sam", 2),))
    assert risk.effective_tier(approved, cfg).name == "T2"


def test_raised_tier_applies_immediately():
    draft = make_risk("T3", version=2, approved_tier="T2")
    assert risk.effective_tier(draft, config()).name == "T3"


def test_feature_tier():
    cfg = config()
    assert risk.feature_tier([make("DISC-001", "discovery")], cfg) is None
    assert risk.feature_tier([make_risk()], cfg).name == "T2"
    assert risk.feature_tier([make_risk("T1")], cfg) is None  # invalid profile


def test_describe_shows_answers_next_to_tier():
    text = "\n".join(risk.describe(make_risk("T3", version=2, approved_tier="T2"), config()))
    assert "Personal data about people" in text
    assert "Computed tier: **Tier 2 (Medium)**, because it handles personal data; it is customer-facing" in text
    assert "Raised by the author to **Tier 3 (High)**" in text
