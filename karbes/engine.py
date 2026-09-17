"""Adapter onto the published LIF engine.

**Kärbes no longer carries its own kernel.** `karbes/sim/lif.py` implemented the synapse
as an instantaneous voltage step, which is a documented failure mode of this model, and
every dynamical conclusion drawn from it was a description of that bug. The engine is now
`mlx-lif-engine` (MIT, `Kisame76/drosophila-brain-mlx`), which implements Shiu et al.'s
equations, is validated against Brian2 to identical per-neuron spike counts, and runs on
this same MaleCNS v1.0 pack.

Two facts worth keeping in view:

* Its pack's `neuron_ids` are **identical** to the retained set `graph/populations.py`
  resolves — same 166,700 bodies, same order — so body IDs join across both.
* Its edge rule is stricter than ours: a presynaptic neuron with an unknown, modulatory or
  histaminergic transmitter keeps its node but contributes **no outgoing edges**, giving
  24,469,412 edges against our 25,582,938. That is the published materialisation, and ours
  guessed excitatory for 2,850 neurons.

Sanity, measured 2026-09-17 on MaleCNS v1.0: no input at all leaves the network at exactly
0 spikes, 5 Hz on the ORNs gives 2.86 Hz network-wide with 6% of neurons active, and 150 Hz
gives 4.89 Hz. Silent at rest, sparse, and graded — none of which our own kernel did.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

PACK = "male_cns_v1"
DT = 1e-4  # one engine tick, 0.1 ms
DURATION = 1.0  # seconds of neural time per bill


@dataclass
class Engine:
    """A loaded connectome pack plus the body-ID index every population resolves through."""

    pack: object
    index: dict[int, int]

    @property
    def n(self) -> int:
        return int(self.pack.n_neurons)

    @property
    def edges(self) -> int:
        return int(self.pack.n_edges)

    def positions(self, bodies: np.ndarray) -> np.ndarray:
        """Pack indices for body IDs. Silently drops any the pack does not carry."""
        return np.array(
            sorted(self.index[int(b)] for b in bodies if int(b) in self.index), dtype=np.int32
        )


def load(pack_dir: Path | None = None) -> Engine:
    from lif import core

    path = pack_dir or (core.PACK_DIR.parent / PACK)
    pack = core.load_pack(path)
    log.info("engine pack %s: %s neurons", path.name, f"{pack.n_neurons:,}")
    return Engine(pack=pack, index={int(n): i for i, n in enumerate(pack.neuron_ids)})


@dataclass
class Run:
    """One simulation: every spike, as (tick, neuron), plus the per-neuron totals."""

    events: np.ndarray  # (spikes, 2) int32 — tick, neuron index
    counts: np.ndarray  # (n,) spikes per neuron
    ticks: int
    duration: float

    def frame_counts(self, members: np.ndarray, frames: int) -> np.ndarray:
        """Spikes from `members` in each of `frames` equal slices. Counts every spike.

        Deliberately not derived from the raster below: the raster is deduplicated per
        frame because the page only asks whether a cell lit up, and counting its entries
        understates the rate worst where the rate is highest.
        """
        if not len(self.events):
            return np.zeros(frames, dtype=np.int64)
        member = np.zeros(self.counts.shape, dtype=bool)
        member[members] = True
        hit = member[self.events[:, 1]]
        if not hit.any():
            return np.zeros(frames, dtype=np.int64)
        frame = self.events[hit, 0].astype(np.int64) * frames // self.ticks
        return np.bincount(np.clip(frame, 0, frames - 1), minlength=frames)

    def raster(self, members: np.ndarray, frames: int) -> list[np.ndarray]:
        """Per frame, which of `members` fired, as positions into `members`."""
        slot = np.full(self.counts.shape, -1, dtype=np.int32)
        slot[members] = np.arange(len(members), dtype=np.int32)
        out: list[np.ndarray] = [np.empty(0, dtype=np.uint16) for _ in range(frames)]
        if not len(self.events):
            return out
        s = slot[self.events[:, 1]]
        keep = s >= 0
        if not keep.any():
            return out
        frame = self.events[keep, 0].astype(np.int64) * frames // self.ticks
        np.clip(frame, 0, frames - 1, out=frame)
        order = np.argsort(frame, kind="stable")
        frame, s = frame[order], s[keep][order]
        for f, start, stop in zip(*_runs(frame), strict=True):
            out[f] = np.unique(s[start:stop]).astype(np.uint16)
        return out


def _runs(sorted_frames: np.ndarray):
    """Frame ids and the [start, stop) slice of each run in a sorted frame array."""
    edges = np.flatnonzero(np.diff(sorted_frames)) + 1
    starts = np.concatenate([[0], edges])
    stops = np.concatenate([edges, [len(sorted_frames)]])
    return sorted_frames[starts], starts, stops


def run(
    engine: Engine,
    targets: np.ndarray,
    rates_hz: np.ndarray,
    seed: int,
    duration: float = DURATION,
) -> Run:
    """Drive `targets` at per-neuron `rates_hz` for `duration`.

    The engine's `Stimulus` carries a fully materialised draw matrix rather than one rate,
    which is what lets every channel and every side have its own input rate in one run.
    """
    import mlx.core as mx
    from lif import core, engine_fused

    if len(targets) != len(rates_hz):
        raise ValueError(f"{len(targets)} targets but {len(rates_hz)} rates")
    ticks = round(duration / DT)
    rng = np.random.default_rng(seed)
    draws = mx.array(rng.random((ticks, len(targets))) < (np.asarray(rates_hz) * DT)[None, :])
    stim = core.Stimulus(
        targets=np.asarray(targets, dtype=np.int32),
        draws=draws,
        n_ticks=ticks,
        rate_hz=float("nan"),  # per-neuron rates, so there is no single one to record
        seed=seed,
    )
    result = engine_fused.run(engine.pack, stim, chunk=32, edge_split=1, record=True)
    events = np.asarray(result.events)
    counts = (
        np.bincount(events[:, 1], minlength=engine.n)
        if len(events)
        else np.zeros(engine.n, dtype=np.int64)
    )
    return Run(events=events, counts=counts, ticks=ticks, duration=duration)
