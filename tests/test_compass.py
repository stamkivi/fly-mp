"""The compass is what the page draws, so its two promises need guarding.

The map must be fitted on the humans and **frozen** — every arm, real or rewired, is
projected through the same coefficients, which is how SPEC §4's identical-procedure rule is
honoured here. And a record must land near the party whose behaviour it shares, or the
picture is decoration.

The permutation test gets its own guards because it is the only inferential claim on the
page and its failure mode is silent: a test that returns a small p for exchangeable groups
would manufacture the result.
"""

from __future__ import annotations

import numpy as np
import pytest

from karbes import chorus
from karbes.analysis import compass
from karbes.analysis.votematrix import build
from karbes.riigikogu.model import LOPPHAALETUS, POOLT, VASTU, Vote

FACTIONS = list(compass.CHES_2024)


def chamber(n_votes: int = 220, per_faction: int = 9, seed: int = 0) -> list[Vote]:
    """A synthetic parliament whose votes actually encode the compass.

    Each bill gets a random direction in compass space; a member votes for it when their
    party sits on the positive side of it. That is a spatial voting model, which is the
    thing the map assumes, so recovering the anchors from these votes is the weakest
    possible test — if it fails here it cannot work on a real chamber.
    """
    rng = np.random.default_rng(seed)
    anchors = {f: np.array(compass.CHES_2024[f], float) for f in FACTIONS}
    centre = np.mean(list(anchors.values()), axis=0)
    # Four of the six faction names begin "Eesti", so an id built from the name's prefix
    # silently collapses them into one member each. Index the faction instead.
    members = {f"m{j}_{i}": f for j, f in enumerate(FACTIONS) for i in range(per_faction)}
    names = dict.fromkeys(members, "x")

    votes = []
    for k in range(n_votes):
        d = rng.normal(size=2)
        decisions = {}
        for mid, faction in members.items():
            side = float(np.dot(anchors[faction] - centre, d))
            decisions[mid] = POOLT if side > 0 else VASTU
        votes.append(
            Vote(
                uuid=f"v{k}",
                kind=LOPPHAALETUS,
                when=f"2024-01-{(k % 28) + 1:02d}T10:00:00",
                draft_uuid=f"d{k}",
                draft_title="t",
                in_favor=sum(1 for v in decisions.values() if v == POOLT),
                against=sum(1 for v in decisions.values() if v == VASTU),
                neutral=0,
                abstained=0,
                decisions=decisions,
                factions={m: members[m] for m in decisions},
                names=names,
            )
        )
    return votes


@pytest.fixture(scope="module")
def fitted():
    vm = build(chamber())
    return vm, compass.fit(vm)


def test_members_land_nearest_their_own_party(fitted):
    _, cmap = fitted
    misplaced = [
        m
        for m in cmap.members
        if min(
            FACTIONS,
            key=lambda f: (
                (compass.CHES_2024[f][0] - m["x"]) ** 2 + (compass.CHES_2024[f][1] - m["y"]) ** 2
            ),
        )
        != m["faction"]
    ]
    assert not misplaced, f"{len(misplaced)} of {len(cmap.members)} members landed elsewhere"


def test_the_map_is_frozen_when_a_new_voter_is_projected(fitted):
    """A rewired fly must not be able to move the axes it is measured on."""
    vm, cmap = fitted
    before = cmap.coef.copy()
    cmap.project(vm.stance[0])
    assert np.array_equal(cmap.coef, before)


def test_projection_reproduces_a_members_own_position(fitted):
    vm, cmap = fitted
    row = vm.member_ids.index(cmap.members[0]["member_id"])
    x, y = cmap.project(vm.stance[row])
    # members carry rounded coordinates, so the tolerance is the rounding
    assert (x, y) == pytest.approx((cmap.members[0]["x"], cmap.members[0]["y"]), abs=1e-3)


def test_held_out_error_is_reported_per_axis(fitted):
    _, cmap = fitted
    assert len(cmap.axis_error) == 2
    assert all(e >= 0 for e in cmap.axis_error)


def test_kind_separates_a_shuffle_from_a_rerun_of_one():
    """Counting a shuffle's rerun as another shuffle would shrink the quantity under test."""
    assert chorus._kind("karbes") == "real"
    assert chorus._kind("karbes-phase2") == "real"
    assert chorus._kind("rewired7") == "rewired"
    assert chorus._kind("rewired0-phase1") == "rewired_rerun"


def test_permutation_finds_nothing_when_the_groups_are_exchangeable():
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(24, 2))
    p = chorus._permutation(pts[:4].tolist(), pts[4:].tolist(), draws=2000)
    assert p > 0.1


def test_permutation_finds_a_tight_group_inside_a_loose_one():
    rng = np.random.default_rng(1)
    tight = (rng.normal(size=(5, 2)) * 0.02).tolist()
    loose = (rng.normal(size=(20, 2)) * 3.0).tolist()
    p = chorus._permutation(tight, loose, draws=2000)
    assert p < 0.01
