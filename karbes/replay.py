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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from karbes import decode, encode
from karbes.analysis import idealpoint, votematrix
from karbes.atlas import Atlas
from karbes.graph.load import Graph
from karbes.graph.populations import CHANNEL_ORNS, Populations
from karbes.riigikogu.model import Bill, Vote
from karbes.score import rubric2
from karbes.score.jev import Scored
from karbes.sim import lif

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
    """A bill that says nothing: every channel zero, at full confidence."""
    keys = (*rubric2.KEYS, "salience")
    return Scored(
        scores=dict.fromkeys(keys, 0.0),
        confidence=dict.fromkeys(keys, 1.0),
        input_tokens=0,
    )


def noise_floor(
    graph: Graph, pops: Populations, seeds: int = 10, params: lif.Params | None = None
) -> dict:
    """|delta| across seeds on a blank bill: the dead band, measured on the brain itself.

    **Not zero input.** With no drive at all this network is perfectly silent — it is
    quiescent without input at every weight scale tested — so a zero-input baseline
    measures nothing and returns exactly 0.0. The honest baseline is the fly smelling its
    own background: all sixteen ORN populations at `encode.BACKGROUND_HZ`, every channel
    scored zero. Changing `seed` then changes only the input phase, which is precisely the
    source of the run-to-run variation the SNR is about.

    This is the only place a threshold comes from. It never looks at the chamber, so it
    cannot be tuned to make the voting record agree with anyone.
    """
    p = params or lif.DEFAULTS
    probes = lif.Probes(
        frames=FRAMES,
        groups={
            "dn_left": graph.index_of(pops.dn_left),
            "dn_right": graph.index_of(pops.dn_right),
        },
    )
    sizes = {"dn_left": len(pops.dn_left), "dn_right": len(pops.dn_right)}
    background = encode.drive(blank_score(), pops, graph)
    deltas, rates = [], []
    for seed in range(seeds):
        result = lif.run(graph, background, params=p, seed=seed, probes=probes)
        deltas.append(decode.race(result.group_counts, sizes, p.duration).delta)
        rates.append(result.mean_rate())
    arr = np.array(deltas)
    return {
        "seeds": seeds,
        "baseline": "all 16 ORN populations at background, every channel scored zero",
        "background_hz": encode.BACKGROUND_HZ,
        "mean_delta_hz": float(arr.mean()),
        "sd_delta_hz": float(arr.std(ddof=1)) if seeds > 1 else 0.0,
        "max_abs_delta_hz": float(np.abs(arr).max()),
        "mean_network_rate_hz": float(np.mean(rates)),
        "deltas_hz": [float(d) for d in arr],
    }


def sweep(graph: Graph, pops: Populations, params: lif.Params | None = None, seed: int = 0) -> dict:
    """Each channel driven to -1 and +1 in turn, everything else at zero.

    SPEC's Stage 2 verification: a flat line here means the connectome is not converting
    the stimulus into anything, and the whole readout is decoration.
    """
    p = params or lif.DEFAULTS
    probes = lif.Probes(
        frames=FRAMES,
        groups={
            "dn_left": graph.index_of(pops.dn_left),
            "dn_right": graph.index_of(pops.dn_right),
        },
    )
    sizes = {"dn_left": len(pops.dn_left), "dn_right": len(pops.dn_right)}
    out: dict[str, dict[str, float]] = {}
    for channel in CHANNEL_ORNS:
        for pole in (-1.0, 1.0):
            scored = blank_score()
            scored.scores[channel] = pole
            drive = encode.drive(scored, pops, graph)
            result = lif.run(graph, drive, params=p, seed=seed, probes=probes)
            delta = decode.race(result.group_counts, sizes, p.duration).delta
            out.setdefault(channel, {})[f"{pole:+.0f}"] = round(delta, 4)
            log.info("sweep %-12s %+.0f -> delta %+.3f Hz", channel, pole, delta)
    return out


