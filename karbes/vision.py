"""The procedural sense: who tabled the bill, as something the fly can see.

**Why vision carries this and olfaction carries substance.** §T5 measured that one bit —
government-tabled or not — moves faction prediction from the ~.74 content ceiling to ~.90,
and re-measured on 565 contested votes it alone calls 94.2% of outcomes against a 52.6%
baseline: government bills advance 99.3% of the time, member bills 10.4%. The Jev rubric is
initiator-blind by construction (`rubric2.bill_prompt` never sees it), so routing the bit
through a second sense adds genuinely new information rather than laundering the first.

Two visual channels, both entering below the retina:

* **Optic flow → steering.** The bit sets which eye sees more motion. T4/T5 are the
  cholinergic directionally-selective motion detectors — 13,580 cells, thirteen times the
  olfactory input surface — and reach the DNa steering pool through the lobula plate and
  HS/VS. Driving them asymmetrically moves the turn index with **d' 9.67**, against
  olfaction's 2.63.
* **Looming → escape.** Salience drives LC4 and LPLC2, which synapse monosynaptically onto
  the two DNp01 giant-fibre cells. Silent at rest and saturated by 150 Hz, so this is an
  alarm rather than a readout: past a threshold the fly bolts and does not vote at all.

Photoreceptors are deliberately not touched. All 6,098 are histaminergic and this pack keeps
only ACh, GABA and glutamate as presynaptic sources, so every one of them has zero outgoing
edges. Driving the retina is a no-op; the motion detectors are where vision starts here.

The mapping is engineered and labelled as such. No fly has an opinion about who tabled a
bill, and which eye means "government" was fixed arbitrarily before any agreement was
measured.
"""

from __future__ import annotations

import logging

import numpy as np

from karbes.engine import Engine
from karbes.graph.populations import Populations
from karbes.riigikogu.model import Bill

log = logging.getLogger(__name__)

#: Background optic flow on both eyes: the world is never perfectly still.
FLOW_BACKGROUND_HZ = 4.0

#: Additional flow on the leading eye. The bit is binary, so this is all-or-nothing.
FLOW_PEAK_HZ = 46.0

#: Salience below this looms at nothing. Real members abstain rarely, so escape has to be
#: rare, and the giant fibre goes from 0 to 117 spikes between 0 and 5 Hz of drive — there
#: is no gentle part of this curve to sit on.
LOOM_THRESHOLD = 0.85
LOOM_PEAK_HZ = 40.0

#: Spikes from the two DNp01 cells above which the fly is taken to have bolted.
ESCAPE_SPIKES = 60


def looming_hz(salience: float) -> float:
    """Drive onto LC4 and LPLC2 for a bill of this salience."""
    over = (float(salience) - LOOM_THRESHOLD) / (1.0 - LOOM_THRESHOLD)
    return max(0.0, min(1.0, over)) * LOOM_PEAK_HZ


def flow(bill: Bill) -> float:
    """Signed optic flow in [-1, +1]. Positive leads the right eye.

    A government bill and a member's bill are the two poles. The assignment of which eye
    means which is arbitrary and fixed, exactly like the channel-to-glomerulus pairing.
    """
    return 1.0 if bill.government_bill else -1.0


def stimulus(
    bill: Bill, salience: float, pops: Populations, engine: Engine
) -> tuple[np.ndarray, np.ndarray]:
    """`(targets, rates_hz)` for the visual channels of one bill.

    Per-eye rates are normalised by that eye's cell count, so the 6,787/6,793 split cannot
    itself act as a stimulus.
    """
    left = engine.positions(pops.t4t5_left)
    right = engine.positions(pops.t4t5_right)
    loom = engine.positions(pops.looming)
    signed = flow(bill)
    mean_n = (len(left) + len(right)) / 2

    targets = np.concatenate([left, right, loom])
    rates = np.concatenate(
        [
            np.full(len(left), (FLOW_BACKGROUND_HZ + FLOW_PEAK_HZ * max(-signed, 0.0)) * mean_n / len(left)),
            np.full(len(right), (FLOW_BACKGROUND_HZ + FLOW_PEAK_HZ * max(signed, 0.0)) * mean_n / len(right)),
            np.full(len(loom), looming_hz(salience)),
        ]
    )
    order = np.argsort(targets)
    return targets[order].astype(np.int32), rates[order]


def bolted(counts: np.ndarray, giant_fibre: np.ndarray) -> tuple[bool, int]:
    """Did the giant fibre fire hard enough that the fly left the tabulaator?"""
    spikes = int(counts[giant_fibre].sum())
    return spikes >= ESCAPE_SPIKES, spikes
