"""Concrete-question rubric: what a bill *does*, not where it sits ideologically.

Stage 1 showed the split cleanly. Axes that two models agreed on were checkable and
topical — eu .90, green .88, fiscal .87, defence .87. Axes they disagreed on were
abstractions — market .42, regional .52, state_power .55, social .57 — because "is this
socially liberal" is a judgement about a bill rather than a property of it.

So every channel here is phrased as a question answerable from the text. That should lift
inter-model agreement for the same reason the topical axes already scored high, and it
should raise *between-bill* variance, which is what the readout needs: under the old
rubric most bills scored near zero on most axes, so every stimulus looked alike.

It also makes the channels legible on screen. A reader can judge "raises what people pay
the state: +0.7" for themselves. They cannot judge "fiscal: -0.4".
"""

from __future__ import annotations

from karbes.riigikogu.model import Bill

#: (key, question, negative pole, positive pole)
QUESTIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "pay",
        "Does it change what people or businesses pay the state?",
        "lowers taxes, fees or charges",
        "raises taxes, fees or charges",
    ),
    (
        "spend",
        "Does it change what the state spends or hands out?",
        "cuts spending or a benefit",
        "increases spending or creates a benefit",
    ),
    (
        "burden",
        "Who carries the new obligation it creates?",
        "businesses and employers",
        "individuals and households",
    ),
    (
        "place",
        "Does it treat parts of the country differently?",
        "favours cities, especially Tallinn",
        "favours rural and regional areas",
    ),
    (
        "power_over",
        "Do officials gain or lose power over a person?",
        "removes a restriction, penalty or surveillance power",
        "adds a restriction, penalty or surveillance power",
    ),
    (
        "who_decides",
        "Where does decision-making move?",
        "towards parliament or local government",
        "towards ministries or the government",
    ),
    (
        "nature",
        "Nature, or the cost of using it?",
        "lowers cost and eases environmental obligations",
        "protects nature, land or climate at a cost",
    ),
    (
        "security",
        "Is it about defence, Russia or civil protection?",
        "reduces military or security effort",
        "increases military or security effort",
    ),
)

KEYS: tuple[str, ...] = tuple(k for k, _, _, _ in QUESTIONS)

#: Short human labels. The keys are fine in a manifest and useless on a page: nobody
#: arriving cold knows what "burden" or "place" is supposed to mean.
LABELS: dict[str, str] = {
    "pay": "what people pay",
    "spend": "what the state spends",
    "burden": "who carries it",
    "place": "city or countryside",
    "power_over": "power over people",
    "who_decides": "who gets to decide",
    "nature": "nature",
    "security": "defence",
}

#: Plain tags, for display and for the metadata control. They do not drive neurons.
AFFECTS = (
    "children",
    "pensioners",
    "workers",
    "farmers",
    "businesses",
    "drivers",
    "patients",
    "students",
    "a language or ethnic group",
)

SALIENCE = "salience"
FIELDS: tuple[str, ...] = (*KEYS, SALIENCE)

SCHEMA = {
    "name": "bill_effects",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [*FIELDS, "affects"],
        "properties": {
            **{
                k: {
                    "type": "number",
                    "minimum": -1,
                    "maximum": 1,
                    "description": f"{q} -1 = {neg}; +1 = {pos}; 0 = it does not",
                }
                for k, q, neg, pos in QUESTIONS
            },
            SALIENCE: {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "0 = pure housekeeping that changes no policy; 1 = a central controversy",
            },
            "affects": {
                "type": "array",
                "items": {"type": "string", "enum": list(AFFECTS)},
                "description": "Groups the bill visibly changes something for. May be empty.",
            },
        },
    },
}

SYSTEM = """You read Estonian draft legislation and answer fixed factual questions about
what the bill does. You are not judging whether it is good, and not placing it on a
political spectrum.

Answer each question from -1 to +1:

{qs}

Also return `salience` from 0 to 1 — how much this bill actually changes. Renumbering,
corrected cross-references and deadline shifts score near 0. And `affects`: which of these
groups the bill visibly changes something for, or an empty list: {groups}.

Rules:
- Almost every Estonian bill is formally an amendment. Judge the change it makes, not its form.
- Answer 0 when the bill genuinely does not do that thing. Do not spread small values around.
- When a bill clearly does something, say so with a large number, not 0.2.
- Answer only from the text. Do not speculate about who proposed it or who would support it.

Return only the JSON object."""


def system_prompt() -> str:
    qs = "\n".join(f"- {k}: {q}\n    -1 = {neg}\n    +1 = {pos}" for k, q, neg, pos in QUESTIONS)
    return SYSTEM.format(qs=qs, groups=", ".join(AFFECTS))


def bill_prompt(bill: Bill, max_chars: int = 5000) -> str:
    """Same inputs as the Stage 0 content baseline. Never the initiator."""
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
