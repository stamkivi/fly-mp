"""The season bundle: a whole voting record, and where it puts the fly.

The one-bill walk shows what a vote looks like. It cannot answer what a visitor arrives
wanting to know — *could this be the 102nd member?* — because one vote is one data point.
This packages the record: every contested bill, the fly's vote, and its position among the
101 recomputed as the record accumulates, so the seat is watched emerging rather than
asserted at the end.
"""

from __future__ import annotations

import logging

import numpy as np

from karbes.analysis import idealpoint, seat, votematrix
from karbes.riigikogu.model import EI_HAALETANUD, POOLT, VASTU

log = logging.getLogger(__name__)

SHORT = {
    "Eesti Reformierakonna fraktsioon": "REF",
    "Eesti 200 fraktsioon": "E200",
    "Sotsiaaldemokraatliku Erakonna fraktsioon": "SDE",
    "Isamaa fraktsioon": "Isamaa",
    "Eesti Konservatiivse Rahvaerakonna fraktsioon": "EKRE",
    "Eesti Keskerakonna fraktsioon": "KESK",
    "Fraktsiooni mittekuuluvad Riigikogu liikmed": "none",
}
COLOUR = {
    "REF": "#E0A200",
    "E200": "#D4267E",
    "SDE": "#D14B4E",
    "Isamaa": "#5F9BC4",
    "EKRE": "#2A3DA0",
    "KESK": "#2F9B6B",
    "none": "#A9A49B",
}

#: Real members decline rarely, so the dead band is set to make the fly decline about as
#: often. AUC is threshold-free and does not move with it; only the POOLT/VASTU marginal
#: does, and the sensitivity is reported rather than hidden.
ABSTAIN_TARGET = 0.08

#: How many points on the convergence curve. The projection is a least squares per point.
CHECKPOINTS = 40


def recode(ballots: list[dict], inverted: dict[str, bool]) -> tuple[float, float]:
    """Centre the readout on its own median and pick the dead band. Returns both.

    **Centring is not outcome tuning.** The informed arm came out voting VASTU on 76% of
    bills, which is a constant offset in the readout rather than a view about the bills:
    the blank-bill baseline already subtracted is measured under a stimulus no real bill
    resembles. The median across the corpus removes what is left. It is computed from the
    fly's own outputs and never sees a vote.
    """
    turns = np.array([b["turn"] for b in ballots])
    centre = float(np.median(turns))
    centred = turns - centre
    band = float(np.quantile(np.abs(centred), ABSTAIN_TARGET))
    for b, v in zip(ballots, centred, strict=True):
        supports = None if abs(v) <= band else bool(v > 0)
        b["turn"] = round(float(v), 5)
        b["code"] = (
            EI_HAALETANUD
            if supports is None
            else (POOLT if supports != inverted.get(b["voting_uuid"], False) else VASTU)
        )
    return centre, band


def convergence(
    ballots: list[dict],
    vm: votematrix.VoteMatrix,
    space: idealpoint.Space,
    inverted: dict[str, bool],
    checkpoints: int = CHECKPOINTS,
) -> list[dict]:
    """The fly's position on dimension 1 after each slice of its record.

    This is the thing SPEC asked to be watchable: "the position converging out of nothing".
    """
    order = sorted(ballots, key=lambda b: b["when"])
    step = max(1, len(order) // checkpoints)
    out = []
    for n in range(step, len(order) + step, step):
        chunk = order[: min(n, len(order))]
        try:
            s = seat.place(chunk, vm, space, inverted)
        except (ValueError, np.linalg.LinAlgError) as exc:
            # a record this short cannot be placed in the space yet
            log.debug("skipping checkpoint at %d: %s", n, exc)
            continue
        if s.dim1 is None:
            continue
        out.append(
            {
                "votes": len(chunk),
                "dim1": s.dim1,
                "agreement": {SHORT.get(k, k): v for k, v in s.faction_agreement.items()},
            }
        )
    return out


def bundle(
    arms: dict[str, list[dict]],
    vm: votematrix.VoteMatrix,
    space: idealpoint.Space,
    inverted: dict[str, bool],
    bills: dict,
    rewired: dict[str, list[dict]] | None = None,
) -> dict:
    """Everything the season page needs."""
    from karbes.season import auc

    latest = vm.latest_faction()
    chamber = [
        {
            "dim1": round(float(c[0]), 3),
            "faction": SHORT.get(latest.get(m, ""), "none"),
            "name": n,
        }
        for m, c, n in zip(space.member_ids, space.coords, space.names, strict=True)
    ]

    def score_arm(ballots: list[dict]) -> dict:
        centre, band = recode(ballots, inverted)
        s = seat.place(ballots, vm, space, inverted)
        turns = np.array([b["turn"] for b in ballots])
        adv = np.array([b["advances"] for b in ballots])
        a = auc(turns, adv)
        return {
            "auc_advances": round(float(max(a, 1 - a)), 4),
            "centre": round(centre, 5),
            "dead_band": round(band, 5),
            "votes": s.votes,
            "decided": s.decided,
            "marginal_poolt": s.marginal_poolt,
            "dim1": s.dim1,
            "agreement": {SHORT.get(k, k): v for k, v in s.faction_agreement.items()},
            "auc": {SHORT.get(k, k): v for k, v in s.faction_auc.items()},
            "nearest": [
                {"name": m["name"], "faction": SHORT.get(m["faction"], "none"), "dim1": m["dim1"]}
                for m in s.nearest_members
            ],
        }

    out = {
        "schema": "karbes-season/1",
        "chamber": {
            "members": chamber,
            "seats": len(chamber),
            "explained_dim1": round(float(space.explained[0]), 4),
            "colours": COLOUR,
        },
        "arms": {name: score_arm(list(b)) for name, b in arms.items()},
        "timeline": [],
        "convergence": {},
    }
    for name, ballots in arms.items():
        out["convergence"][name] = convergence(ballots, vm, space, inverted)

    lead = arms.get("informed") or next(iter(arms.values()))
    for b in sorted(lead, key=lambda x: x["when"]):
        bill = bills.get(b["bill_uuid"])
        out["timeline"].append(
            {
                "title": (bill.title if bill else "")[:90],
                "when": b["when"][:10],
                "government": b["government"],
                "code": b["code"],
                "turn": b["turn"],
                "advances": b["advances"],
            }
        )

    if rewired:
        out["rewired"] = {}
        for name, ballots in rewired.items():
            out["rewired"][name] = score_arm(list(ballots))
    return out
