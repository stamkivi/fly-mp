"""Ideal-point scaling: recover the chamber's political space from votes alone.

This is the project's primary artifact, and it is deliberately label-agnostic. Stage 0
showed that faction labels are unreliable exactly where the term is most interesting —
Reform and Eesti 200 differ on 2 votes of 563, SDE changes side mid-term, and 22 MPs sit
as formally non-affiliated while voting with a bloc. A scaling ignores all of that and
recovers position from behaviour, so factions become an overlay rather than the unit.

Kärbes enters as row 102 via `project`, which places a new voter in the *existing* space
without letting it move the axes. A fly that shifted the political space by being added to
it would tell us nothing about where it sits in the real one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from karbes.analysis.votematrix import VoteMatrix

log = logging.getLogger(__name__)

MIN_VOTES_PER_MEMBER = 20


@dataclass
class Space:
    """A fitted political space: member coordinates plus the vote geometry that made it."""

    coords: np.ndarray  # (members, dims)
    member_ids: list[str]
    names: list[str]
    vote_loadings: np.ndarray  # (votes, dims) — how each vote discriminates
    vote_means: np.ndarray  # (votes,) — column centring, needed to project
    explained: np.ndarray  # variance share per dimension
    dims: int

    def coord_of(self, member_id: str) -> np.ndarray:
        return self.coords[self.member_ids.index(member_id)]

    def project(self, stance: np.ndarray) -> np.ndarray:
        """Place a new voter in the existing space from their stance vector.

        `stance` is length n_votes with +1/-1/0 and nan for "no vote". The axes are held
        fixed: a new member is located in the chamber's space, not allowed to redefine it.
        """
        if stance.shape[0] != self.vote_loadings.shape[0]:
            raise ValueError(
                f"stance has {stance.shape[0]} votes, space has {self.vote_loadings.shape[0]}"
            )
        observed = ~np.isnan(stance)
        if observed.sum() < MIN_VOTES_PER_MEMBER:
            raise ValueError(f"only {observed.sum()} votes; need {MIN_VOTES_PER_MEMBER}")
        y = stance[observed] - self.vote_means[observed]
        loadings = self.vote_loadings[observed]
        # Least squares onto the fixed axes, so partial voting records still place.
        coef, *_ = np.linalg.lstsq(loadings, y, rcond=None)
        return coef


def fit(vm: VoteMatrix, dims: int = 2, iters: int = 30) -> Space:
    """Fit by SVD on the centred stance matrix, imputing absences iteratively.

    Absence is missing data, not a position, so it cannot be read as 0. Iterative
    imputation lets the current fit fill the gaps rather than a constant that would pull
    every frequently-absent member toward the centre.
    """
    x = vm.stance.astype(float)
    missing = np.isnan(x)
    keep = (~missing).sum(axis=1) >= MIN_VOTES_PER_MEMBER
    if keep.sum() < dims + 1:
        raise ValueError("too few members with enough votes")

    x = x[keep]
    missing = missing[keep]
    member_ids = [m for m, k in zip(vm.member_ids, keep, strict=True) if k]
    names = [n for n, k in zip(vm.names, keep, strict=True) if k]

    filled = np.where(missing, 0.0, x)
    col_mean = np.zeros(x.shape[1])
    u = s = vt = None
    for _ in range(iters):
        col_mean = filled.mean(axis=0)
        centred = filled - col_mean
        u, s, vt = np.linalg.svd(centred, full_matrices=False)
        approx = (u[:, :dims] * s[:dims]) @ vt[:dims] + col_mean
        new = np.where(missing, approx, x)
        if np.allclose(new, filled, atol=1e-6):
            filled = new
            break
        filled = new

    assert u is not None and s is not None and vt is not None
    var = s**2
    explained = var / var.sum() if var.sum() else var

    coords = u[:, :dims] * s[:dims]
    loadings = vt[:dims].T  # (votes, dims), orthonormal so projection is well posed

    # Orient dimension 1 so that higher = more supportive of bills that passed, which
    # makes the axis readable rather than arbitrary in sign.
    passed = np.array([1.0 if v.in_favor > v.against else -1.0 for v in vm.votes], dtype=float)
    if float(np.dot(loadings[:, 0], passed)) < 0:
        loadings[:, 0] *= -1
        coords[:, 0] *= -1

    return Space(
        coords=coords,
        member_ids=member_ids,
        names=names,
        vote_loadings=loadings,
        vote_means=col_mean,
        explained=explained[:dims],
        dims=dims,
    )


def classification_accuracy(space: Space, vm: VoteMatrix) -> float:
    """Share of observed votes the fitted space predicts correctly.

    The standard sanity check for a spatial model: a space that cannot reproduce the votes
    it was fitted on is not describing the chamber.
    """
    recon = space.coords @ space.vote_loadings.T + space.vote_means
    idx = [vm.member_ids.index(m) for m in space.member_ids]
    truth = vm.stance[idx]
    observed = ~np.isnan(truth) & (truth != 0.0)
    if not observed.any():
        return float("nan")
    return float((np.sign(recon[observed]) == np.sign(truth[observed])).mean())


def bloc_separation(space: Space, vm: VoteMatrix) -> dict:
    """Where each faction sits on dimension 1, and whether blocs actually separate."""
    latest = vm.latest_faction()
    groups: dict[str, list[float]] = {}
    for mid, coord in zip(space.member_ids, space.coords, strict=True):
        groups.setdefault(latest.get(mid, "?"), []).append(float(coord[0]))
    out = {
        f: {
            "n": len(v),
            "median": round(float(np.median(v)), 3),
            "iqr": [round(float(np.percentile(v, 25)), 3), round(float(np.percentile(v, 75)), 3)],
        }
        for f, v in sorted(groups.items(), key=lambda kv: np.median(kv[1]))
    }
    return out


def bootstrap_coord(
    vm: VoteMatrix, member_id: str, draws: int = 200, dims: int = 2, seed: int = 0
) -> dict:
    """Cluster-bootstrap a member's position by resampling *bills*, not votes.

    Votes on the same bill are not independent — 90 bills carry both a contested rejection
    motion and a contested final vote — so resampling votes would understate the interval.
    """
    rng = np.random.default_rng(seed)
    bills = sorted({v.draft_uuid for v in vm.votes})
    by_bill: dict[str, list[int]] = {}
    for j, v in enumerate(vm.votes):
        by_bill.setdefault(v.draft_uuid, []).append(j)

    draws_out = []
    for _ in range(draws):
        chosen = rng.choice(len(bills), size=len(bills), replace=True)
        cols = [j for b in chosen for j in by_bill[bills[b]]]
        mask = np.zeros(len(vm.votes), dtype=bool)
        mask[np.unique(cols)] = True
        try:
            sp = fit(vm.subset(mask), dims=dims, iters=8)
            draws_out.append(sp.coord_of(member_id)[0])
        except (ValueError, np.linalg.LinAlgError):
            continue
    if not draws_out:
        return {"error": "no successful draws"}
    arr = np.array(draws_out)
    return {
        "draws": len(arr),
        "median": round(float(np.median(arr)), 3),
        "ci95": [
            round(float(np.percentile(arr, 2.5)), 3),
            round(float(np.percentile(arr, 97.5)), 3),
        ],
    }
