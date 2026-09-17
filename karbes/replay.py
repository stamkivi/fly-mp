"""Replay bundles: one bill, simulated once, frozen as data the page plays back.

No LLM call and no simulation at view time — the page has to survive being public, so
everything is generated offline and shipped as bytes.

A bundle is a JSON file plus one binary blob. The blob is the spike raster, which is the
only part big enough to care about: `uint32` frame offsets followed by `uint16` atlas
slots, sorted by frame. Two bytes per spike and directly indexable, rather than three
bytes per `(slot, frame)` pair that the page would have to bucket at load time.

**Bill selection is outcome-blind and pre-registered.** `pick_bill` takes the
highest-salience bill that has a discriminative substantive vote and a Jev score, ties
broken by date. Salience is a property of the bill; nothing in the rule can see whether
the fly agreed with anyone.
"""

from __future__ import annotations

import json
import logging
import os
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from karbes import decode, encode
from karbes import engine as E
from karbes.analysis import idealpoint, votematrix
from karbes.atlas import Atlas
from karbes.graph.populations import CHANNEL_ORNS, Populations
from karbes.riigikogu.model import Bill, Vote
from karbes.score import rubric2
from karbes.score.jev import Scored

log = logging.getLogger(__name__)

SCHEMA = "karbes-replay/1"
FRAMES = 100
RASTER_MAGIC = b"KRB1"


@dataclass
class Bundle:
    """One bill's replay: the JSON document and the raster blob it points at."""

    doc: dict
    raster: bytes
    name: str

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        blob = out_dir / f"{self.name}.raster.bin"
        doc = out_dir / f"{self.name}.json"
        _atomic(blob, self.raster)
        _atomic(doc, json.dumps(self.doc, ensure_ascii=False, indent=1).encode("utf-8"))
        return doc, blob


