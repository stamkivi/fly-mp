"""The fly in the Speaker's chair: drive the brain with a sitting and record what it did.

Three stimulus rules, all engineered and all declared:

* **A speech is a scent from the speaker's side of the hall.** The olfactory receptor
  neurons on that side, at a low rate, for the speech's compressed duration. This is the
  glow of someone talking, and its onset out of silence is the measured wave — antennal
  lobe at 5 ms, mushroom body at 15 ms. Scent never reaches the giant fibre, which is why
  speeches take this route: one-sided *motion* drive fires the escape reflex by itself,
  and a chair that bolts at every speaker is not a chair.
* **Hostility makes something come at the chair.** LC4/LPLC2 on the speaker's side, at a
  rate that is zero until `tone.hostility` clears a knee and then rises to `LOOM_HZ`. A
  civil or mildly accusatory speech drives them not at all; a confident insult drives
  them hard. Downstream — the giant fibre, the recoil — is the connectome's.
* **A disturbance lunges; a vote fills the hall.** A heckle is a brief looming pulse from
  the heckler's side (both sides if unseated). A vote is strong scent from both sides.

Every event starts the brain from rest, which is what the measured 100 ms decay makes it
do anyway, and is followed by 150 ms of silence so the next onset is an onset.

What is recorded per event: giant-fibre spikes (the fly's bell), the DNa turn (which way
it threw itself), and the frames the page draws.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from karbes import decode
from karbes import engine as E
from karbes.atlas import Atlas
from karbes.graph.populations import Populations
from karbes.sitting import SILENCE, Event, Sitting

log = logging.getLogger(__name__)

SPEECH_HZ = 30.0  # ORNs on the speaker's side while they speak
LOOM_HZ = 40.0  # LC4/LPLC2 at hostility 1.0; measured to drive DNp01 at ~90 spikes / 300 ms
LOOM_KNEE = 0.3  # hostility below this is not a threat; the giant fibre fires for any drive
HECKLE_HZ = 40.0
VOTE_HZ = 90.0
FPS = 10  # frames per biological second the page receives
PINPRICKS = 400  # at most this many individual cells per frame, so the page stays small
BELL_GF = 8  # giant-fibre spikes in one event before it counts as the bell: a twitch is not a bolt


@dataclass
class Reaction:
    index: int
    gf: int  # giant-fibre spikes: the fly's bell
    turn: float  # (R-L)/(R+L) after baseline; + is a throw to the right
    dna_l: int
    dna_r: int
    spikes: int
    active: int
    frames: int


@dataclass
class Recording:
    date: str
    reactions: list[Reaction] = field(default_factory=list)
    group_hz: dict[str, list[float]] = field(default_factory=dict)  # per frame
    raster: list[list[int]] = field(default_factory=list)  # per frame, atlas positions
    frame_event: list[int] = field(default_factory=list)  # per frame, event index (-1 = silence)


def loom_rate(hostility: float) -> float:
    """Zero below the knee, LOOM_HZ at 1.0, linear between. Declared, not fitted."""
    return LOOM_HZ * max(0.0, hostility - LOOM_KNEE) / (1.0 - LOOM_KNEE)


def _targets(e: Event, pops: Populations, eng: E.Engine) -> tuple[np.ndarray, np.ndarray]:
    """Pack indices and rates for one event."""
    parts: list[tuple[np.ndarray, float]] = []
    both = e.side not in ("L", "R")
    orn = {"L": pops.orn_left, "R": pops.orn_right}
    if e.kind == "speech":
        for sd in ("L", "R") if both else (e.side,):
            parts.append((eng.positions(orn[sd]), SPEECH_HZ))
        hz = loom_rate(e.hostility)
        if hz > 0:
            parts.append((_loom(e.side, pops, eng), hz))
    elif e.kind == "heckle":
        parts.append((_loom(e.side, pops, eng), HECKLE_HZ))
    elif e.kind in ("vote", "presence"):
        hz = VOTE_HZ if e.kind == "vote" else SPEECH_HZ
        parts.append((eng.positions(pops.orn_left), hz))
        parts.append((eng.positions(pops.orn_right), hz))
    tg = np.concatenate([p[0] for p in parts]) if parts else np.zeros(0, np.int32)
    rt = np.concatenate([np.full(len(p[0]), p[1]) for p in parts]) if parts else np.zeros(0)
    order = np.argsort(tg)
    return tg[order].astype(np.int32), rt[order]


_LOOM_SIDES: dict[str, np.ndarray] | None = None


def _loom(side: str, pops: Populations, eng: E.Engine) -> np.ndarray:
    """Looming cells on one side, split by soma side once and cached."""
    global _LOOM_SIDES
    if _LOOM_SIDES is None:
        import re

        from pyarrow import feather

        from karbes.graph.populations import ANNOTATIONS

        d = feather.read_table(
            Path("data/malecns") / ANNOTATIONS, columns=["bodyId", "instance", "somaSide"]
        ).to_pydict()
        want = {int(b) for b in pops.looming}
        sides: dict[str, list[int]] = {"L": [], "R": []}
        for b, i, s in zip(d["bodyId"], d["instance"], d["somaSide"], strict=True):
            if int(b) not in want:
                continue
            sd = s if s in ("L", "R") else (re.search(r"_([LR])$", i or "") or [None, None])[1]
            if sd in sides:
                sides[sd].append(int(b))
        _LOOM_SIDES = {k: eng.positions(np.array(v)) for k, v in sides.items()}
        _LOOM_SIDES[""] = np.concatenate([_LOOM_SIDES["L"], _LOOM_SIDES["R"]])
    return _LOOM_SIDES.get(side, _LOOM_SIDES[""])


def record(
    s: Sitting, eng: E.Engine, pops: Populations, atlas: Atlas, bias: float, *, limit: int | None = None,
    seed: int = 0,
) -> Recording:
    L = eng.positions(pops.dna_left)
    R = eng.positions(pops.dna_right)
    GF = eng.positions(pops.giant_fibre)
    atlas_pos = eng.positions(atlas.bodies)
    # atlas order -> pack index; the raster needs pack index -> atlas slot
    slot = np.full(eng.n, -1, np.int32)
    slot[atlas_pos] = np.arange(len(atlas_pos), dtype=np.int32)
    groups = list(atlas.group_names())
    members = {g: atlas_pos[atlas.group == i] for i, g in enumerate(groups)}
    rec = Recording(date=s.date, group_hz={g: [] for g in groups})
    rng = np.random.default_rng(seed)

    stimuli = [(i, e) for i, e in enumerate(s.events) if e.bio > 0]
    if limit:
        stimuli = stimuli[:limit]
    for n, (i, e) in enumerate(stimuli, 1):
        tg, rt = _targets(e, pops, eng)
        dur = e.bio + SILENCE
        run = E.run(eng, tg, rt, seed=seed + i, duration=dur)
        frames = max(1, round(dur * FPS))
        on_frames = max(1, round(e.bio * FPS))
        counts = run.counts
        turn = decode.turn_index(counts, L, R, baseline=bias, dead_band=0.0).turn
        rec.reactions.append(Reaction(
            index=i, gf=int(counts[GF].sum()), turn=round(float(turn), 4),
            dna_l=int(counts[L].sum()), dna_r=int(counts[R].sum()),
            spikes=len(run.events), active=int((counts > 0).sum()), frames=frames,
        ))
        for g in groups:
            fc = run.frame_counts(members[g], frames)
            per_cell_per_s = fc / max(len(members[g]), 1) * FPS
            rec.group_hz[g].extend(round(float(x), 3) for x in per_cell_per_s)
        for f, ids in enumerate(run.raster(atlas_pos, frames)):
            ids = np.asarray(ids)
            if len(ids) > PINPRICKS:
                ids = rng.choice(ids, PINPRICKS, replace=False)
            rec.raster.append(sorted(int(x) for x in ids))
            rec.frame_event.append(i if f < on_frames else -1)
        if n % 25 == 0:
            log.info("chair: %d/%d events, %d frames", n, len(stimuli), len(rec.raster))
    return rec


def save(rec: Recording, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(rec)), encoding="utf-8")
    tmp.replace(path)
