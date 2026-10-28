"""Risk profile: the intake questionnaire and deterministic tier computation.

The risk artifact (`risk.md`, RISK-xxx) records the PM's answers and the
tier. The CLI computes the tier; the author may raise it but never set it
below the computed one. Once a tier has been approved, a lower tier only takes
effect when a new version is approved (by the risk reviewer, via routing).
"""

from dataclasses import dataclass
from typing import Any

from aidlc.artifacts import Artifact, Issue
from aidlc.config import Config, Tier, tier_rank

DATA_CLASSES = ("public", "internal", "confidential", "personal", "payment")
AUTONOMY = ("suggest", "act_with_approval", "act_autonomously")
AUDIENCE = ("internal", "customer_facing")
RISK_FIELDS = ("data_classes", "autonomy", "audience", "regulated_decision", "declared_tier", "rationale")


@dataclass(frozen=True)
class Option:
    value: Any
    text: str


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    options: tuple[Option, ...]
    multiple: bool = False


QUESTIONS: tuple[Question, ...] = (
    Question(
        "data_classes",
        "What kinds of data will the AI see? Pick all that apply.",
        (
            Option("public", "Public information anyone could find"),
            Option("internal", "Internal business information"),
            Option("confidential", "Confidential business information (contracts, finances, plans)"),
            Option("personal", "Personal data about people (names, contact details, room numbers)"),
            Option("payment", "Payment or card data"),
        ),
        multiple=True,
    ),
    Question(
        "autonomy",
        "What will the AI do with its output?",
        (
            Option("suggest", "Suggest only; a person decides and acts"),
            Option("act_with_approval", "Act, but only after a person approves each action"),
            Option("act_autonomously", "Act on its own without a person checking first"),
        ),
    ),
    Question(
        "audience",
        "Who sees or is affected by the result?",
        (
            Option("internal", "Only our own staff"),
            Option("customer_facing", "Customers or guests"),
        ),
    ),
    Question(
        "regulated_decision",
        "Does it affect pricing, eligibility, credit or a similar decision about a person?",
        (Option(False, "No"), Option(True, "Yes")),
    ),
)


@dataclass(frozen=True)
class Answers:
    data_classes: tuple[str, ...]
    autonomy: str
    audience: str
    regulated_decision: bool


def compute_tier(a: Answers) -> tuple[str, list[str]]:
    """Tier name plus the plain-language reasons that decided it."""
    sensitive = [c for c in ("personal", "confidential") if c in a.data_classes]
    t3: list[str] = []
    if "payment" in a.data_classes:
        t3.append("it handles payment data")
    if a.regulated_decision:
        t3.append("it affects pricing, eligibility, credit or a similar decision")
    if a.autonomy == "act_autonomously" and sensitive:
        t3.append(f"it acts on its own with {' and '.join(sensitive)} data")
    if t3:
        return "T3", t3

    t2: list[str] = []
    if sensitive:
        t2.append(f"it handles {' and '.join(sensitive)} data")
    if a.audience == "customer_facing":
        t2.append("it is customer-facing")
    if a.autonomy == "act_with_approval":
        t2.append("it acts once a person approves")
    if t2:
        return "T2", t2
    return "T1", ["it uses no sensitive data, is internal and only suggests"]


def answers_of(a: Artifact) -> Answers:
    e = a.extra
    return Answers(
        data_classes=tuple(e["data_classes"]),
        autonomy=e["autonomy"],
        audience=e["audience"],
        regulated_decision=e["regulated_decision"],
    )


def check_answers(raw: dict[str, Any]) -> list[str]:
    """Problems with questionnaire answers, as plain sentences."""
    problems = []
    classes = raw.get("data_classes")
    if not isinstance(classes, list) or not classes or any(c not in DATA_CLASSES for c in classes):
        problems.append(f"data_classes must list one or more of: {', '.join(DATA_CLASSES)}")
    if raw.get("autonomy") not in AUTONOMY:
        problems.append(f"autonomy must be one of: {', '.join(AUTONOMY)}")
    if raw.get("audience") not in AUDIENCE:
        problems.append(f"audience must be one of: {', '.join(AUDIENCE)}")
    if not isinstance(raw.get("regulated_decision"), bool):
        problems.append("regulated_decision must be true or false")
    return problems


def check_fields(a: Artifact, config: Config, where: str) -> list[Issue]:
    """Validate a risk artifact's questionnaire fields and declared tier."""
    issues = [Issue("error", where, p) for p in check_answers(a.extra)]
    declared = a.extra.get("declared_tier")
    if declared not in config.risk_tiers:
        issues.append(Issue("error", where, (
            f"declared_tier {declared!r} must be one of: {', '.join(config.risk_tiers)}")))
    elif not issues:
        computed, reasons = compute_tier(answers_of(a))
        if tier_rank(declared) < tier_rank(computed):
            issues.append(Issue("error", where, (
                f"declared_tier {declared} is lower than the computed {computed} "
                f"({'; '.join(reasons)}); a tier can be raised but not lowered")))
    approved = a.extra.get("approved_tier")
    if approved is not None and approved not in config.risk_tiers:
        issues.append(Issue("error", where, f"approved_tier {approved!r} is not a configured tier"))
    if not str(a.extra.get("rationale") or "").strip():
        issues.append(Issue("warning", where, "has no rationale; say in a sentence why the answers fit"))
    return issues


def effective_tier(a: Artifact, config: Config) -> Tier:
    """The tier that governs the feature. A lowered tier does not take effect
    until the new version is approved: until then the last approved tier holds.
    Assumes `check_fields` passed."""
    names = [a.extra["declared_tier"]]
    approved = a.extra.get("approved_tier")
    if approved in config.risk_tiers and a.status != "approved":
        names.append(approved)
    return config.tier(max(names, key=tier_rank))


def describe(a: Artifact, config: Config) -> list[str]:
    """Questionnaire answers next to the tier, for review requests."""
    labels = {q.key: {o.value: o.text for o in q.options} for q in QUESTIONS}
    lines = []
    for q in QUESTIONS:
        value = a.extra.get(q.key)
        shown = (", ".join(labels[q.key].get(v, str(v)) for v in value)
                 if isinstance(value, list) else labels[q.key].get(value, str(value)))
        lines.append(f"- {q.text} **{shown}**")
    computed, reasons = compute_tier(answers_of(a))
    tier = effective_tier(a, config)
    lines.append(f"- Computed tier: **{config.tier(computed).display}**, because {'; '.join(reasons)}")
    if a.extra["declared_tier"] != computed:
        lines.append(f"- Raised by the author to **{config.tier(a.extra['declared_tier']).display}**")
    if tier.name != a.extra["declared_tier"]:
        lines.append(f"- Still governed by the approved **{tier.display}** until this version is approved")
    if a.extra.get("rationale"):
        lines.append(f"- Rationale: {a.extra['rationale']}")
    return lines


def feature_tier(items: list[Artifact], config: Config) -> Tier | None:
    """The governing tier of a feature, or None without a valid risk profile."""
    profile = next((a for a in items if a.type == "risk"), None)
    if profile is None or any(i.severity == "error" for i in check_fields(profile, config, "")):
        return None
    return effective_tier(profile, config)