def _atomic(path: Path, payload: bytes) -> None:
    """Cache and artifact writes are atomic: a truncated file parses as valid-but-wrong."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def pack_raster(frames: list[np.ndarray]) -> bytes:
    """`KRB1` | frames u32 | offsets u32[frames+1] | slots u16[total], sorted by frame."""
    offsets, total = [0], 0
    for f in frames:
        total += len(f)
        offsets.append(total)
    slots = np.concatenate(frames) if frames else np.empty(0, dtype=np.uint16)
    return (
        RASTER_MAGIC
        + struct.pack("<I", len(frames))
        + np.asarray(offsets, dtype="<u4").tobytes()
        + slots.astype("<u2").tobytes()
    )


def pick_bill(
    bills: dict[str, Bill], votes: list[Vote], scores: dict[str, Scored]
) -> tuple[Bill, Vote]:
    """The most consequential bill the fly can actually smell. Never an agreement rule."""
    candidates = []
    for vote in votes:
        bill = bills.get(vote.draft_uuid)
        scored = scores.get(vote.draft_uuid)
        if bill is None or scored is None or not vote.discriminative:
            continue
        candidates.append((scored.scores.get("salience", 0.0), vote.when, bill, vote))
    if not candidates:
        raise ValueError("no scored, discriminative bill in the corpus")
    salience, _, bill, vote = max(candidates, key=lambda c: (c[0], -_epoch(c[1])))
    log.info("selected %r (salience %.2f) of %d candidates", bill.title, salience, len(candidates))
    return bill, vote


def _epoch(when: str) -> float:
    return datetime.fromisoformat(when).timestamp()


def blank_score() -> Scored:
    """A bill that says nothing: every channel zero, at full confidence.

    Salience is zero too, which is right for a baseline — a blank bill changes nothing —
    but wrong for a sweep. `salience_gain` floors at 0.25, so probing a channel on top of
    this delivers a quarter of the drive it should and the measurement lands under the
    noise. Use `probe_score` for that.
    """
    keys = (*rubric2.KEYS, "salience")
    return Scored(
        scores=dict.fromkeys(keys, 0.0),
        confidence=dict.fromkeys(keys, 1.0),
        input_tokens=0,
    )


def probe_score(**channels: float) -> Scored:
    """A synthetic bill at full salience, for measuring what a channel can actually do.

    Salience at 1.0 rather than 0.0: the sweep asks how far a channel moves the fly at its
    strongest, and a quarter-strength probe answers a different question. Getting this
    wrong once already produced a full-scale contrast of the wrong sign.
    """
    scored = blank_score()
    scored.scores["salience"] = 1.0
    for channel, value in channels.items():
        scored.scores[channel] = value
    return scored


def baseline(
    engine: E.Engine, pops: Populations, seeds: int = 12, duration: float = E.DURATION
) -> dict:
    """The turn index on a bill that says nothing: the bias, and the spread around it.

    **Both are required and neither is optional.** A blank bill drives both antennae
    equally, so the turn index it produces is pure anatomy — the left/right asymmetry of
    the wiring plus the 363/525 rootSide imbalance in how many receptor neurons each side
    has. flybrain measured that bias at up to -1.3 against a directional signal of ~0.08
    and had to subtract it; here it is about -0.08 against an effect of ~0.38.

    The spread across input phases sets the dead band. It is measured on the network
    alone and never looks at the chamber, so it cannot be tuned to make the voting record
    agree with anybody.
    """
    dna_l, dna_r = engine.positions(pops.dna_left), engine.positions(pops.dna_right)
    targets, rates = encode.stimulus(blank_score(), pops, engine)
    turns, spikes = [], []
    for seed in range(seeds):
        run = E.run(engine, targets, rates, seed=seed, duration=duration)
        turns.append(decode.turn_index(run.counts, dna_l, dna_r).raw)
        spikes.append(int(run.counts.sum()))
    arr = np.array(turns, dtype=float)
    return {
        "seeds": seeds,
        "stimulus": "blank bill: every channel zero, both antennae driven equally",
        "bias": round(float(arr.mean()), 5),
        "sd": round(float(arr.std(ddof=1)), 5) if seeds > 1 else 0.0,
        "se": round(float(arr.std(ddof=1) / np.sqrt(seeds)), 5) if seeds > 1 else 0.0,
        "mean_network_hz": round(float(np.mean(spikes)) / (engine.n * duration), 4),
        "turns": [round(float(t), 5) for t in arr],
    }


def sweep(
    engine: E.Engine, pops: Populations, seeds: int = 12, duration: float = E.DURATION
) -> dict:
    """Each channel driven fully right and fully left in turn, everything else at zero.

    SPEC's Stage 2 verification. Every point is averaged over `seeds` input phases and
    reports its standard error: run-to-run spread is real here, and a span quoted without
    an error bar is what produced the retracted Stage 2b numbers.
    """
    dna_l, dna_r = engine.positions(pops.dna_left), engine.positions(pops.dna_right)
    base = baseline(engine, pops, seeds=seeds, duration=duration)
    out: dict[str, dict] = {}
    for channel in CHANNEL_ORNS:
        poles = {}
        for pole in (-1.0, 1.0):
            targets, rates = encode.stimulus(probe_score(**{channel: pole}), pops, engine)
            poles[pole] = np.array(
                [
                    decode.turn_index(
                        E.run(engine, targets, rates, seed=s, duration=duration).counts,
                        dna_l,
                        dna_r,
                        baseline=base["bias"],
                    ).turn
                    for s in range(seeds)
                ]
            )
        lo, hi = poles[-1.0], poles[1.0]
        span = float(hi.mean() - lo.mean())
        se = float(np.sqrt(hi.var(ddof=1) / seeds + lo.var(ddof=1) / seeds))
        out[channel] = {
            "left": round(float(lo.mean()), 5),
            "right": round(float(hi.mean()), 5),
            "span": round(span, 5),
            "se": round(se, 5),
            "t": round(span / se, 3) if se else None,
        }
        log.info("sweep %-12s span %+.4f  se %.4f  t %+.2f", channel, span, se, span / se if se else 0)
    return {"baseline": base, "channels": out}


def full_scale(
    engine: E.Engine, pops: Populations, bias: float, seeds: int, duration: float
) -> dict:
    """Every channel to one extreme against every channel to the other.

    The most stimulus this encoding can deliver, and therefore the test of whether the
    instrument is alive at all. A single channel drives two glomeruli of sixteen, so its
    effect is roughly an eighth of this and needs correspondingly more phases to resolve —
    a flat per-channel sweep at low `seeds` is a power statement, not a null result.
    """
    dna_l, dna_r = engine.positions(pops.dna_left), engine.positions(pops.dna_right)
    sides = {}
    for label, pole in (("right", 1.0), ("left", -1.0)):
        scored = probe_score(**dict.fromkeys(CHANNEL_ORNS, pole))
        targets, rates = encode.stimulus(scored, pops, engine)
        sides[label] = np.array(
            [
                decode.turn_index(
                    E.run(engine, targets, rates, seed=s, duration=duration).counts,
                    dna_l,
                    dna_r,
                    baseline=bias,
                ).turn
                for s in range(seeds)
            ]
        )
    r, left = sides["right"], sides["left"]
    diff = float(r.mean() - left.mean())
    se = float(np.sqrt(r.var(ddof=1) / seeds + left.var(ddof=1) / seeds))
    pooled = float(np.sqrt((r.var(ddof=1) + left.var(ddof=1)) / 2))
    log.info("full scale: %+.4f +/- %.4f  t %+.2f  d' %+.2f", diff, se, diff / se, diff / pooled)
    return {
        "right": round(float(r.mean()), 5),
        "left": round(float(left.mean()), 5),
        "difference": round(diff, 5),
        "se": round(se, 5),
        "t": round(diff / se, 3) if se else None,
        "d_prime": round(diff / pooled, 3) if pooled else None,
    }


def calibrate(
    engine: E.Engine, pops: Populations, seeds: int = 12, duration: float = E.DURATION
) -> dict:
    """Measure the bias, the dead band and whether any channel moves the fly at all."""
    swept = sweep(engine, pops, seeds=seeds, duration=duration)
    base = swept["baseline"]
    spans = [abs(v["span"]) for v in swept["channels"].values()]
    resolved = [c for c, v in swept["channels"].items() if v["t"] and abs(v["t"]) >= 2.0]
    return {
        "measured": datetime.now(tz=UTC).isoformat(),
        "engine": "mlx-lif-engine (Shiu et al. equations, Brian2-validated)",
        "readout": "DNa family, turn = (R-L)/(R+L), baseline-subtracted",
        "duration_s": duration,
        "seeds": seeds,
        "baseline_bias": base["bias"],
        "noise_sd": base["sd"],
        "dead_band": base["sd"],
        "dead_band_rule": "one SD of the blank-bill turn index, measured on the network alone",
        "signal": round(float(np.mean(spans)), 5),
        "snr": round(float(np.mean(spans)) / base["sd"], 4) if base["sd"] else None,
        "channels_resolved_above_noise": resolved,
        "full_scale": full_scale(engine, pops, base["bias"], seeds, duration),
        "sweep": swept["channels"],
        "network_hz": base["mean_network_hz"],
    }


@dataclass
class Inputs:
    """Everything a bundle needs that is not a simulation parameter."""

    bill: Bill
    vote: Vote
    scored: Scored
    engine: E.Engine
    pops: Populations
    atlas: Atlas
    space: idealpoint.Space | None = None
    vm: votematrix.VoteMatrix | None = None
    bias: float = 0.0
    dead_band: float = decode.DEAD_BAND
    duration: float = E.DURATION
    seed: int = 0
    #: How many input phases to run the same bill under. The replay plays `seed`; the rest
    #: exist so the page can state how often this bill comes out the other way.
    seeds: int = 8


def build(inputs: Inputs) -> Bundle:
    """Simulate one bill and freeze the result."""
    eng, pops, atlas = inputs.engine, inputs.pops, inputs.atlas
    dna_l, dna_r = eng.positions(pops.dna_left), eng.positions(pops.dna_right)
    atlas_idx = eng.positions(atlas.bodies)
    targets, rates = encode.stimulus(inputs.scored, pops, eng)

    started = datetime.now(tz=UTC)
    run = E.run(eng, targets, rates, seed=inputs.seed, duration=inputs.duration)
    elapsed = (datetime.now(tz=UTC) - started).total_seconds()

    turn = decode.turn_index(
        run.counts, dna_l, dna_r, baseline=inputs.bias, dead_band=inputs.dead_band
    )
    code = turn.vote(inputs.vote.inverted)
    chamber_advances = inputs.vote.in_favor > inputs.vote.against
    if inputs.vote.inverted:
        chamber_advances = not chamber_advances

    frame_s = inputs.duration / FRAMES
    race = {
        side: [
            round(float(c) / (n * frame_s), 4)
            for c in run.frame_counts(idx, FRAMES)
        ]
        for side, idx, n in (
            ("left_hz", dna_l, len(dna_l)),
            ("right_hz", dna_r, len(dna_r)),
        )
    }
    # Cumulative spikes per side. Sixteen DNa cells at ~1 Hz put 0 or 1 spikes in most
    # 10 ms frames, so a per-frame rate series is mostly zeros and reads as a comb. The
    # running total is both legible and closer to the statistic, which is a ratio of the
    # totals rather than anything instantaneous.
    cum = {
        f"{side}_cum": np.cumsum(run.frame_counts(idx, FRAMES)).tolist()
        for side, idx in (("left", dna_l), ("right", dna_r))
    }
    raster = run.raster(atlas_idx, FRAMES)
    wavering = _wavering(inputs, targets, rates, dna_l, dna_r)

    doc = {
        "schema": SCHEMA,
        "generated": started.isoformat(),
        "bill": {
            "uuid": inputs.bill.uuid,
            "title": inputs.bill.title,
            "mark": inputs.bill.mark,
            "summary": inputs.bill.introduction,
            "committee": inputs.bill.committee,
            "draft_type": inputs.bill.draft_type,
            "initiated": inputs.bill.initiated,
            "descriptors": list(inputs.bill.descriptors),
            "government_bill": inputs.bill.government_bill,
        },
        "chamber": {
            "voting_uuid": inputs.vote.uuid,
            "kind": inputs.vote.kind,
            "when": inputs.vote.when,
            "inverted": inputs.vote.inverted,
            "in_favor": inputs.vote.in_favor,
            "against": inputs.vote.against,
            "neutral": inputs.vote.neutral,
            "abstained": inputs.vote.abstained,
            "advances_bill": chamber_advances,
        },
        "channels": _channels(inputs.scored),
        "drive": {
            "encoding": "score sign picks the antenna; magnitude sets its rate",
            "background_hz": encode.BACKGROUND_HZ,
            "peak_hz": encode.PEAK_HZ,
            "orn_left": len(pops.orn_left),
            "orn_right": len(pops.orn_right),
            "laterality": "rootSide; ORNs carry no somaSide and unknown-side cells are dropped",
        },
        "sim": {
            "engine": "mlx-lif-engine (Shiu et al. equations, Brian2-validated)",
            "frames": FRAMES,
            "duration_s": inputs.duration,
            "dt_s": E.DT,
            "seed": inputs.seed,
            "neurons": eng.n,
            "edges": eng.edges,
            "total_spikes": int(run.counts.sum()),
            "mean_rate_hz": round(float(run.counts.sum()) / (eng.n * inputs.duration), 4),
            "wall_seconds": round(elapsed, 2),
        },
        "race": {
            **race,
            **cum,
            "turn": round(turn.turn, 5),
            "raw_turn": round(turn.raw, 5),
            "baseline_bias": round(inputs.bias, 5),
            "dead_band": round(inputs.dead_band, 5),
            "dna_left": len(dna_l),
            "dna_right": len(dna_r),
            "left_spikes": turn.left_spikes,
            "right_spikes": turn.right_spikes,
        },
        "verdict": {
            "supports_bill": turn.supports_bill,
            "code": code,
            "chamber_advances": chamber_advances,
            "agrees_with_chamber": (
                None if turn.supports_bill is None else turn.supports_bill == chamber_advances
            ),
        },
        "wavering": wavering,
        "seat": _seat(inputs, turn),
        "raster": _raster_meta(raster),
        "atlas": {
            "somas": atlas.k,
            "groups": list(atlas.fractions()),
            "sampled_fraction": {k: round(v, 4) for k, v in atlas.fractions().items()},
            "group_hz": _group_hz(atlas, atlas_idx, run, inputs.duration),
            "dn_left_slots": _slots(atlas, pops.dna_left),
            "dn_right_slots": _slots(atlas, pops.dna_right),
        },
        "audit": {
            "driven_bodies": {
                name: [int(b) for b in pops.orn[name]]
                for pair in CHANNEL_ORNS.values()
                for name in pair
            },
            "dna_left_bodies": [int(b) for b in pops.dna_left],
            "dna_right_bodies": [int(b) for b in pops.dna_right],
            "jev_input_tokens": inputs.scored.input_tokens,
        },
    }
    name = f"{inputs.bill.uuid[:8]}-{inputs.vote.uuid[:8]}"
    return Bundle(doc=doc, raster=pack_raster(raster), name=name)


def _wavering(
    inputs: Inputs,
    targets: np.ndarray,
    rates: np.ndarray,
    dna_l: np.ndarray,
    dna_r: np.ndarray,
) -> dict:
    """The same bill under other input phases.

    Run-to-run spread on this readout is real and comparable to a weak bill's effect, so a
    single verdict is not the whole truth and the bundle carries the distribution.
    """
    if inputs.seeds <= 1:
        return {"seeds": 1, "note": "not measured"}
    runs = []
    for seed in range(inputs.seeds):
        if seed == inputs.seed:
            continue
        counts = E.run(inputs.engine, targets, rates, seed=seed, duration=inputs.duration).counts
        t = decode.turn_index(
            counts, dna_l, dna_r, baseline=inputs.bias, dead_band=inputs.dead_band
        )
        runs.append({"seed": seed, "turn": round(t.turn, 5), "code": t.vote(inputs.vote.inverted)})
    tally: dict[str, int] = {}
    for r in runs:
        tally[r["code"]] = tally.get(r["code"], 0) + 1
    turns = np.array([r["turn"] for r in runs])
    return {
        "seeds": inputs.seeds,
        "note": "the same bill, same scores, different input phase",
        "runs": runs,
        "tally": tally,
        "turn_sd": round(float(turns.std(ddof=1)), 5) if len(turns) > 1 else 0.0,
        "turn_min": round(float(turns.min()), 5),
        "turn_max": round(float(turns.max()), 5),
    }


def _group_hz(
    atlas: Atlas, atlas_idx: np.ndarray, run: E.Run, duration: float
) -> dict[str, list[float]]:
    """Per drawn group, the true firing rate in each frame. Never raster-derived."""
    frame_s = duration / FRAMES
    out = {}
    for gid, name in enumerate(atlas.group_names()):
        members = atlas_idx[atlas.group == gid]
        if not len(members):
            continue
        counts = run.frame_counts(members, FRAMES)
        out[name] = [round(float(c) / (len(members) * frame_s), 2) for c in counts]
    return out


def _slots(atlas: Atlas, bodies: np.ndarray) -> list[int]:
    """Atlas positions of the given body IDs. A DN without a soma location has none."""
    index = {int(b): i for i, b in enumerate(atlas.bodies)}
    return [index[int(b)] for b in bodies if int(b) in index]


def _channels(scored: Scored) -> list[dict]:
    """The nine Jev channels as the page draws them: score, confidence, and the drive."""
    drive = encode.channel_drive(scored)
    out = []
    for key, question, neg, pos in rubric2.QUESTIONS:
        out.append(
            {
                "key": key,
                "question": question,
                "negative": neg,
                "positive": pos,
                "orn": list(CHANNEL_ORNS[key]),
                "score": round(scored.scores.get(key, 0.0), 4),
                "confidence": round(scored.confidence.get(key, 0.0), 4),
                "drive": round(drive[key], 4),
            }
        )
    out.append(
        {
            "key": "salience",
            "question": "How much does this bill actually change?",
            "negative": "pure housekeeping",
            "positive": "central political controversy",
            "orn": [],
            "score": round(scored.scores.get("salience", 0.0), 4),
            "confidence": round(scored.confidence.get("salience", 0.0), 4),
            "drive": round(encode.salience_gain(scored.scores.get("salience", 0.0)), 4),
        }
    )
    return out


def _seat(inputs: Inputs, turn: decode.Turn) -> dict:
    """Where this one vote puts the fly on the chamber's first dimension.

    **One vote does not identify a position**, and the estimate says so. `fly_dim1` is the
    mean dimension-1 coordinate of the MPs who voted the way Kärbes just did on this very
    bill — a real, defined quantity, not a projection faked from a single observation. A
    declined vote places nothing, and returns null rather than the centre.
    """
    if inputs.space is None or inputs.vm is None:
        return {"available": False}
    space, vm = inputs.space, inputs.vm
    latest = vm.latest_faction()
    chamber = [
        {"dim1": round(float(c[0]), 4), "faction": latest.get(mid, "")}
        for mid, c in zip(space.member_ids, space.coords, strict=True)
    ]

    supports = turn.supports_bill
    fly_dim1, n_like = None, 0
    try:
        column = [v.uuid for v in vm.votes].index(inputs.vote.uuid)
    except ValueError:
        column = None
    if column is not None and supports is not None:
        want = votematrix.SUPPORT if supports else votematrix.OPPOSE
        like = [
            float(space.coords[i][0])
            for i, mid in enumerate(space.member_ids)
            if vm.stance[vm.member_ids.index(mid), column] == want
        ]
        n_like = len(like)
        fly_dim1 = round(float(np.mean(like)), 4) if like else None

    return {
        "available": True,
        "basis": "mean dimension-1 coordinate of the MPs who voted as Karbes did on this bill",
        "votes_used": 1,
        "identified": False,
        "fly_dim1": fly_dim1,
        "n_like_fly": n_like,
        "explained_dim1": round(float(space.explained[0]), 4),
        # More than 101: members are replaced during a term, so this is everyone who held
        # a seat and cast enough votes to be placed, not the chamber at one moment.
        "chamber": chamber,
        "factions": idealpoint.bloc_separation(space, vm),
    }


def _raster_meta(frames: list[np.ndarray]) -> dict:
    events = int(sum(len(f) for f in frames))
    return {
        "encoding": "u32 frames | u32 offsets[frames+1] | u16 atlas slots",
        "magic": RASTER_MAGIC.decode(),
        "frames": len(frames),
        "events": events,
        "bytes": len(RASTER_MAGIC) + 4 + 4 * (len(frames) + 1) + 2 * events,
    }
