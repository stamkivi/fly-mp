"""Descending-neuron activity to a vote.

`delta = mean rate(right DN pool) - mean rate(left DN pool)`, read over every descending
neuron with a lateralised soma. **An engineered interface, labelled as such** — there are
no "aye" neurons in a fly, and which side means "for" was fixed arbitrarily before any
agreement with the chamber was measured.

Two things here are load-bearing for the honesty of the result:

* **The dead band comes from the fly's own noise floor, never from the chamber.** It is
  the spread of `delta` with no stimulus at all, so "the fly declined" means "the race was
  inside the range this brain produces when it is smelling nothing" — a statement about
  the network, not a threshold tuned until the voting record looked good.
* **The rejection-motion flip lives here and only here**, so every control arm inherits
  it identically. On a `Tagasi lukkamine` motion, supporting the bill means voting VASTU.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from karbes.riigikogu.model import EI_HAALETANUD, POOLT, VASTU

log = logging.getLogger(__name__)

#: The network settles in 50-100 ms under constant drive, so the verdict is read from the
#: settled window only. The frames before it are the brain making up its mind and are
#: shown on screen, not scored.
SETTLE_SECONDS = 0.15

#: Zero-input |delta| on this graph, measured over seeds 0-9 (see `runs/noise_floor.json`
#: and FINDINGS.md). A race closer than this is not a decision.
DEAD_BAND_HZ = 1.0


@dataclass(frozen=True)
class Race:
    """The left/right descending race, frame by frame, and what it resolved to."""

    left_hz: np.ndarray  # (frames,) mean rate of the left pool in that frame
    right_hz: np.ndarray
    delta_hz: np.ndarray  # (frames,) right - left, the readout as it evolves
    delta: float  # the settled readout, averaged over the scored window
    settled_from: int  # first frame included in `delta`
    dead_band: float

    @property
    def supports_bill(self) -> bool | None:
        """Stance on the *bill*. None when the race stayed inside the noise floor."""
        if abs(self.delta) <= self.dead_band:
            return None
        return self.delta > 0

    def vote(self, inverted: bool) -> str:
        """The code the fly emits, given whether POOLT means killing the bill."""
        supports = self.supports_bill
        if supports is None:
            return EI_HAALETANUD
        return POOLT if supports != inverted else VASTU


def race(
    group_counts: dict[str, np.ndarray],
    sizes: dict[str, int],
    duration: float,
    dead_band: float = DEAD_BAND_HZ,
) -> Race:
    """Turn per-frame DN spike counts into the race and the settled readout.

    `group_counts` holds the `dn_left` / `dn_right` series from `sim.lif.Probes`; `sizes`
    the cell count of each pool, so the two sides are compared as rates rather than as
    counts and the 656/648 imbalance cannot masquerade as a decision.
    """
    left, right = group_counts["dn_left"], group_counts["dn_right"]
    frames = len(left)
    frame_seconds = duration / frames
    left_hz = left / (sizes["dn_left"] * frame_seconds)
    right_hz = right / (sizes["dn_right"] * frame_seconds)
    delta_hz = right_hz - left_hz

    settled_from = min(int(SETTLE_SECONDS / frame_seconds), frames - 1)
    return Race(
        left_hz=left_hz,
        right_hz=right_hz,
        delta_hz=delta_hz,
        delta=float(delta_hz[settled_from:].mean()),
        settled_from=settled_from,
        dead_band=dead_band,
    )