def calibrate(
    graph: Graph, pops: Populations, seeds: int = 20, params: lif.Params | None = None
) -> dict:
    """Measure the dead band and the signal-to-noise ratio, and report both.

    **The dead band is one standard deviation of the blank-bill readout.** A race closer
    than the spread this brain produces on a bill that says nothing is not a decision.
    The rule is fixed here, on the network alone; no part of it can see the chamber.

    SNR is the stimulus effect over that spread. It has been measured at roughly 0.5, and
    it is reported rather than engineered away: a brain visibly making up its mind is the
    point, and averaging it into false confidence would be the dishonest move.
    """
    floor = noise_floor(graph, pops, seeds=seeds, params=params)
    swept = sweep(graph, pops, params=params)
    spans = [abs(v["+1"] - v["-1"]) for v in swept.values()]
    signal = float(np.mean(spans))
    noise = floor["sd_delta_hz"]
    return {
        "measured": datetime.now(tz=UTC).isoformat(),
        "weight_scale": (params or lif.DEFAULTS).weight_scale,
        "noise_floor": floor,
        "sweep": swept,
        "signal_hz": round(signal, 4),
        "widest_channel_hz": round(float(np.max(spans)), 4),
        "narrowest_channel_hz": round(float(np.min(spans)), 4),
        "noise_hz": round(noise, 4),
        "snr": round(signal / noise, 4) if noise else None,
        "dead_band_hz": round(noise, 4),
        "dead_band_rule": "one SD of the blank-bill readout, measured on the network alone",
    }


@dataclass
class Inputs:
    """Everything a bundle needs that is not a simulation parameter."""

    bill: Bill
    vote: Vote
    scored: Scored
    graph: Graph
    pops: Populations
    atlas: Atlas
    space: idealpoint.Space | None = None
    vm: votematrix.VoteMatrix | None = None
    dead_band: float = decode.DEAD_BAND_HZ
    params: lif.Params = field(default_factory=lambda: lif.DEFAULTS)
    seed: int = 0
    #: How many input phases to run the same bill under. The replay plays `seed`; the rest
    #: exist so the page can state how often this bill comes out the other way.
    seeds: int = 8


