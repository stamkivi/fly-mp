"""Twenty flies from one connectome: the same brain, rewired, voting the same season.

SPEC calls the rewired-graph arm "not validation, it is the experiment", and this is the
form the experiment finally takes. Earlier the shuffle was run three times and read as a
control on *accuracy* — it beat the real connectome on AUC, which retired the idea that the
wiring makes the fly a better predictor of the chamber. What it did not retire is the more
interesting reading: the three shuffles landed in three different places. Wiring does not
decide whether the fly is right. It decides **who the fly is**.

So: one degree-preserving shuffle per seed, each a different brain with identical statistics
— same in-degree, out-degree, sign and total output per neuron, only the addressees changed
— each given the identical corpus, the identical encoder, the identical calibration and the
identical decoder. Whatever separates them is the connectivity and nothing else.

Packs are 190 MB each, so a pack is built, run, and deleted. The record is what we keep.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from dataclasses import asdict
from pathlib import Path

log = logging.getLogger(__name__)

#: Where `lif` keeps compiled packs. The shuffler writes its output beside the source.
PACKS = Path.home() / "git" / "drosophila-brain-mlx" / "data" / "pack"
SOURCE = "male_cns_v1"
OUT = Path("runs/chorus")


def pack_path(seed: int) -> Path:
    return PACKS / f"{SOURCE}-shuffled-seed{seed}"


def ensure_pack(seed: int) -> Path:
    """Build the degree-preserving shuffle for `seed` unless it is already on disk."""
    path = pack_path(seed)
    if (path / "manifest.json").exists():
        return path
    from lif.shuffle_pack import write_shuffled_pack

    t0 = time.time()
    manifest = write_shuffled_pack(PACKS / SOURCE, path, seed)
    s = manifest["shuffle"]
    log.info(
        "shuffled seed %d in %.0fs: %s edges land where they already were, %s self-loops, "
        "%s repair rounds",
        seed,
        time.time() - t0,
        f"{s['edges_kept']:,}",
        f"{s['self_loops']:,}",
        s["repair_rounds"],
    )
    return path


def record(name: str) -> Path:
    return OUT / f"{name}.json"


def run_one(name: str, pack: Path | None, pops, bills, votes, scores, cal, *, seed: int = 0):
    """One fly's full season. Returns the ballots; writes them before returning."""
    from karbes import engine as E
    from karbes import season

    existing = record(name)
    if existing.exists():
        log.info("%s already voted, keeping the record", name)
        return json.loads(existing.read_text(encoding="utf-8"))

    engine = E.load(pack)
    ballots = season.run(
        engine,
        pops,
        bills,
        votes,
        scores,
        bias=cal["baseline_bias"],
        dead_band=cal["dead_band"],
        sees_initiator=True,
        seed=seed,
        label=name,
    )
    rows = [asdict(b) if hasattr(b, "__dataclass_fields__") else b.__dict__ for b in ballots]
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = existing.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows), encoding="utf-8")
    tmp.replace(existing)
    return rows


def drop_pack(seed: int) -> None:
    """A pack is 190 MB and reproducible from its seed; the record is not."""
    path = pack_path(seed)
    if path.exists() and (path / "manifest.json").exists():
        shutil.rmtree(path)


# ---------------------------------------------------------------- placing the chorus


def stance(ballots: list[dict], vm, inverted: dict[str, bool]):
    """A record as the same +1/-1/0/nan stance vector the 101 humans are encoded in."""
    import numpy as np

    from karbes.analysis.seat import _stance

    column = {v.uuid: j for j, v in enumerate(vm.votes)}
    out = np.full(len(vm.votes), np.nan)
    for b in ballots:
        j = column.get(b["voting_uuid"])
        if j is not None:
            out[j] = _stance(b["code"], inverted.get(b["voting_uuid"], False))
    return out


BASELINE = Path("runs/baseline.json")
RELIABILITY = Path("runs/reliability_informed.json")

#: The one shuffled pack that is itself re-run under new input noise, so its reruns can be
#: grouped with it.
_BASE_RERUN = "rewired0"
_RERUN = re.compile(r"^rewired\d+-phase\d+$")


def _kind(name: str) -> str:
    if name.startswith("karbes"):
        return "real"
    if _RERUN.match(name):
        return "rewired_rerun"
    return "rewired"


