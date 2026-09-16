"""Polarity is the easiest place to silently invert the whole result.

On a `Tagasi lükkamine` (motion to reject), POOLT means *kill the bill*. Every column of
the vote matrix must mean the same thing — +1 = this member wanted the bill to advance —
or the fly is compared against a mixture of two opposite conventions.
"""

from __future__ import annotations

import numpy as np

from karbes.analysis import votematrix as vmx
from karbes.riigikogu.model import (
    EI_HAALETANUD,
    LOPPHAALETUS,
    POOLT,
    PUUDUB,
    TAGASI_LUKKAMINE,
    VASTU,
    Vote,
)

MEMBERS = {"a": "Ants", "b": "Bert", "c": "Carl"}


def make_vote(kind: str, decisions: dict[str, str], **kw) -> Vote:
    return Vote(
        uuid=kw.get("uuid", "v1"),
        kind=kind,
        when=kw.get("when", "2025-01-01T10:00:00"),
        draft_uuid=kw.get("draft_uuid", "d1"),
        draft_title="Test",
        in_favor=sum(1 for d in decisions.values() if d == POOLT),
        against=sum(1 for d in decisions.values() if d == VASTU),
        neutral=0,
        abstained=0,
        decisions=decisions,
        factions=dict.fromkeys(decisions, kw.get("faction", "F")),
        names={k: MEMBERS[k] for k in decisions},
    )


def test_final_vote_poolt_means_supports_bill():
    v = make_vote(LOPPHAALETUS, {"a": POOLT, "b": VASTU})
    assert v.supports_bill("a") is True
    assert v.supports_bill("b") is False


def test_rejection_motion_poolt_means_opposes_bill():
    """The inversion. POOLT on a motion to reject is a vote against the bill."""
    v = make_vote(TAGASI_LUKKAMINE, {"a": POOLT, "b": VASTU})
    assert v.supports_bill("a") is False
    assert v.supports_bill("b") is True


def test_declining_is_not_a_position():
    v = make_vote(LOPPHAALETUS, {"a": EI_HAALETANUD, "b": PUUDUB})
    assert v.supports_bill("a") is None
    assert v.supports_bill("b") is None


def test_matrix_columns_share_one_convention():
    """Same substantive stance, opposite button, opposite motion -> identical column value."""
    final = make_vote(LOPPHAALETUS, {"a": POOLT, "b": VASTU}, uuid="v1")
    reject = make_vote(
        TAGASI_LUKKAMINE, {"a": VASTU, "b": POOLT}, uuid="v2", when="2025-01-02T10:00:00"
    )
    m = vmx.build([final, reject])
    ia, ib = m.member_ids.index("a"), m.member_ids.index("b")
    assert m.stance[ia, 0] == m.stance[ia, 1] == vmx.SUPPORT
    assert m.stance[ib, 0] == m.stance[ib, 1] == vmx.OPPOSE


def test_absent_is_nan_not_zero():
    """Absence is missing data. Encoding it as 0 would make it look like a deliberate
    decline and inflate every agreement denominator."""
    m = vmx.build([make_vote(LOPPHAALETUS, {"a": PUUDUB, "b": EI_HAALETANUD})])
    ia, ib = m.member_ids.index("a"), m.member_ids.index("b")
    assert np.isnan(m.stance[ia, 0])
    assert m.stance[ib, 0] == vmx.DECLINE


def test_faction_line_is_majority_stance():
    decisions = {"a": POOLT, "b": POOLT, "c": VASTU}
    m = vmx.build([make_vote(LOPPHAALETUS, decisions)])
    assert m.faction_line("F")[0] == vmx.SUPPORT


def test_faction_line_is_nan_when_tied():
    m = vmx.build([make_vote(LOPPHAALETUS, {"a": POOLT, "b": VASTU})])
    assert np.isnan(m.faction_line("F")[0])


def test_discriminative_requires_both_sides():
    lopsided = make_vote(LOPPHAALETUS, dict.fromkeys(MEMBERS, POOLT))
    assert not lopsided.discriminative
    split = Vote(
        uuid="v",
        kind=LOPPHAALETUS,
        when="",
        draft_uuid="d",
        draft_title="",
        in_favor=60,
        against=20,
        neutral=0,
        abstained=21,
        decisions={},
        factions={},
        names={},
    )
    assert split.discriminative


def test_crossbench_excluded_from_faction_targets():
    """The crossbench is formal registration, not a bloc, and is never a match target."""
    v = make_vote(LOPPHAALETUS, {"a": POOLT, "b": VASTU})
    v = Vote(**{**v.__dict__, "factions": {"a": vmx.CROSSBENCH, "b": "Isamaa fraktsioon"}})
    m = vmx.build([v])
    assert vmx.CROSSBENCH not in m.faction_names()
    assert vmx.CROSSBENCH in m.faction_names(include_crossbench=True)
