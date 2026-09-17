"""Topic scores to currents into named ORN populations.

Three properties of this mapping matter more than its details, and all three are fixed
before any agreement with the chamber is measured:

1. **It is engineered, not discovered.** No glomerulus in a fly means "taxes". The
   channel-to-ORN assignment in `graph.populations.CHANNEL_ORNS` is arbitrary and fixed;
   this module only decides how hard each one is driven.
2. **Drive is weighted by confidence.** A channel Jev could not read drives the fly
   weakly rather than driving it with noise dressed as signal. That is the whole reason
   Jev replaced the LLM rubric, so it has to show up here and not just in the JSON.
3. **Nothing here is tuned against an outcome.** The rates below are pre-registered: they
   place drive inside the 5-200 Hz range ORNs are measured to fire in, and that is their
   entire justification.

Rates cannot be negative, so each channel is a pole pair: a positive score drives the
positive-pole population and a negative score the negative one, both poles idling at a
background rate so a score of zero is symmetric rather than silent.
"""

from __future__ import annotations

import logging

import numpy as np

from karbes.graph.load import Graph
from karbes.graph.populations import CHANNEL_ORNS, Populations
from karbes.score.jev import Scored

log = logging.getLogger(__name__)

#: Spontaneous background on every ORN population, driven or not. Keeps a zero score
#: symmetric across the pole pair instead of silencing both sides of it.
BACKGROUND_HZ = 5.0

#: Peak additional drive on the active pole at |score x confidence| == 1 and full
#: salience. 5 + 95 lands at the top of the measured ORN range without exceeding it.
PEAK_HZ = 95.0

#: Salience scales the stimulus, never the background. A housekeeping bill still smells
#: of something; it just does not shout. The floor keeps a low-salience bill legible on
#: screen rather than indistinguishable from baseline.
SALIENCE_FLOOR = 0.25


def salience_gain(salience: float) -> float:
    """Map Jev's [0, 1] salience onto the stimulus multiplier."""
    return SALIENCE_FLOOR + (1.0 - SALIENCE_FLOOR) * float(np.clip(salience, 0.0, 1.0))


def channel_drive(scored: Scored) -> dict[str, float]:
    """Per channel, the signed drive in [-1, +1] that the fly actually receives.

    This is `score x confidence x salience gain` — the number the page draws as bar
    length, so what is on screen is what went into the neurons.
    """
    gain = salience_gain(scored.scores.get("salience", 0.0))
    return {
        channel: float(np.clip(scored.drive_weight(channel), -1.0, 1.0)) * gain
        for channel in CHANNEL_ORNS
    }


def orn_rates(scored: Scored, pops: Populations) -> dict[str, float]:
    """Per ORN *type*, the per-neuron input rate in Hz.

    Rates are normalised by population size against the mean, so a channel does not get
    weight purely from having more cells. Sizes span 43-84, so the correction stays
    inside 0.7-1.4x and every rate remains inside the measured ORN range.
    """
    sizes = {name: len(ids) for name, ids in pops.orn.items()}
    mean_size = float(np.mean(list(sizes.values())))

    rates: dict[str, float] = {}
    for channel, signed in channel_drive(scored).items():
        neg, pos = CHANNEL_ORNS[channel]
        active, quiet = (pos, neg) if signed >= 0 else (neg, pos)
        rates[active] = BACKGROUND_HZ + PEAK_HZ * abs(signed)
        rates[quiet] = BACKGROUND_HZ
    return {name: hz * mean_size / sizes[name] for name, hz in rates.items()}


def drive(scored: Scored, pops: Populations, graph: Graph) -> dict[int, float]:
    """The kernel's `drive` argument: graph index -> input rate in Hz.

    Bilateral by construction. ORN somas sit in the antenna and carry no `somaSide`, and
    a bill does not arrive from the left or the right — keeping the input symmetric is
    also what makes the zero-input left-right asymmetry floor interpretable.
    """
    out: dict[int, float] = {}
    for name, hz in orn_rates(scored, pops).items():
        for index in graph.index_of(pops.orn[name]):
            out[int(index)] = hz
    return out
