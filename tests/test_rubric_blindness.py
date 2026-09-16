"""The rubric must not see who tabled the bill.

Stage 0's T5 ablation showed that one bit — government vs MP initiator — moves prediction of
faction lines from ~.74 to ~.90. If it reaches the model, the topic scores launder it and
Kärbes's apparent performance is leakage rather than comprehension. This is the single
easiest way to invalidate the whole study, and it would be invisible in the results.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from karbes.riigikogu.corpus import load_bills
from karbes.riigikogu.model import Bill
from karbes.score import rubric

CACHE = Path("data/raw")

#: Estonian phrasings that state who tabled a bill, as opposed to bills *about* the
#: government, which are legitimate content.
INITIATOR_PHRASE = re.compile(
    r"(Vabariigi Valitsuse[a-z]*\s+algatatud"
    r"|algatatud\s+Vabariigi Valitsuse"
    r"|Riigikogu\s+liikme(te)?\s+[^.]{0,80}algatatud"
    r"|fraktsiooni\s+algatatud"
    r"|algatas\s+Vabariigi Valitsus)",
    re.IGNORECASE,
)


def a_bill(**kw) -> Bill:
    base = {
        "uuid": "u", "title": "Test", "mark": 1, "introduction": "Seletus.",
        "descriptors": ("maks",), "initiators": ("Vabariigi Valitsus",),
        "committee": "Rahanduskomisjon", "draft_type": "SE", "initiated": "2025-01-01",
    }
    base.update(kw)
    return Bill(**base)


def test_prompt_omits_the_initiator_field():
    bill = a_bill(initiators=("Vabariigi Valitsus",))
    prompt = rubric.bill_prompt(bill)
    assert "Vabariigi Valitsus" not in prompt
    assert bill.government_bill is True  # the field exists; it just must not be rendered


def test_prompt_omits_named_mp_initiators():
    bill = a_bill(initiators=("Riigikogu liige Jaak Aab", "Riigikogu liige Mari Maa"))
    prompt = rubric.bill_prompt(bill)
    assert "Jaak Aab" not in prompt
    assert "Mari Maa" not in prompt


def test_prompt_carries_the_content_features_t5_used():
    """The fair comparison against the .74 content ceiling requires the same inputs."""
    bill = a_bill(descriptors=("kaitsepoliitika", "sõda"), committee="Riigikaitsekomisjon")
    prompt = rubric.bill_prompt(bill)
    assert "kaitsepoliitika" in prompt
    assert "Riigikaitsekomisjon" in prompt
    assert "SE" in prompt


def test_system_prompt_forbids_speculating_about_the_proposer():
    assert "who proposed it" in rubric.system_prompt()


def test_schema_is_strict_and_complete():
    assert rubric.SCHEMA["strict"] is True
    assert rubric.SCHEMA["schema"]["additionalProperties"] is False
    assert set(rubric.SCHEMA["schema"]["required"]) == set(rubric.FIELDS)
    assert len(rubric.FIELDS) == 9


def test_real_bill_text_does_not_state_the_initiator():
    """Blinding the field is useless if the summary says it anyway. It does not — but if a
    future corpus changes that, this catches it before the scores are contaminated."""
    if not (CACHE / "draft").exists():
        pytest.skip("no cached bills")
    bills = [b for b in load_bills(CACHE).values() if b.has_text]
    if not bills:
        pytest.skip("no bills with text")
    leaking = [b.uuid for b in bills if INITIATOR_PHRASE.search(f"{b.title} {b.introduction}")]
    assert not leaking, f"{len(leaking)} of {len(bills)} bills name their initiator in text"