def _split(
    records: dict[str, list[dict]], a: str, b: str, bills, scores, limit: int = 3
) -> list[dict]:
    """Bills where two brains voted opposite ways, most confidently first.

    The scatter plot is an abstraction and reads as one. A named bill on which the real
    connectome said yes and a shuffle of it said no is the same fact at human scale, and it
    costs nothing but a join.

    Titles stay in Estonian because that is the bill's actual name and the cache keeps source
    text verbatim; the English line beside each is the channel the scorer read most strongly,
    which is what the fly actually smelled.
    """
    from karbes.score.rubric3 import LABELS

    left = {r["bill_uuid"]: r for r in records.get(a, [])}
    right = {r["bill_uuid"]: r for r in records.get(b, [])}
    rows = []
    for uuid, l in left.items():
        r = right.get(uuid)
        if r is None or l["code"] == r["code"]:
            continue
        if {l["code"], r["code"]} - {"POOLT", "VASTU"}:
            continue  # a decline is not a disagreement, it is a shrug
        bill = bills.get(uuid) if bills else None
        sc = (scores or {}).get(uuid)
        channel = ""
        if sc is not None:
            k, v = max(
                ((k, v) for k, v in sc.scores.items() if k != "salience"),
                key=lambda kv: abs(kv[1]),
                default=("", 0.0),
            )
            if k:
                channel = f"{'raises' if v > 0 else 'lowers'} {LABELS.get(k, k)}"
        rows.append(
            {
                "title": (getattr(bill, "title", "") or "")[:110],
                "channel": channel,
                "when": l["when"][:10],
                "government": l["government"],
                "a": l["code"],
                "b": r["code"],
                "confidence": round(float(abs(l["turn"]) + abs(r["turn"])), 5),
            }
        )
    rows.sort(key=lambda x: -x["confidence"])
    return [r for r in rows if r["title"]][:limit] or rows[:limit]


def place_all(
    vm, space, cmap, inverted: dict[str, bool], bills=None, scores=None, root: Path = OUT
) -> dict:
    """Read every record in `root`, recode it, and put it on the compass.

    The real fly's extra phases are the within-brain yardstick: whatever distance separates
    two runs of the *same* wiring is the distance below which a difference between two
    wirings means nothing.
    """
    import numpy as np

    from karbes.analysis.compass import AXES, CHES_2024
    from karbes.season import auc
    from karbes.seasonpage import SHORT, recode

    flies = []
    records: dict[str, list[dict]] = {}
    for path in sorted(root.glob("*.json")):
        name = path.stem
        ballots = json.loads(path.read_text(encoding="utf-8"))
        recode(ballots, inverted)  # rewrites turn and code in place; see seasonpage.recode
        records[name] = ballots
        x, y = cmap.project(stance(ballots, vm, inverted))
        turns = np.array([b["turn"] for b in ballots])
        adv = np.array([b["advances"] for b in ballots])
        a = float(auc(turns, adv))
        codes = [b["code"] for b in ballots]
        near = min(cmap.members, key=lambda m: (m["party_x"] - x) ** 2 + (m["party_y"] - y) ** 2)
        flies.append(
            {
                "name": name,
                # Three kinds, and conflating any two of them corrupts a spread. A rerun of a
                # *shuffle* is the same wiring twice, so counting it as another rewiring would
                # drag the across-wiring spread down by exactly the quantity being tested.
                "kind": _kind(name),
                "phase": "-phase" in name,
                "x": round(x, 3),
                "y": round(y, 3),
                "votes": len(ballots),
                "auc_advances": round(max(a, 1 - a), 4),
                "poolt": round(float(np.mean([c == "POOLT" for c in codes])), 3),
                "nearest_party": SHORT.get(near["faction"], near["faction"]),
            }
        )

    def spread(points: list[tuple[float, float]]) -> float:
        if len(points) < 2:
            return float("nan")
        p = np.array(points)
        d = [
            float(np.linalg.norm(p[i] - p[j])) for i in range(len(p)) for j in range(i + 1, len(p))
        ]
        return float(np.mean(d))

    real_pts = [(f["x"], f["y"]) for f in flies if f["kind"] == "real"]
    rewired_pts = [(f["x"], f["y"]) for f in flies if f["kind"] == "rewired"]
    # One shuffled brain, re-run: is a rewiring an individual, or a fresh draw each time?
    shuffle_rerun = [
        (f["x"], f["y"]) for f in flies if f["kind"] == "rewired_rerun" or f["name"] == _BASE_RERUN
    ]
    # The same brain's AUC wanders far more than its seat does. Worth stating, because AUC is
    # the statistic the accuracy framing rests on and it turns out to be the unstable one.
    real_aucs = [f["auc_advances"] for f in flies if f["kind"] == "real"]
    auc_range = (
        [round(min(real_aucs), 3), round(max(real_aucs), 3)] if len(real_aucs) > 1 else None
    )
    within = spread(real_pts)
    across = spread(rewired_pts)
    p_value = _permutation(real_pts, rewired_pts)
    parties = {SHORT.get(k, k): {"x": v[0], "y": v[1]} for k, v in CHES_2024.items()}

    karbes = next((f for f in flies if f["name"] == "karbes"), None)

    # Why the real connectome scores badly, rather than an apology for it. AUC here is
    # direction-free by construction (max(a, 1-a)), so it rewards tracking the chamber's
    # dominant axis in *either* direction. A fly that lands at a pole has picked a side and
    # predicts well; one that lands between them predicts nothing. Being a good predictor of
    # this parliament means being a partisan in it.
    partisanship = None
    if len(rewired_pts) >= 5:
        midline = float(np.median([v[1] for v in CHES_2024.values()]))
        far = np.array([abs(f["y"] - midline) for f in flies if f["kind"] == "rewired"])
        aucs = np.array([f["auc_advances"] for f in flies if f["kind"] == "rewired"])
        partisanship = {
            "midline": round(midline, 3),
            "r": round(float(np.corrcoef(far, aucs)[0, 1]), 3),
            "karbes_from_midline": round(abs(karbes["y"] - midline), 3) if karbes else None,
        }

    # Is the measured connectome distinguished among its own shuffles, or is it one of them?
    # The page should not imply the former when the data says the latter.
    typicality = None
    if karbes and len(rewired_pts) >= 3:
        pts = np.asarray(rewired_pts, float)
        centre = pts.mean(axis=0)
        theirs = np.linalg.norm(pts - centre, axis=1)
        mine = float(np.linalg.norm(np.array([karbes["x"], karbes["y"]]) - centre))
        typicality = {
            "karbes_from_centre": round(mine, 3),
            "shuffles_from_centre": round(float(theirs.mean()), 3),
            "percentile": round(float((theirs < mine).mean()), 3),
        }
    furthest, split = None, []
    if karbes and rewired_pts:
        cand = [f for f in flies if f["kind"] == "rewired"]
        furthest = max(
            cand, key=lambda f: (f["x"] - karbes["x"]) ** 2 + (f["y"] - karbes["y"]) ** 2
        )
        split = _split(records, "karbes", furthest["name"], bills, scores)
    log.info(
        "chorus: %d flies, within-brain spread %.2f, across-wiring spread %.2f "
        "(permutation p = %s), party spacing %.2f",
        len(flies),
        within,
        across,
        p_value,
        cmap.spread,
    )
    return {
        "schema": "karbes-chorus/1",
        "axes": list(AXES),
        "parties": parties,
        "members": cmap.members,
        "loo_error": cmap.loo_error,
        "axis_error": list(cmap.axis_error),
        "axis_range": list(cmap.axis_range),
        "party_spacing": cmap.spread,
        "flies": flies,
        "furthest": furthest["name"] if furthest else None,
        "typicality": typicality,
        "partisanship": partisanship,
        "split": split,
        # JSON has no NaN, and a page that reads NaN as a number prints one. A spread that
        # could not be measured is absent, not zero.
        "permutation_p": p_value,
        "real_auc_range": auc_range,
        "within_brain_spread": None if np.isnan(within) else round(within, 3),
        "within_shuffle_spread": (
            None if np.isnan(spread(shuffle_rerun)) else round(spread(shuffle_rerun), 3)
        ),
        "across_wiring_spread": None if np.isnan(across) else round(across, 3),
        # What a regression gets from the same inputs. The fly is never fitted to the
        # outcome and these are, so the comparison flatters them — which is the point.
        "baseline": json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None,
        "per_bill": _per_bill(),
    }


