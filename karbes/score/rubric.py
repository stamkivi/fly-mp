"""The topic rubric: a bill reduced to eight signed axes plus salience.

**The rubric is initiator-blind, and that is load-bearing.** Stage 0's T5 ablation showed that
one bit — whether the government or an MP tabled the bill — moves prediction of faction lines
from ~.74 to ~.90, because the coalition backs government bills and kills opposition ones. That
is procedural signalling, not content. If the model sees the initiator, the scores launder that
bit and Kärbes's apparent performance is leakage rather than comprehension.

So the prompt receives exactly what the T5 `content` baseline received — title, summary text,
subject descriptors, leading committee, draft type — and nothing about who tabled it, when, or
how anyone voted.
"""

from __future__ import annotations

from karbes.riigikogu.model import Bill

#: Signed axes, each in [-1, +1]. Chosen for Estonian politics rather than imported
#: culture-war framings. Whether eight *independent* dimensions actually exist is a
#: hypothesis the pilot tests: if PC1 explains >70% of variance, it does not.
AXES: tuple[tuple[str, str, str], ...] = (
    (
        "fiscal",
        "austerity, lower taxes, smaller budgets",
        "higher spending, redistribution, larger budgets",
    ),
    (
        "market",
        "deregulation, private provision, competition",
        "state regulation, public provision, worker protection",
    ),
    (
        "defence",
        "lower military spending, de-escalation",
        "higher military spending, hard security, deterrence against Russia",
    ),
    (
        "eu",
        "national sovereignty, resisting EU competence",
        "deeper EU integration, adopting EU rules",
    ),
    (
        "social",
        "traditional and conservative social policy",
        "liberal and permissive social policy, minority rights",
    ),
    (
        "green",
        "cost and industry first, slower transition",
        "climate ambition, environmental protection",
    ),
    ("regional", "urban and central priorities", "rural, regional and peripheral priorities"),
    (
        "state_power",
        "civil liberties, privacy, limits on the state",
        "state capacity, enforcement, surveillance powers",
    ),
)

AXIS_NAMES: tuple[str, ...] = tuple(a for a, _, _ in AXES)
SALIENCE = "salience"
FIELDS: tuple[str, ...] = (*AXIS_NAMES, SALIENCE)

SCHEMA = {
    "name": "bill_topic_scores",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": list(FIELDS),
        "properties": {
            **{
                axis: {
                    "type": "number",
                    "minimum": -1,
                    "maximum": 1,
                    "description": f"-1 = {neg}; +1 = {pos}; 0 = neutral or not engaged",
                }
                for axis, neg, pos in AXES
            },
            SALIENCE: {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": (
                    "0 = purely technical, procedural or a routine ratification with no "
                    "ideological content; 1 = a central political controversy"
                ),
            },
        },
    },
}

SYSTEM_PROMPT = """You score Estonian draft legislation on fixed policy dimensions.

You will be given a bill's title, its official summary, its subject descriptors, the leading
parliamentary committee, and its draft type. The text is in Estonian.

Return a score on each dimension in the range -1 to +1:

{axes}

Also return `salience` from 0 to 1: how ideologically contested the bill is at all. Technical
amendments, ratifications of international agreements, and routine legal housekeeping should
score near 0 even if they touch a policy area. A bill at the centre of political argument
scores near 1.

Rules:
- Score what the bill DOES, not the policy area it belongs to. A technical amendment to an
  environmental law is not a green bill; it is a technical bill.
- Use 0 on any dimension the bill does not engage. Do not spread small values across every
  dimension.
- Use the full range. If a bill clearly pushes one direction, say so with a large magnitude.
- Judge the bill on its own terms. Do not speculate about who proposed it or who would
  support it.

Return only the JSON object."""


def system_prompt() -> str:
    lines = [f"- {axis}: -1 = {neg} / +1 = {pos}" for axis, neg, pos in AXES]
    return SYSTEM_PROMPT.format(axes="\n".join(lines))


def bill_prompt(bill: Bill, max_chars: int = 5000) -> str:
    """Render a bill for scoring. Deliberately omits the initiator and all vote data."""
    parts = [f"PEALKIRI: {bill.title}"]
    if bill.draft_type:
        parts.append(f"EELNÕU LIIK: {bill.draft_type}")
    if bill.committee:
        parts.append(f"JUHTIVKOMISJON: {bill.committee}")
    if bill.descriptors:
        parts.append(f"MÄRKSÕNAD: {', '.join(bill.descriptors)}")
    text = bill.introduction.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " […]"
    parts.append(f"\nSELETUS:\n{text}")
    return "\n".join(parts)


def leak_probe_prompt(bill: Bill) -> str:
    """Ask the model to predict the vote outright — the leakage audit.

    If a cheap model can call the outcome from bill text alone, then "the fly decided" is not
    a true sentence and the pipeline is contaminated before the connectome is involved.
    """
    return (
        bill_prompt(bill)
        + "\n\nWill the Estonian parliament pass this bill, and which factions will vote "
        "against it? Answer in one short sentence."
    )


def to_vector(scores: dict) -> list[float]:
    return [float(scores[f]) for f in FIELDS]