def build(inputs: Inputs) -> Bundle:
    """Simulate one bill and freeze the result."""
    p = inputs.params
    drive = encode.drive(inputs.scored, inputs.pops, inputs.graph)
    atlas_idx = inputs.graph.index_of(inputs.atlas.bodies)
    probes = lif.Probes(
        frames=FRAMES,
        groups={
            "dn_left": inputs.graph.index_of(inputs.pops.dn_left),
            "dn_right": inputs.graph.index_of(inputs.pops.dn_right),
        },
        raster=atlas_idx,
    )
    started = datetime.now(tz=UTC)
    result = lif.run(inputs.graph, drive, params=p, seed=inputs.seed, probes=probes)
    elapsed = (datetime.now(tz=UTC) - started).total_seconds()

    sizes = {"dn_left": len(inputs.pops.dn_left), "dn_right": len(inputs.pops.dn_right)}
    race = decode.race(result.group_counts, sizes, p.duration, dead_band=inputs.dead_band)
    code = race.vote(inputs.vote.inverted)
    chamber_advances = inputs.vote.in_favor > inputs.vote.against
    if inputs.vote.inverted:
        chamber_advances = not chamber_advances

    wavering = _wavering(inputs, drive, probes, sizes)

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
        "orn": {
            name: round(hz, 3) for name, hz in encode.orn_rates(inputs.scored, inputs.pops).items()
        },
        "sim": {
            "frames": FRAMES,
            "duration_s": p.duration,
            "dt_s": p.dt,
            "weight_scale": p.weight_scale,
            "seed": inputs.seed,
            "neurons": inputs.graph.n,
            "edges": inputs.graph.nnz,
            "total_spikes": result.total_spikes,
            "mean_rate_hz": round(result.mean_rate(), 4),
            "input_spikes": result.input_spikes,
            "wall_seconds": round(elapsed, 2),
        },
        "race": {
            "left_hz": [round(float(x), 4) for x in race.left_hz],
            "right_hz": [round(float(x), 4) for x in race.right_hz],
            "delta_hz": [round(float(x), 4) for x in race.delta_hz],
            "delta": round(race.delta, 4),
            "settled_from_frame": race.settled_from,
            "dead_band_hz": round(race.dead_band, 4),
            "dn_left": sizes["dn_left"],
            "dn_right": sizes["dn_right"],
        },
        "verdict": {
            "supports_bill": race.supports_bill,
            "code": code,
            "chamber_advances": chamber_advances,
            "agrees_with_chamber": (
                None if race.supports_bill is None else race.supports_bill == chamber_advances
            ),
        },
        "wavering": wavering,
        "seat": _seat(inputs, race),
        "raster": _raster_meta(result.raster),
        "atlas": {
            "somas": inputs.atlas.k,
            "groups": list(inputs.atlas.fractions()),
            "sampled_fraction": {k: round(v, 4) for k, v in inputs.atlas.fractions().items()},
            # Atlas slots of the two racing pools, so the page can show the race in the
            # brain itself rather than only in the chart beside it.
            "dn_left_slots": _slots(inputs.atlas, inputs.pops.dn_left),
            "dn_right_slots": _slots(inputs.atlas, inputs.pops.dn_right),
        },
        "audit": {
            "driven_bodies": {
                name: [int(b) for b in inputs.pops.orn[name]]
                for pair in CHANNEL_ORNS.values()
                for name in pair
            },
            "dn_left_bodies": [int(b) for b in inputs.pops.dn_left],
            "dn_right_bodies": [int(b) for b in inputs.pops.dn_right],
            "jev_input_tokens": inputs.scored.input_tokens,
        },
    }
    name = f"{inputs.bill.uuid[:8]}-{inputs.vote.uuid[:8]}"
    return Bundle(doc=doc, raster=pack_raster(result.raster), name=name)


def _wavering(
    inputs: Inputs, drive: dict[int, float], probes: lif.Probes, sizes: dict[str, int]
) -> dict:
    """The same bill under other input phases. **This is the finding, not a robustness
    check.**

    SNR on this readout is below 1, so which way the fly goes is genuinely uncertain. That
    has to be stated on the page with a number beside it rather than hidden behind a single
    confident verdict. The extra runs record only the descending pools, not the raster, so
    they cost a simulation each and nothing else.
    """
    if inputs.seeds <= 1:
        return {"seeds": 1, "note": "not measured"}
    bare = lif.Probes(frames=FRAMES, groups=probes.groups)
    runs = []
    for seed in range(inputs.seeds):
        if seed == inputs.seed:
            continue
        result = lif.run(inputs.graph, drive, params=inputs.params, seed=seed, probes=bare)
        race = decode.race(
            result.group_counts, sizes, inputs.params.duration, dead_band=inputs.dead_band
        )
        runs.append({"seed": seed, "delta": round(race.delta, 4), "code": race.vote(inputs.vote.inverted)})
    tally: dict[str, int] = {}
    for r in runs:
        tally[r["code"]] = tally.get(r["code"], 0) + 1
    deltas = np.array([r["delta"] for r in runs])
    return {
        "seeds": inputs.seeds,
        "note": "the same bill, same scores, different input phase",
        "runs": runs,
        "tally": tally,
        "delta_sd_hz": round(float(deltas.std(ddof=1)), 4) if len(deltas) > 1 else 0.0,
        "delta_min_hz": round(float(deltas.min()), 4),
        "delta_max_hz": round(float(deltas.max()), 4),
    }


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


def _seat(inputs: Inputs, race: decode.Race) -> dict:
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

    supports = race.supports_bill
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
