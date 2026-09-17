"""Descending-neuron activity to a vote.

`turn = (R - L) / (R + L)` over the **DNa family**, with the symmetric-stimulus baseline
subtracted. Every part of that is taken from the published work rather than invented here:

* **Which cells.** Rotational velocity in walking flies tracks the left-right firing
  difference of DNa01/DNa02, near-linearly across the dynamic range (Rayshubskiy et al.,
  *Cell* 2024). flybrain scores the readouts on this connectome — DNa02 alone d' 1.11, the
  DNa family **d' 4.21**, all 1,310 descending neurons **d' -1.70, wrong-signed**, because
  a whole-population average "tracks residual asymmetry, not steering".
* **The statistic.** A normalised ratio, not a raw rate difference, so it does not move
  with overall excitability.
* **The baseline.** The left/right bias under a symmetric stimulus is large and must be
  subtracted — measured here at about -0.11, against a stimulus effect of ~0.38.

Still an engineered interface, and labelled as one: a fly steers, it does not vote. Which
side means "for" was fixed arbitrarily before any agreement with the chamber was measured.

The rejection-motion flip lives here and only here, so every control arm inherits it
identically. On a `Tagasi lukkamine` motion, supporting the bill means voting VASTU.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from karbes.riigikogu.model import EI_HAALETANUD, POOLT, VASTU

log = logging.getLogger(__name__)

#: Fallback dead band on the baseline-subtracted turn index. The real one is measured by
#: `karbes calibrate` from the spread across input phases and read from the run manifest.
DEAD_BAND = 0.25


@dataclass(frozen=True)
class Turn:
    """The DNa steering readout for one run."""

    left_spikes: int
    right_spikes: int
    baseline: float  # turn index under a symmetric stimulus, subtracted below
    dead_band: float

    @property
    def raw(self) -> float:
        total = self.left_spikes + self.right_spikes
        return (self.right_spikes - self.left_spikes) / total if total else float("nan")

    @property
    def turn(self) -> float:
        """Baseline-subtracted turn index. This is the readout."""
        return self.raw - self.baseline

    @property
    def supports_bill(self) -> bool | None:
        """Stance on the *bill*. None when the turn stayed inside the dead band."""
        t = self.turn
        if not np.isfinite(t) or abs(t) <= self.dead_band:
            return None
        return t > 0

    def vote(self, inverted: bool) -> str:
        """The code the fly emits, given whether POOLT means killing the bill."""
        supports = self.supports_bill
        if supports is None:
            return EI_HAALETANUD
        return POOLT if supports != inverted else VASTU


def turn_index(
    counts: np.ndarray,
    dna_left: np.ndarray,
    dna_right: np.ndarray,
    baseline: float = 0.0,
    dead_band: float = DEAD_BAND,
) -> Turn:
    """Read the DNa family out of a per-neuron spike-count vector."""
    return Turn(
        left_spikes=int(counts[dna_left].sum()),
        right_spikes=int(counts[dna_right].sum()),
        baseline=baseline,
        dead_band=dead_band,
    )
