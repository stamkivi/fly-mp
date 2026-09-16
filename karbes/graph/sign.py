"""Excitatory / inhibitory sign per neuron, from transmitter predictions.

Sign is assigned **per presynaptic neuron**, not per edge. That is Dale's law, and it is
also what makes the rewiring control valid: shuffling edges cannot scramble the E/I
balance, because the sign travels with the sending cell rather than the connection.

Coverage on MaleCNS v1.0: 163,850 of 166,700 retained neurons resolve to a transmitter
(98.3%). The remaining 2,850 take an explicit fallback rather than being dropped or
silently treated as excitatory.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

import numpy as np
from pyarrow import feather

log = logging.getLogger(__name__)

NEUROTRANSMITTERS = "body-neurotransmitters-male-cns-v1.0.feather"

EXCITATORY = frozenset({"acetylcholine"})
INHIBITORY = frozenset({"gaba", "glutamate", "histamine"})
#: Modulators act on slow timescales and are not fast synaptic drive. They are recorded
#: but contribute no sign; modelling them as excitation would be wrong.
MODULATORY = frozenset({"dopamine", "serotonin", "octopamine"})

#: What an unresolved neuron becomes. Acetylcholine is 64% of resolved cells, so
#: excitatory is the maximum-likelihood guess — but it is a guess, it is counted, and
#: it is a parameter so a control can flip it.
UNKNOWN_SIGN = 1.0


def per_neuron_transmitter(root) -> dict[int, str]:
    """Modal clear `consensus_nt` per body, falling back to the cell-type prediction."""
    table = feather.read_table(
        root / NEUROTRANSMITTERS,
        columns=["body", "consensus_nt", "celltype_predicted_nt"],
    )
    d = table.to_pydict()
    votes: dict[int, Counter] = defaultdict(Counter)
    for b, nt in zip(d["body"], d["consensus_nt"], strict=True):
        if nt and nt != "unclear":
            votes[b][nt] += 1
    resolved = {b: c.most_common(1)[0][0] for b, c in votes.items()}
    for b, nt in zip(d["body"], d["celltype_predicted_nt"], strict=True):
        if nt and nt != "unclear":
            resolved.setdefault(b, nt)
    return resolved


def signs(root, retained: np.ndarray, unknown: float = UNKNOWN_SIGN) -> tuple[np.ndarray, dict]:
    """Return a sign per retained neuron, aligned to `retained`, plus a coverage report."""
    nt = per_neuron_transmitter(root)
    out = np.empty(len(retained), dtype=np.float32)
    stats = Counter()
    for i, body in enumerate(retained.tolist()):
        t = nt.get(body)
        if t in EXCITATORY:
            out[i] = 1.0
            stats["excitatory"] += 1
        elif t in INHIBITORY:
            out[i] = -1.0
            stats["inhibitory"] += 1
        elif t in MODULATORY:
            # No fast drive. Excluded from synaptic transmission entirely.
            out[i] = 0.0
            stats["modulatory"] += 1
        else:
            out[i] = unknown
            stats["unknown"] += 1
    report = {
        **stats,
        "coverage": round(1 - stats["unknown"] / max(len(retained), 1), 4),
        "unknown_assigned": unknown,
    }
    log.info(
        "signs: %d excitatory, %d inhibitory, %d modulatory (silent), %d unknown -> %+.0f",
        stats["excitatory"],
        stats["inhibitory"],
        stats["modulatory"],
        stats["unknown"],
        unknown,
    )
    return out, report
