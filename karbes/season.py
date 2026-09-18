"""The voting record: every contested bill, one vote each, read from the brain.

The one-bill walk answers "what does a vote look like". It cannot answer the question a
visitor actually arrives with — *could this thing be the 102nd member?* That needs a record:
hundreds of votes, placed against the 101 real members.

The vote is read from the descending neurons, not from geography. The arena's pot-nearest
rule had made the connectome into a noisy argmax over its own inputs: the largest score
usually won, so the brain only chose which number to look up. Here the bill drives the
antennae, the DNa family produces a turn, and the sign of that turn — past a dead band
measured on the network itself — is the vote.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from karbes import decode, encode, vision
from karbes.engine import Engine
from karbes.graph.populations import Populations
from karbes.riigikogu.model import Bill, Vote
from karbes.score.jev import Scored

log = logging.getLogger(__name__)

#: Seconds of neural time per vote. One shot, no walk: a season is hundreds of bills.
DURATION = 0.5


@dataclass
class Ballot:
    """One bill, one fly, one vote."""

    bill_uuid: str
    voting_uuid: str
    turn: float
    code: str
    advances: bool
    government: bool
    when: str


def cast(
    engine: Engine,
    pops: Populations,
    bill: Bill,
    vote: Vote,
    scored: Scored,
    *,
    sees_initiator: bool,
    bias: float,
    dead_band: float,
    seed: int = 0,
    duration: float = DURATION,
) -> Ballot:
    """One bill through the brain. `sees_initiator` is the only difference between arms."""
    targets, rates = encode.stimulus(scored, pops, engine)
    if sees_initiator:
        vt, vr = vision.stimulus(bill, scored.scores.get("salience", 0.0), pops, engine)
        targets = np.concatenate([targets, vt])
        rates = np.concatenate([rates, vr])
        order = np.argsort(targets)
        targets, rates = targets[order].astype(np.int32), rates[order]

    from karbes import engine as E

    counts = E.run(engine, targets, rates, seed=seed, duration=duration).counts
    turn = decode.turn_index(
        counts,
        engine.positions(pops.dna_left),
        engine.positions(pops.dna_right),
        baseline=bias,
        dead_band=dead_band,
    )
    advances = vote.in_favor > vote.against
    if vote.inverted:
        advances = not advances
    return Ballot(
        bill_uuid=bill.uuid,
        voting_uuid=vote.uuid,
        turn=round(turn.turn, 5),
        code=turn.vote(vote.inverted),
        advances=advances,
        government=bill.government_bill,
        when=vote.when,
    )


def auc(scores: np.ndarray, positive: np.ndarray) -> float:
    """Threshold-free agreement: SPEC's primary statistic."""
    scores, positive = np.asarray(scores, float), np.asarray(positive, bool)
    if positive.all() or not positive.any():
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty(len(scores), float)
    ranks[order] = np.arange(1, len(scores) + 1)
    n1, n0 = positive.sum(), (~positive).sum()
    return float((ranks[positive].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def run(
    engine: Engine,
    pops: Populations,
    bills: dict[str, Bill],
    votes: list[Vote],
    scores: dict[str, Scored],
    *,
    bias: float,
    dead_band: float,
    sees_initiator: bool,
    seed: int = 0,
    limit: int | None = None,
    label: str = "fly",
) -> list[Ballot]:
    """Vote on every contested bill that has a score."""
    seen: dict[str, Vote] = {}
    for v in votes:
        if v.discriminative and v.draft_uuid in scores and v.draft_uuid in bills:
            seen.setdefault(v.draft_uuid, v)
    order = sorted(seen, key=lambda u: seen[u].when)
    if limit:
        order = order[:limit]
    out = []
    for n, uuid in enumerate(order, 1):
        out.append(
            cast(
                engine, pops, bills[uuid], seen[uuid], scores[uuid],
                sees_initiator=sees_initiator, bias=bias, dead_band=dead_band, seed=seed,
            )
        )
        if n % 50 == 0:
            log.info("%s: %d/%d", label, n, len(order))
    return out
