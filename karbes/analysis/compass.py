"""Place a voting record on the Estonian political compass, not on an arbitrary axis.

`idealpoint` recovers the chamber's own space from votes alone, which is the right primary
artifact but an unreadable one: dimension 1 is signed and scaled by an SVD, so "+3.6" means
nothing to a reader and cannot be compared across runs. The compass fixes that by anchoring
the latent space to coordinates somebody else published, on axes that already have names.

The anchors are the Chapel Hill Expert Survey 2024 wave, Estonia, election year 2023 — the
chamber this corpus covers. CHES asks political scientists to place each party on economic
left-right (`lrecon`) and GAL-TAN (`galtan`), both 0-10. Two properties matter here:

* **The anchors are external.** Nothing in this repository decides where Reform sits. The
  map from votes to compass is fitted on the 101 humans and their parties' published
  coordinates, and the fly never participates in fitting it.
* **The map is frozen before any fly is projected.** SPEC §4 requires that every control arm
  receive an identical fitting procedure; here they receive an identical *fitted map*, which
  is stronger. A rewired fly cannot move its own axes any more than Kärbes can.

Honest error is reported by leave-one-party-out cross-validation: hold out a whole party,
refit on the rest, and measure how far the held-out members land from where CHES put them.
Holding out single members would be self-flattering, because their party-mates carry the
answer.

**The two axes are not equally well measured, and the asymmetry is the finding.** The
chamber's dominant voting dimension — 61% of the variance, and in this parliament the
government/opposition split — correlates r = +0.92 with GAL-TAN and only -0.41 with the
economic axis. Held out, GAL-TAN comes back to 0.80 on a 7.4-wide range of party positions;
economic left-right to 1.74 on a range of 4.1. Roll-call votes in the XV Riigikogu carry
cultural position sharply and economic position barely, so any picture drawn from them has
a sharp vertical and a soft horizontal. Saying so is part of the result.

Rovny et al. (2025), *25 Years of Political Party Positions in Europe: The Chapel Hill
Expert Survey, 1999-2024*. Values below are `country == 22`, wave 2024.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from karbes.analysis import idealpoint, votematrix

log = logging.getLogger(__name__)

#: CHES 2024, Estonia, election year 2023: (economic left-right, GAL-TAN), both 0-10.
#: Keyed by Riigikogu faction name so the join needs no fuzzy matching.
CHES_2024 = {
    "Eesti Reformierakonna fraktsioon": (7.3684211, 2.4736843),
    "Eesti Keskerakonna fraktsioon": (3.6666667, 5.6111112),
    "Eesti Konservatiivse Rahvaerakonna fraktsioon": (5.8421054, 9.2631578),
    "Sotsiaaldemokraatliku Erakonna fraktsioon": (3.2631578, 1.8421053),
    "Isamaa fraktsioon": (7.0, 7.5789475),
    "Eesti 200 fraktsioon": (7.1052632, 2.0),
}

AXES = ("economic left → right", "liberal → conservative")

#: Latent dimensions carried into the map. Four is comfortably more than the chamber's
#: government/opposition split needs and still leaves 97 members per fitted coefficient.
DIMS = 4

#: Ridge penalty on the latent coordinates. Fixed rather than tuned, because tuning it
#: against the held-out error would quietly turn cross-validation into fitting.
RIDGE = 1e-3


@dataclass
class Map:
    """A frozen linear map from the chamber's latent space to the compass."""

    space: idealpoint.Space
    coef: np.ndarray  # (dims + 1, 2), last row is the intercept
    members: list[dict]  # every anchored human, with their fitted and published position
    loo_error: float  # mean distance, compass units, leave-one-party-out
    spread: float  # mean distance between anchored parties, for scale
    axis_error: tuple[float, float]  # held-out error per axis
    axis_range: tuple[float, float]  # spread of the anchors on each axis, for scale

    def project(self, stance: np.ndarray) -> tuple[float, float]:
        """Place a voting record. `stance` is the +1/-1/0/nan vector over the same votes."""
        latent = self.space.project(stance)
        x = np.append(latent[:DIMS], 1.0)
        out = x @ self.coef
        return float(out[0]), float(out[1])


def _design(coords: np.ndarray) -> np.ndarray:
    return np.hstack([coords[:, :DIMS], np.ones((len(coords), 1))])


def _solve(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    penalty = RIDGE * np.eye(x.shape[1])
    penalty[-1, -1] = 0.0  # never penalise the intercept
    return np.linalg.solve(x.T @ x + penalty, x.T @ y)


def fit(vm: votematrix.VoteMatrix, space: idealpoint.Space | None = None) -> Map:
    """Fit the votes-to-compass map on the humans, and report its held-out error."""
    space = space or idealpoint.fit(vm, dims=DIMS)
    if space.dims < DIMS:
        raise ValueError(f"space has {space.dims} dims, the map needs {DIMS}")

    latest = vm.latest_faction()
    rows, targets, keep = [], [], []
    for i, mid in enumerate(space.member_ids):
        faction = latest.get(mid, "")
        anchor = CHES_2024.get(faction)
        if anchor is None:
            continue  # crossbenchers have no published party position, so they cannot anchor
        rows.append(space.coords[i])
        targets.append(anchor)
        keep.append((mid, space.names[i], faction))

    if len(rows) < DIMS + 2:
        raise ValueError(f"only {len(rows)} anchored members")

    coords = np.array(rows)
    y = np.array(targets)
    x = _design(coords)
    coef = _solve(x, y)

    # Leave one *party* out: the held-out members get no help from their own bloc.
    errors, per_axis = [], []
    parties = sorted({f for _, _, f in keep})
    for party in parties:
        out = np.array([f == party for _, _, f in keep])
        if out.all() or (~out).sum() < DIMS + 2:
            continue
        held = _solve(x[~out], y[~out])
        pred = x[out] @ held
        errors.append(np.linalg.norm(pred - y[out], axis=1))
        per_axis.append(np.abs(pred - y[out]))
    loo = float(np.concatenate(errors).mean()) if errors else float("nan")
    axis = np.concatenate(per_axis).mean(axis=0) if per_axis else np.array([np.nan, np.nan])

    anchors = np.array(sorted(CHES_2024.values()))
    pair = [
        float(np.linalg.norm(anchors[i] - anchors[j]))
        for i in range(len(anchors))
        for j in range(i + 1, len(anchors))
    ]

    fitted = x @ coef
    members = [
        {
            "member_id": mid,
            "name": name,
            "faction": faction,
            "x": round(float(fitted[i, 0]), 3),
            "y": round(float(fitted[i, 1]), 3),
            "party_x": CHES_2024[faction][0],
            "party_y": CHES_2024[faction][1],
        }
        for i, (mid, name, faction) in enumerate(keep)
    ]

    axis_range = (float(np.ptp(y[:, 0])), float(np.ptp(y[:, 1])))
    log.info(
        "compass: %d anchored members; held out a whole party, error %.2f overall, "
        "%.2f on economic (range %.1f) and %.2f on GAL-TAN (range %.1f)",
        len(members),
        loo,
        axis[0],
        axis_range[0],
        axis[1],
        axis_range[1],
    )
    return Map(
        space=space,
        coef=coef,
        members=members,
        loo_error=round(loo, 3),
        spread=round(float(np.mean(pair)), 3),
        axis_error=(round(float(axis[0]), 3), round(float(axis[1]), 3)),
        axis_range=(round(axis_range[0], 3), round(axis_range[1], 3)),
    )
