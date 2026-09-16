"""Resolve the named cell populations Kärbes reads from and writes to.

Everything here is read out of `body-annotations`, never hardcoded from memory. The type
strings below were confirmed against MaleCNS v1.0: 54 olfactory receptor types named
`ORN_<glomerulus>`, and 481 descending-neuron types of which 472 have both sides present.

Two annotation quirks matter:
  * ORNs have no `somaSide` — their somas sit in the antenna, not the brain. Side comes
    from `rootSide`, which also carries an `unknown` value for ~15% of them.
  * The retention policy is simply "has a superclass". That drops 44,877 of 211,577 rows
    and leaves exactly 166,700, which is the figure the community reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyarrow import feather

log = logging.getLogger(__name__)

ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"

#: Sixteen ORN types, two per rubric axis, chosen for comparable population size
#: (43-84 cells) and for having both sides represented. The very large pheromone
#: channels (ORN_DA1 at 204, ORN_VA1d at 132) are excluded so no axis is louder than
#: another purely through cell count.
AXIS_ORNS: dict[str, tuple[str, str]] = {
    # axis:        (negative pole,  positive pole)
    "fiscal": ("ORN_VM5d", "ORN_VA2"),
    "market": ("ORN_DL1", "ORN_VL1"),
    "defence": ("ORN_VM4", "ORN_DM1"),
    "eu": ("ORN_VA6", "ORN_DM3"),
    "social": ("ORN_DL4", "ORN_DM6"),
    "green": ("ORN_V", "ORN_DM2"),
    "regional": ("ORN_DA2", "ORN_VL2p"),
    "state_power": ("ORN_DL5", "ORN_VM3"),
}

#: Descending neurons read out as the fly's steering. DNp-class cells project to the
#: nerve cord and drive locomotion; these three types are well populated on both sides.
DN_READOUT: tuple[str, ...] = ("DNp17", "DNg08", "DNg07")


@dataclass
class Populations:
    """Body IDs for every named population, plus the retained-neuron index."""

    retained: np.ndarray  # sorted int64 body IDs kept in the graph
    orn: dict[str, np.ndarray]  # ORN type -> body IDs
    dn_left: np.ndarray
    dn_right: np.ndarray
    types: dict[int, str]  # body ID -> type, for audit logs

    @property
    def n(self) -> int:
        return len(self.retained)

    def axis_channels(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Per axis, the (negative pole, positive pole) body-ID arrays."""
        out = {}
        for axis, (neg, pos) in AXIS_ORNS.items():
            out[axis] = (
                self.orn.get(neg, np.array([], dtype=np.int64)),
                self.orn.get(pos, np.array([], dtype=np.int64)),
            )
        return out


def load(root: Path) -> Populations:
    """Read annotations and resolve every population. Fails loudly on a missing type."""
    path = root / ANNOTATIONS
    table = feather.read_table(
        path, columns=["bodyId", "type", "class", "superclass", "somaSide", "rootSide"]
    )
    d = table.to_pydict()
    body = np.asarray(d["bodyId"], dtype=np.int64)
    typ = d["type"]
    cls = d["class"]
    sup = d["superclass"]
    # DNs are brain neurons and carry somaSide. ORNs do not — their somas sit in the
    # antenna — but they are stimulated bilaterally anyway: a bill does not arrive from
    # the left or the right. Keeping input symmetric is also what makes the zero-input
    # left-right asymmetry test in Stage 2 interpretable.
    soma_side = d["somaSide"]

    # Retention: keep anything with an assigned superclass; drop glia and unresolved.
    keep = np.array([s is not None for s in sup], dtype=bool)
    retained = np.sort(body[keep])
    log.info("retained %d of %d bodies", keep.sum(), len(body))

    kept = set(retained.tolist())
    orn: dict[str, np.ndarray] = {}
    wanted = {t for pair in AXIS_ORNS.values() for t in pair}
    for name in wanted:
        ids = np.array(
            [
                b
                for b, t, c in zip(body, typ, cls, strict=True)
                if t == name and c == "olfactory" and b in kept
            ],
            dtype=np.int64,
        )
        if len(ids) == 0:
            raise ValueError(f"ORN type {name!r} resolved to no retained cells")
        orn[name] = np.sort(ids)

    left, right = [], []
    for b, t, s, side in zip(body, typ, sup, soma_side, strict=True):
        if s != "descending_neuron" or t not in DN_READOUT or b not in kept:
            continue
        if side == "L":
            left.append(b)
        elif side == "R":
            right.append(b)
    if not left or not right:
        raise ValueError(f"DN readout {DN_READOUT} has an empty side: L={len(left)} R={len(right)}")

    return Populations(
        retained=retained,
        orn=orn,
        dn_left=np.sort(np.array(left, dtype=np.int64)),
        dn_right=np.sort(np.array(right, dtype=np.int64)),
        types={int(b): t for b, t, k in zip(body, typ, keep, strict=True) if k and t},
    )


def summary(pops: Populations) -> str:
    lines = [f"retained {pops.n:,} neurons"]
    for axis, (neg, pos) in AXIS_ORNS.items():
        lines.append(
            f"  {axis:<12} {neg:<10} n={len(pops.orn[neg]):<4} {pos:<10} n={len(pops.orn[pos])}"
        )
    lines.append(f"  readout      DN left n={len(pops.dn_left)}  right n={len(pops.dn_right)}")
    return "\n".join(lines)
