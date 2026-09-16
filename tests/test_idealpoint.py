"""The scaling is the project's primary artifact, so its guarantees need guarding.

Two properties matter most: absence must not be read as a centrist position, and adding a
new member must not move the axes. If either breaks, Kärbes's reported seat is an artefact.
"""

from __future__ import annotations

import numpy as np
import pytest

from karbes.analysis import idealpoint as ip
from karbes.analysis.votematrix import build
from karbes.riigikogu.model import EI_HAALETANUD, LOPPHAALETUS, POOLT, PUUDUB, VASTU, Vote


def synthetic(n_votes: int = 60, attendance: float = 0.6) -> list[Vote]:
    """Two disciplined blocs, plus an often-absent member who votes with the left.

    `attendance` stays above the MIN_VOTES_PER_MEMBER threshold by default, so the
    absentee is actually placed rather than dropped for a thin record.
    """
    rng = np.random.default_rng(0)
    left = [f"L{i}" for i in range(6)]
    right = [f"R{i}" for i in range(6)]
    absentee = "A0"
    names = dict.fromkeys([*left, *right, absentee], "x")
    votes = []
    for k in range(n_votes):
        decisions = {}
        for m in left:
            decisions[m] = POOLT
        for m in right:
            decisions[m] = VASTU
        # The absentee shares the left's view but is often away.
        decisions[absentee] = POOLT if rng.random() < attendance else PUUDUB
        votes.append(
            Vote(
                uuid=f"v{k}", kind=LOPPHAALETUS, when=f"2024-01-{(k % 28) + 1:02d}T10:00:00",
                draft_uuid=f"d{k}", draft_title="t",
                in_favor=sum(1 for d in decisions.values() if d == POOLT),
                against=sum(1 for d in decisions.values() if d == VASTU),
                neutral=0, abstained=0,
                decisions=decisions, factions=dict.fromkeys(decisions, "F"), names=names,
            )
        )
    return votes


def test_blocs_separate_on_dimension_one():
    vm = build(synthetic())
    sp = ip.fit(vm, dims=2)
    left = np.mean([sp.coord_of(f"L{i}")[0] for i in range(6)])
    right = np.mean([sp.coord_of(f"R{i}")[0] for i in range(6)])
    assert abs(left - right) > 1.0


def test_dimension_one_dominates_a_one_dimensional_chamber():
    sp = ip.fit(build(synthetic()), dims=2)
    assert sp.explained[0] > 0.5
    assert sp.explained[0] > sp.explained[1]


def test_absence_does_not_drag_a_member_to_the_centre():
    """PUUDUB is missing data. If it were read as 0, the absentee would land between the
    blocs instead of with the one they actually vote with."""
    vm = build(synthetic(n_votes=80, attendance=0.45))
    sp = ip.fit(vm, dims=2)
    left = np.mean([sp.coord_of(f"L{i}")[0] for i in range(6)])
    right = np.mean([sp.coord_of(f"R{i}")[0] for i in range(6)])
    absentee = sp.coord_of("A0")[0]
    assert abs(absentee - left) < abs(absentee - right)


def test_projection_round_trips():
    """Projecting a member's own record must reproduce their fitted coordinate."""
    vm = build(synthetic())
    sp = ip.fit(vm, dims=2)
    for mid in ("L0", "R3"):
        stance = vm.stance[vm.member_ids.index(mid)]
        assert np.allclose(sp.project(stance), sp.coord_of(mid), atol=1e-6)


def test_projection_does_not_move_the_axes():
    """A new voter is located in the chamber's space, never allowed to redefine it."""
    vm = build(synthetic())
    sp = ip.fit(vm, dims=2)
    before = sp.vote_loadings.copy()
    sp.project(vm.stance[vm.member_ids.index("L0")])
    assert np.array_equal(sp.vote_loadings, before)


def test_a_thin_record_is_excluded_from_the_fit():
    """A member who barely voted cannot be given a coordinate the data does not support."""
    vm = build(synthetic(n_votes=40, attendance=0.1))
    sp = ip.fit(vm, dims=2)
    assert "A0" not in sp.member_ids
    assert "L0" in sp.member_ids


def test_projection_rejects_a_thin_record():
    """A fly that voted three times cannot be given a seat."""
    vm = build(synthetic())
    sp = ip.fit(vm, dims=2)
    thin = np.full(vm.shape[1], np.nan)
    thin[:3] = 1.0
    with pytest.raises(ValueError, match="need"):
        sp.project(thin)


def test_projection_rejects_a_mismatched_length():
    vm = build(synthetic())
    sp = ip.fit(vm, dims=2)
    with pytest.raises(ValueError, match="votes"):
        sp.project(np.ones(7))


def test_declining_is_a_position_but_absence_is_not():
    """EI_HAALETANUD is a choice and enters as 0; PUUDUB is missing and enters as nan."""
    votes = synthetic(40)
    d = dict(votes[0].decisions)
    d["L0"], d["L1"] = EI_HAALETANUD, PUUDUB
    votes[0] = Vote(**{**votes[0].__dict__, "decisions": d})
    vm = build(votes)
    assert vm.stance[vm.member_ids.index("L0"), 0] == 0.0
    assert np.isnan(vm.stance[vm.member_ids.index("L1"), 0])


def test_classification_accuracy_is_high_for_a_clean_chamber():
    vm = build(synthetic())
    sp = ip.fit(vm, dims=2)
    assert ip.classification_accuracy(sp, vm) > 0.95
