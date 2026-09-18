"""Topic scores to lateralised olfactory drive.

**The side carries the sign.** Scores are signed and firing rates are not, so the earlier
encoder gave each channel a pole pair — one glomerulus for negative, one for positive — and
drove both antennae identically. That was incompatible with a left-minus-right readout by
construction: a bilaterally symmetric stimulus has no reason to move an antisymmetric
statistic, and flybrain measured exactly that on this connectome, a turn response to a
left-vs-right stimulus of "0.0000, identical to four decimals". One glomerulus per channel
is enough once the side carries the sign.

So a positive score now drives the **right** antenna harder and a negative score the left,
which is a stimulus the steering circuit is actually built to resolve. Two consequences:

* Laterality comes from `rootSide`, the only side ORNs carry. The 409 whose rootSide is
  unknown are dropped rather than guessed.

Three properties are fixed before any agreement with the chamber is measured, as before:
the mapping is engineered rather than discovered, drive is weighted by Jev's confidence so
an unreadable channel drives weakly, and no rate here is tuned against an outcome.
"""

from __future__ import annotations

import logging

import numpy as np

from karbes.engine import Engine
from karbes.graph.populations import CHANNEL_ORNS, Populations
from karbes.score.jev import Scored

log = logging.getLogger(__name__)

#: Background on every driven ORN. A channel scored zero leaves its glomerulus at this on
#: both sides, so zero is symmetric rather than silent.
BACKGROUND_HZ = 15.0

#: Additional drive on the leading side at |score x confidence| == 1 and full salience.
#: 150 Hz is the published default input rate for this model.
PEAK_HZ = 135.0

#: Salience scales the stimulus, never the background.
SALIENCE_FLOOR = 0.25


def salience_gain(salience: float) -> float:
    return SALIENCE_FLOOR + (1.0 - SALIENCE_FLOOR) * float(np.clip(salience, 0.0, 1.0))


def channel_drive(scored: Scored) -> dict[str, float]:
    """Per channel, the signed drive in [-1, +1]: positive leads right, negative left.

    This is `score x confidence x salience gain` — the number the page draws as bar
    length, so what is on screen is what reached the antennae.
    """
    gain = salience_gain(scored.scores.get("salience", 0.0))
    return {
        channel: float(np.clip(scored.drive_weight(channel), -1.0, 1.0)) * gain
        for channel in CHANNEL_ORNS
    }


def stimulus(scored: Scored, pops: Populations, engine: Engine) -> tuple[np.ndarray, np.ndarray]:
    """Return `(targets, rates_hz)` for `engine.run`, one entry per driven ORN.

    Per-side rates are normalised by that side's cell count, so the 363/525 rootSide
    imbalance does not itself act as a permanent stimulus. What is equalised is the drive
    delivered to each antenna, not the rate delivered to each cell.
    """
    drive = channel_drive(scored)
    left = set(pops.orn_left.tolist())
    right = set(pops.orn_right.tolist())

    bodies: list[int] = []
    rates: list[float] = []
    for channel, signed in drive.items():
        name = CHANNEL_ORNS[channel]
        ids = pops.orn[name]
        side_ids = {
            "L": [b for b in ids.tolist() if b in left],
            "R": [b for b in ids.tolist() if b in right],
        }
        n_l, n_r = len(side_ids["L"]), len(side_ids["R"])
        if not n_l or not n_r:
            raise ValueError(f"ORN type {name!r} has an empty side: L={n_l} R={n_r}")
        mean_n = (n_l + n_r) / 2
        hz = {
            "R": (BACKGROUND_HZ + PEAK_HZ * max(signed, 0.0)) * mean_n / n_r,
            "L": (BACKGROUND_HZ + PEAK_HZ * max(-signed, 0.0)) * mean_n / n_l,
        }
        for side in ("L", "R"):
            bodies.extend(side_ids[side])
            rates.extend([hz[side]] * len(side_ids[side]))

    order = np.argsort(np.asarray(bodies))
    ordered = np.asarray(bodies)[order]
    targets = engine.positions(ordered)
    if len(targets) != len(ordered):
        raise ValueError("an ORN body is missing from the engine pack")
    return targets, np.asarray(rates)[order]