def _permutation(real, rewired, draws: int = 20000, seed: int = 0):
    """Could the same-brain reruns be this tight by chance, if wiring made no difference?

    Under the null every fly is drawn from one scatter, so which few of them are labelled
    "the same brain, re-run" is arbitrary. Relabel at random and recompute the ratio of mean
    pairwise distances. Comparing two means alone leaves that question open, and with three
    points in the denominator it is a real question.
    """
    import numpy as np

    a, b = np.asarray(real, float), np.asarray(rewired, float)
    if len(a) < 2 or len(b) < 2:
        return None

    def mean_pair(pts):
        return float(
            np.mean(
                [
                    np.linalg.norm(pts[i] - pts[j])
                    for i in range(len(pts))
                    for j in range(i + 1, len(pts))
                ]
            )
        )

    def ratio(pts, idx):
        inside = pts[idx]
        outside = pts[np.setdiff1d(np.arange(len(pts)), idx)]
        tight = mean_pair(inside)
        return mean_pair(outside) / tight if tight > 0 else np.inf

    allpts = np.vstack([a, b])
    observed = ratio(allpts, np.arange(len(a)))
    rng = np.random.default_rng(seed)
    hits = sum(
        ratio(allpts, rng.choice(len(allpts), size=len(a), replace=False)) >= observed
        for _ in range(draws)
    )
    return round((hits + 1) / (draws + 1), 4)


def _per_bill() -> dict | None:
    """How reproducible one *vote* is, against how reproducible the whole record is.

    The two numbers only mean something together. A record that reproduces to a quarter of a
    compass unit while its individual votes land on the same side barely more often than a
    coin is the interesting shape, and quoting either one alone hides it.
    """
    import numpy as np

    if not RELIABILITY.exists():
        return None
    m = np.array(json.loads(RELIABILITY.read_text(encoding="utf-8"))["turns"])
    centred = m - np.median(m, axis=1, keepdims=True)  # the vote is the centred sign
    rs, agree = [], []
    for i in range(len(centred)):
        for j in range(i + 1, len(centred)):
            rs.append(float(np.corrcoef(centred[i], centred[j])[0, 1]))
            agree.append(float(np.mean(np.sign(centred[i]) == np.sign(centred[j]))))
    return {
        "bills": int(m.shape[1]),
        "runs": int(m.shape[0]),
        "r": round(float(np.mean(rs)), 3),
        "same_side": round(float(np.mean(agree)), 3),
    }
