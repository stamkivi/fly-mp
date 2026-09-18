"""Where the fly sits among the 101, from its voting record.

This is the question a visitor actually arrives with — *could this be the 102nd member?* —
and it cannot be answered from one bill. It needs the record: every contested vote, placed
against the same votes cast by the real chamber.

Two statistics, and the order matters:

* **Agreement per faction** is what reads on a page, but it is contaminated by marginals.
  A voter that says POOLT to everything agrees most with whichever faction says POOLT most,
  which is a fact about base rates rather than about politics.
* **AUC of the continuous readout** against each faction's line is threshold-free, has an
  exact null at 0.5, and is what SPEC §4 pre-registers as primary. Both are reported.

Placement on the chamber's first dimension uses `idealpoint.project`, which locates a new
voter in the *existing* space without letting it move the axes. A fly that redefined the
political space by being added to it would tell us nothing about the real one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from karbes.analysis import idealpoint, votematrix
from karbes.riigikogu.model import POOLT, VASTU

log = logging.getLogger(__name__)


@dataclass
class Seat:
    """Where one fly ended up."""

    votes: int
    decided: int
    marginal_poolt: float
    faction_agreement: dict[str, float]
    faction_auc: dict[str, float]
    best_faction: str | None
    dim1: float | None
    chamber_dim1: list[dict]
    nearest_members: list[dict]


def _stance(code: str, inverted: bool) -> float:
    """The fly's stance on the *bill*, matching how the vote matrix encodes members.

    The emitted code is a vote on the *motion*, so on a `Tagasi lukkamine` POOLT means
    killing the bill. Leaving that flip in made agreement and AUC point opposite ways: the
    readout tracked the government line at AUC 0.69 while the recorded agreement with the
    same faction came out at 0.42.
    """
    if code == POOLT:
        return votematrix.OPPOSE if inverted else votematrix.SUPPORT
    if code == VASTU:
        return votematrix.SUPPORT if inverted else votematrix.OPPOSE
    return votematrix.DECLINE


def place(
    ballots: list,
    vm: votematrix.VoteMatrix,
    space: idealpoint.Space,
    inverted: dict[str, bool] | None = None,
) -> Seat:
    """Score one fly's record against the chamber."""
    inverted = inverted or {}
    by_voting = {b.voting_uuid if hasattr(b, "voting_uuid") else b["voting_uuid"]: b for b in ballots}
    column = {v.uuid: j for j, v in enumerate(vm.votes)}

    latest = vm.latest_faction()
    factions = vm.faction_names()
    agree: dict[str, list[float]] = {f: [] for f in factions}
    auc_scores: dict[str, tuple[list[float], list[bool]]] = {f: ([], []) for f in factions}

    stance = np.full(len(vm.votes), np.nan)
    decided = 0
    turns = []
    for uuid, b in by_voting.items():
        j = column.get(uuid)
        if j is None:
            continue
        code = b.code if hasattr(b, "code") else b["code"]
        turn = b.turn if hasattr(b, "turn") else b["turn"]
        stance[j] = _stance(code, inverted.get(uuid, False))
        turns.append(turn)
        if code in (POOLT, VASTU):
            decided += 1

    # a faction line is a scan over every member, so compute each one once
    for f in factions:
        line = vm.faction_line(f)
        for uuid, b in by_voting.items():
            j = column.get(uuid)
            if j is None or np.isnan(line[j]):
                continue
            code = b.code if hasattr(b, "code") else b["code"]
            turn = b.turn if hasattr(b, "turn") else b["turn"]
            wants = line[j] == votematrix.SUPPORT
            if code in (POOLT, VASTU):
                agree[f].append((_stance(code, inverted.get(uuid, False)) == votematrix.SUPPORT) == wants)
            auc_scores[f][0].append(turn)
            auc_scores[f][1].append(wants)

    from karbes.season import auc

    faction_auc = {}
    for f, (scores, wants) in auc_scores.items():
        if len(scores) > 20:
            a = auc(np.array(scores), np.array(wants))
            faction_auc[f] = round(float(a), 4)
    faction_agreement = {
        f: round(float(np.mean(v)), 4) for f, v in agree.items() if len(v) > 20
    }
    best = max(faction_agreement, key=faction_agreement.get) if faction_agreement else None

    dim1 = None
    try:
        coords = space.project(stance)
        dim1 = round(float(coords[0]), 4)
    except ValueError as exc:
        log.warning("cannot place the fly: %s", exc)

    chamber = [
        {"dim1": round(float(c[0]), 4), "faction": latest.get(m, ""), "name": n}
        for m, c, n in zip(space.member_ids, space.coords, space.names, strict=True)
    ]
    nearest = []
    if dim1 is not None:
        nearest = sorted(chamber, key=lambda m: abs(m["dim1"] - dim1))[:5]

    codes = [b.code if hasattr(b, "code") else b["code"] for b in ballots]
    return Seat(
        votes=len(ballots),
        decided=decided,
        marginal_poolt=round(float(np.mean([c == POOLT for c in codes])), 4),
        faction_agreement=faction_agreement,
        faction_auc=faction_auc,
        best_faction=best,
        dim1=dim1,
        chamber_dim1=chamber,
        nearest_members=nearest,
    )
