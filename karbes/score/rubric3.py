"""Topic rubric derived from what Estonian voters actually rank, not from invention.

`rubric2` fixed the right problem — Stage 1 measured that abstract axes ("is this socially
liberal") disagreed between models at .42-.57 while concrete, checkable ones agreed at
.87-.90, so every question became answerable from the text. But its eight questions were
**authored**, never checked against what Estonian politics is about, and the gap shows:

* No channel at all for the top two topics — cost of living at 42% and healthcare at 32%.
* Two channels for things voters rank near the bottom: nature (5%, a niche topic) and
  regional development (6%).
* Two channels that are not topics at all — `power_over` and `who_decides` — which is why
  a monument-removal bill registered as "moves decisions to the ministries". True, and
  useless.

The channels here are the SALK topic list, in order of measured salience, and the two
topics SALK marks **lõhestav** (important *and* polarising — defence, and economic
competitiveness) are kept rather than merged, because those are the ones that split votes.
Consensus topics are kept too but are not expected to discriminate.

**Framing matters and was measured.** Three forms were tried on the same bills:

| form | example | result |
|---|---|---|
| input / mechanism | "does it increase or reduce military effort?" | reliable but blind: the Bronze Soldier bill scores −0.01 because removing a monument moves no budget |
| contested outcome | "does this make Estonia safer from Russia?" | fires on that bill (+0.44) but confidence collapses to 0.07, and the Weapons Act comes back at −0.57 — the model is guessing at a counterfactual |
| **concrete outcome** | "does it change what everyday life costs?" | confidence 0.53–0.88 across every bill tried |

So each question below names a thing voters care about and asks something checkable about
what the bill does to it. Not what the bill is *about*, and not whether it makes us better
off in some contested sense.
"""

from __future__ import annotations

from karbes.score.rubric2 import AFFECTS, bill_prompt  # noqa: F401  (re-exported, unchanged)

#: (key, question, negative pole, positive pole, SALK salience, divisive)
QUESTIONS: tuple[tuple[str, str, str, str, int, bool], ...] = (
    (
        "cost_of_living",
        "Does it change what everyday life costs — food, housing, transport, bills?",
        "makes everyday life more expensive",
        "makes everyday life cheaper",
        42,
        False,
    ),
    (
        "healthcare",
        "Does it change how easily people get healthcare, or what it is funded with?",
        "narrows access or cuts health funding",
        "widens access or increases health funding",
        32,
        False,
    ),
    (
        "defence",
        "Does it change Estonia's defence or internal security capability?",
        "reduces defence or security capability",
        "increases defence or security capability",
        31,
        True,
    ),
    (
        "social",
        "Does it change benefits, pensions or support for people who are struggling?",
        "cuts support or tightens who qualifies",
        "increases support or widens who qualifies",
        23,
        False,
    ),
    (
        "taxes",
        "Does it change taxes, duties or state fees?",
        "lowers what is collected",
        "raises what is collected",
        21,
        False,
    ),
    (
        "education",
        "Does it change schools, teachers or what education is provided?",
        "reduces provision or funding",
        "expands provision or funding",
        19,
        False,
    ),
    (
        "wages",
        "Does it change wages, or what employers must pay for staff?",
        "lowers pay or employment costs",
        "raises pay or employment costs",
        19,
        False,
    ),
    (
        "energy",
        "Does it change energy prices, or how dependent Estonia is for energy?",
        "raises energy costs or increases dependence",
        "lowers energy costs or increases independence",
        16,
        False,
    ),
    (
        "business",
        "Does it change the cost or difficulty of running a business here?",
        "eases costs or rules on business",
        "adds costs or rules on business",
        16,
        True,
    ),
    (
        "immigration",
        "Does it change immigration, or the rights of people who are not citizens?",
        "restricts immigration or those rights",
        "opens immigration or those rights",
        5,
        False,
    ),
)

KEYS: tuple[str, ...] = tuple(k for k, *_ in QUESTIONS)

#: Short labels naming both poles of each axis, for the page. `rubric2`'s labels collided
#: with the *initiator* ("who gets to decide" against "who tabled it") and read as topics
#: when they are directions of change.
LABELS: dict[str, str] = {
    "cost_of_living": "cost of living",
    "healthcare": "healthcare",
    "defence": "defence and security",
    "social": "benefits and pensions",
    "taxes": "taxes and fees",
    "education": "schools",
    "wages": "wages",
    "energy": "energy",
    "business": "business costs",
    "immigration": "immigration",
}

#: What SALK measured, carried alongside so the page can say why these ten and not others.
SALIENCE: dict[str, int] = {k: s for k, _, _, _, s, _ in QUESTIONS}
DIVISIVE: frozenset[str] = frozenset(k for k, _, _, _, _, d in QUESTIONS if d)


def questions_for_jev(levels: tuple[str, ...]) -> dict:
    """The Jev question block for these channels."""
    return {
        k: {
            "type": "score",
            "instructions": f"{q} Negative means: {neg}. Positive means: {pos}.",
            "criteria": list(levels),
        }
        for k, q, neg, pos, _, _ in QUESTIONS
    }
