"""The 101 x V vote matrix and the faction bookkeeping every later stage reads."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from karbes.riigikogu.model import (
    EI_HAALETANUD,
    ERAPOOLETU,
    POOLT,
    PUUDUB,
    VASTU,
    Vote,
)

#: Formal label for MPs who belong to no faction. Mostly defectors who still vote with
#: their old or new party, so this is never treated as a bloc.
CROSSBENCH = "Fraktsiooni mittekuuluvad Riigikogu liikmed"

# Stance encoding for the matrix: +1 supports the bill, -1 opposes, 0 declined, nan absent.
SUPPORT, OPPOSE, DECLINE = 1.0, -1.0, 0.0


@dataclass
class VoteMatrix:
    """Members x votes, encoded as a stance on the *bill* rather than on the motion.

    Rejection motions are polarity-inverted at construction, so every column means the
    same thing: +1 = this member wanted the bill to advance.
    """

    member_ids: list[str]
    names: list[str]
    votes: list[Vote]
    stance: np.ndarray  # (members, votes): +1 / -1 / 0 / nan
    faction: np.ndarray  # (members, votes) of faction name at that vote, dtype=object

    @property
    def shape(self) -> tuple[int, int]:
        return self.stance.shape

    def factions_at(self, j: int) -> np.ndarray:
        return self.faction[:, j]

    def latest_faction(self) -> dict[str, str]:
        """Each member's faction at the most recent vote where they appear."""
        out: dict[str, str] = {}
        for i, mid in enumerate(self.member_ids):
            for j in range(self.faction.shape[1] - 1, -1, -1):
                f = self.faction[i, j]
                if f:
                    out[mid] = f
                    break
        return out

    def faction_names(self, include_crossbench: bool = False) -> list[str]:
        names = {f for f in self.faction.ravel().tolist() if f}
        if not include_crossbench:
            names.discard(CROSSBENCH)
        return sorted(names)

    def faction_line(self, faction: str) -> np.ndarray:
        """Per vote: the faction's majority stance (+1/-1), or nan if it had no majority."""
        n = self.stance.shape[1]
        line = np.full(n, np.nan)
        for j in range(n):
            members = self.faction[:, j] == faction
            col = self.stance[members, j]
            col = col[~np.isnan(col)]
            pro = float((col == SUPPORT).sum())
            con = float((col == OPPOSE).sum())
            if pro > con:
                line[j] = SUPPORT
            elif con > pro:
                line[j] = OPPOSE
        return line

    def subset(self, mask: np.ndarray) -> VoteMatrix:
        idx = np.flatnonzero(mask)
        return VoteMatrix(
            member_ids=self.member_ids,
            names=self.names,
            votes=[self.votes[j] for j in idx],
            stance=self.stance[:, idx],
            faction=self.faction[:, idx],
        )


def build(votes: list[Vote]) -> VoteMatrix:
    """Assemble the matrix. Members are every MP who appears in any voting."""
    member_ids: list[str] = []
    seen: dict[str, str] = {}
    for v in votes:
        for mid, name in v.names.items():
            if mid not in seen:
                seen[mid] = name
                member_ids.append(mid)

    index = {mid: i for i, mid in enumerate(member_ids)}
    stance = np.full((len(member_ids), len(votes)), np.nan)
    faction = np.empty((len(member_ids), len(votes)), dtype=object)
    faction[:] = ""

    for j, v in enumerate(votes):
        for mid, decision in v.decisions.items():
            i = index[mid]
            faction[i, j] = v.factions.get(mid, "")
            if decision == PUUDUB:
                continue  # absent: missing, not a position
            if decision in (EI_HAALETANUD, ERAPOOLETU):
                stance[i, j] = DECLINE
            elif decision == POOLT:
                stance[i, j] = OPPOSE if v.inverted else SUPPORT
            elif decision == VASTU:
                stance[i, j] = SUPPORT if v.inverted else OPPOSE

    return VoteMatrix(
        member_ids=member_ids,
        names=[seen[m] for m in member_ids],
        votes=votes,
        stance=stance,
        faction=faction,
    )


def discriminative_mask(votes: list[Vote]) -> np.ndarray:
    return np.array([v.discriminative for v in votes], dtype=bool)
