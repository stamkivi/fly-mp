"""Leaky integrate-and-fire kernel over the MaleCNS graph.

**Event-driven propagation with vectorised membrane integration is not an optimisation
here, it is the difference between the study running and not running.** Touching all
25.6M edges on every one of the 5,000 timesteps is 128 G edge-operations per simulation —
roughly 139 hours for Stage 3. Propagating only from cells that actually spiked brings
that to ~64M edge-ops at a plausible 5 Hz, and the dominant remaining cost becomes
membrane integration, which numpy does in one call per step rather than 166,700.

Parameters follow Stonkfly's documented table, reimplemented rather than copied.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from karbes.graph.load import Graph

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Params:
    dt: float = 0.1e-3  # 0.1 ms
    tau_m: float = 20e-3  # membrane
    tau_s: float = 5e-3  # synaptic
    v_rest: float = -52e-3
    v_threshold: float = -45e-3
    v_reset: float = -52e-3
    delay: float = 1.8e-3
    refractory: float = 2.2e-3
    weight_scale: float = 0.275e-3  # mV per synaptic contact
    duration: float = 0.5  # 500 ms of neural time

    @property
    def steps(self) -> int:
        return round(self.duration / self.dt)

    @property
    def delay_steps(self) -> int:
        return max(1, round(self.delay / self.dt))

    @property
    def refractory_steps(self) -> int:
        return max(1, round(self.refractory / self.dt))


#: Stonkfly's documented parameters, as a singleton so it is not rebuilt per call.
DEFAULTS = Params()


@dataclass
class Result:
    spike_counts: np.ndarray  # (n,) spikes per neuron over the run
    duration: float
    total_spikes: int
    steps: int
    input_spikes: int
    history: np.ndarray | None = field(default=None)  # optional (steps,) population rate

    def rates(self) -> np.ndarray:
        """Firing rate in Hz per neuron."""
        return self.spike_counts / self.duration

    def mean_rate(self) -> float:
        return float(self.spike_counts.sum() / (len(self.spike_counts) * self.duration))


def _expand_rows(starts: np.ndarray, lens: np.ndarray) -> np.ndarray:
    """Concatenate the CSR index ranges [s, s+len) for many rows, without a Python loop."""
    total = int(lens.sum())
    ends = np.cumsum(lens)
    return np.repeat(starts, lens) + (np.arange(total) - np.repeat(ends - lens, lens))


def run(
    graph: Graph,
    drive: dict[int, float],
    params: Params | None = None,
    seed: int = 0,
    record_history: bool = False,
    poisson_input: bool = False,
) -> Result:
    """Simulate `params.duration` of neural time.

    `drive` maps neuron index to an input rate in Hz. Each input spike injects one
    threshold-sized step, so a driven cell fires at roughly its commanded rate.

    Input is a **regular spike train by default, not Poisson**. Poisson drive puts a
    variance on the readout that swamped the stimulus: measured SNR 0.26, with run-to-run
    noise four times the effect of moving an axis from -1 to +1. That noise is a modelling
    choice rather than physiology, so it is removed. Per-cell phases are staggered so the
    population does not fire in lockstep, which would be its own artefact. `seed` then
    only sets those phases, and the simulation is genuinely deterministic.
    """
    n = graph.n
    p = params or DEFAULTS
    rng = np.random.default_rng(seed)

    v = np.full(n, p.v_rest, dtype=np.float32)
    last_spike = np.full(n, -(10**6), dtype=np.int32)
    counts = np.zeros(n, dtype=np.int32)

    # Ring buffer of synaptic input, one slot per step of axonal delay.
    dsteps = p.delay_steps
    pending = np.zeros((dsteps, n), dtype=np.float32)

    decay_v = np.float32(np.exp(-p.dt / p.tau_m))
    v_rest = np.float32(p.v_rest)
    thr = np.float32(p.v_threshold)
    reset = np.float32(p.v_reset)
    wscale = np.float32(p.weight_scale)
    # One input spike moves a resting cell across threshold.
    kick = np.float32(p.v_threshold - p.v_rest)

    driven_idx = np.fromiter(drive.keys(), dtype=np.int64, count=len(drive))
    driven_hz = np.array([drive[int(i)] for i in driven_idx], dtype=np.float64)
    if poisson_input:
        driven_p = (driven_hz * p.dt).astype(np.float32)
        phase = interval = None
    else:
        # Regular train: fire when the accumulated phase wraps past 1.
        interval = np.where(driven_hz > 0, driven_hz * p.dt, 0.0)
        phase = rng.random(len(driven_idx)) if len(driven_idx) else np.zeros(0)

    history = np.zeros(p.steps, dtype=np.float32) if record_history else None
    total_in = 0
    indptr, indices, weights, sign = graph.indptr, graph.indices, graph.weights, graph.sign

    for step in range(p.steps):
        slot = step % dsteps

        # Current-based LIF with instantaneous PSPs: an arriving spike is a voltage
        # step of `contacts x weight_scale`, which is what "0.275 mV per contact" means.
        # Filtering it through a 5 ms synapse and adding the filtered value every step
        # instead integrates each event ~50x over, and the network runs away.
        v -= v_rest
        v *= decay_v
        v += v_rest
        v += pending[slot]
        pending[slot] = 0.0

        if len(driven_idx):
            if poisson_input:
                fired_in = rng.random(len(driven_idx)) < driven_p
            else:
                phase += interval
                fired_in = phase >= 1.0
                phase[fired_in] -= 1.0
            if fired_in.any():
                v[driven_idx[fired_in]] += kick
                total_in += int(fired_in.sum())

        refractory = (step - last_spike) < p.refractory_steps
        spiking = (v >= thr) & ~refractory
        idx = np.flatnonzero(spiking)
        if idx.size:
            v[idx] = reset
            last_spike[idx] = step
            counts[idx] += 1

            # Propagate only from cells that fired: the whole point of the design.
            starts, ends = indptr[idx], indptr[idx + 1]
            lens = ends - starts
            nz = lens > 0
            if nz.any():
                starts, lens, srcs = starts[nz], lens[nz], idx[nz]
                offsets = _expand_rows(starts, lens)
                targets = indices[offsets]
                amps = weights[offsets] * wscale * np.repeat(sign[srcs], lens)
                # Ring of exactly `dsteps` slots, so writing to this slot delivers the
                # current one axonal delay later, when the ring comes back around.
                np.add.at(pending[slot], targets, amps)

        if history is not None:
            history[step] = idx.size

    return Result(
        spike_counts=counts,
        duration=p.duration,
        total_spikes=int(counts.sum()),
        steps=p.steps,
        input_spikes=total_in,
        history=history,
    )
