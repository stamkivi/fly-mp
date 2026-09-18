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
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyarrow import feather

log = logging.getLogger(__name__)

ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"

#: One glomerulus per rubric channel, ten in all.
#:
#: **The pole pair is gone.** It existed because firing rates cannot be negative, so each
#: channel needed a glomerulus for each direction. Since the *side* now carries the sign —
#: a positive score drives the right antenna harder — one population per channel is enough,
#: and the pair had stopped meaning anything.
#:
#: Chosen for balanced `rootSide` counts (L/R between 0.72 and 1.21) and comparable size
#: (41-76 cells), so no channel is louder than another through cell count, and neither
#: antenna is louder through annotation asymmetry. The large pheromone channels (ORN_DA1 at
#: 204, ORN_VA1d at 132) stay excluded.
#:
#: **The channel-to-glomerulus assignment is arbitrary and fixed, not discovered.** No
#: glomerulus in a fly means "healthcare". Channels are in `rubric3.KEYS` order against
#: glomeruli in a fixed list; it is never re-drawn to improve a result.
#: `test_channel_keys_track_the_rubric` fails if the rubric and this table drift apart.
CHANNEL_ORNS: dict[str, str] = {
    "cost_of_living": "ORN_DM1",
    "healthcare": "ORN_DL1",
    "defence": "ORN_VA2",
    "social": "ORN_VA6",
    "taxes": "ORN_DM2",
    "education": "ORN_VM5d",
    "wages": "ORN_DM3",
    "energy": "ORN_DM6",
    "business": "ORN_DA2",
    "immigration": "ORN_DL5",
}

DN_SUPERCLASS = "descending_neuron"

#: The steering readout: the **DNa family**, 15 types with 16 cells on each side.
#:
#: Reading all 1,304 lateralised descending neurons was wrong, and measurably so. It was
#: adopted because a hand-picked 51 gave a zero-input left-minus-right asymmetry of
#: -4.577 Hz, and widening the pool drove that to +0.011 Hz. That suppressed the symptom
#: by averaging the signal away with it. `TheMrRaGe/flybrain` scores the three options on
#: this same connectome: DNa02 alone d' 1.11, the **DNa family d' 4.21**, and all 1,310
#: descending neurons **d' -1.70 — significant with the wrong sign**, because a whole-
#: population average "tracks residual asymmetry, not steering".
#:
#: The biology is specific rather than a guess: rotational velocity in walking flies
#: tracks the left-right firing difference of DNa01/DNa02, near-linearly across the
#: dynamic range (Rayshubskiy et al., *Cell* 2024).
DNA_FAMILY = re.compile(r"DNa\d+")

#: The visual motion detectors, and the entry point for the *procedural* sense.
#:
#: **Not the photoreceptors.** All 6,098 are histaminergic, and this pack keeps only
#: acetylcholine, GABA and glutamate as presynaptic sources, so every photoreceptor has
#: zero outgoing edges and driving one is a no-op. T4 and T5 are cholinergic, live, and
#: 13,580 cells — thirteen times the olfactory input surface. Driving them asymmetrically
#: by eye moves the DNa turn index with d' 9.67 against olfaction's 2.63.
T4T5 = re.compile(r"T[45][a-d]")

#: Looming. LC4 (6,362 contacts) and LPLC2 (4,862) drive DNp01 monosynaptically — the
#: published giant-fibre escape circuit, onto exactly two cells. Silent at rest and
#: saturating by 150 Hz, so it is an all-or-nothing alarm rather than a graded readout.
LOOMING_TYPES = ("LC4", "LPLC2")
GIANT_FIBRE = "DNp01"


@dataclass
class Populations:
    """Body IDs for every named population, plus the retained-neuron index."""

    retained: np.ndarray  # sorted int64 body IDs kept in the graph
    orn: dict[str, np.ndarray]  # ORN type -> body IDs
    dn_left: np.ndarray  # every lateralised descending neuron, kept for audit only
    dn_right: np.ndarray
    dna_left: np.ndarray  # the DNa family — this is what the vote is read from
    dna_right: np.ndarray
    orn_left: np.ndarray  # ORNs by rootSide; a bill arrives on one side or the other
    orn_right: np.ndarray
    t4t5_left: np.ndarray  # visual motion detectors, the procedural sense
    t4t5_right: np.ndarray
    looming: np.ndarray  # LC4 + LPLC2, into the giant fibre
    giant_fibre: np.ndarray  # DNp01, two cells
    types: dict[int, str]  # body ID -> type, for audit logs

    @property
    def n(self) -> int:
        return len(self.retained)

    def channels(self) -> dict[str, np.ndarray]:
        """Per channel, the body IDs of its glomerulus."""
        return {
            channel: self.orn.get(name, np.array([], dtype=np.int64))
            for channel, name in CHANNEL_ORNS.items()
        }


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
    # Descending neurons are brain cells and carry `somaSide`. ORNs carry none at all —
    # every one of the 2,635 has `somaSide` None, because their somas sit in the antenna —
    # so their laterality comes from `rootSide`, which resolves 883 left and 1,343 right
    # and leaves 409 unknown.
    #
    # **Sensory laterality is load-bearing, not a detail.** Driving the antennae
    # symmetrically and then reading a left-minus-right difference cannot work: a
    # symmetric stimulus has no reason to move an antisymmetric statistic. flybrain
    # measured exactly that on this connectome — with laterality taken from `somaSide`
    # the "turn response to stimulus left vs right was 0.0000, identical to four
    # decimals". Unknown-rootSide ORNs are dropped rather than assigned a side.
    soma_side = d["somaSide"]
    root_side = d["rootSide"]

    # Retention: keep anything with an assigned superclass; drop glia and unresolved.
    keep = np.array([s is not None for s in sup], dtype=bool)
    retained = np.sort(body[keep])
    log.info("retained %d of %d bodies", keep.sum(), len(body))

    kept = set(retained.tolist())
    orn: dict[str, np.ndarray] = {}
    wanted = set(CHANNEL_ORNS.values())
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
    for b, s, side in zip(body, sup, soma_side, strict=True):
        if s != DN_SUPERCLASS or b not in kept:
            continue
        if side == "L":
            left.append(b)
        elif side == "R":
            right.append(b)
    if not left or not right:
        raise ValueError(f"DN readout has an empty side: L={len(left)} R={len(right)}")
    log.info(
        "readout: %d descending neurons (L %d / R %d)",
        len(left) + len(right),
        len(left),
        len(right),
    )

    dna: dict[str, list[int]] = {"L": [], "R": []}
    for b, ty, cls_sup, side in zip(body, typ, sup, soma_side, strict=True):
        if (
            cls_sup == DN_SUPERCLASS
            and ty
            and DNA_FAMILY.fullmatch(ty)
            and side in dna
            and b in kept
        ):
            dna[side].append(b)
    if not dna["L"] or not dna["R"]:
        raise ValueError(f"DNa readout has an empty side: {len(dna['L'])}/{len(dna['R'])}")

    orn_side: dict[str, list[int]] = {"L": [], "R": []}
    for b, ty, c, side in zip(body, typ, cls, root_side, strict=True):
        if c == "olfactory" and ty in wanted and b in kept and side in orn_side:
            orn_side[side].append(b)

    vis: dict[str, list[int]] = {"L": [], "R": []}
    looming, giant = [], []
    for b, ty, cls_sup, side in zip(body, typ, sup, soma_side, strict=True):
        if b not in kept or not ty:
            continue
        if T4T5.fullmatch(ty) and side in vis:
            vis[side].append(b)
        elif ty in LOOMING_TYPES:
            looming.append(b)
        elif ty == GIANT_FIBRE:
            giant.append(b)
    if not looming or not giant:
        raise ValueError(f"looming {len(looming)} / giant fibre {len(giant)} cells resolved")

    log.info(
        "vision: T4/T5 L %d / R %d   looming %d -> giant fibre %d",
        len(vis["L"]),
        len(vis["R"]),
        len(looming),
        len(giant),
    )
    log.info(
        "readout: DNa family L %d / R %d   drive: ORN rootSide L %d / R %d",
        len(dna["L"]),
        len(dna["R"]),
        len(orn_side["L"]),
        len(orn_side["R"]),
    )
    return Populations(
        retained=retained,
        orn=orn,
        dn_left=np.sort(np.array(left, dtype=np.int64)),
        dn_right=np.sort(np.array(right, dtype=np.int64)),
        dna_left=np.sort(np.array(dna["L"], dtype=np.int64)),
        dna_right=np.sort(np.array(dna["R"], dtype=np.int64)),
        orn_left=np.sort(np.array(orn_side["L"], dtype=np.int64)),
        orn_right=np.sort(np.array(orn_side["R"], dtype=np.int64)),
        t4t5_left=np.sort(np.array(vis["L"], dtype=np.int64)),
        t4t5_right=np.sort(np.array(vis["R"], dtype=np.int64)),
        looming=np.sort(np.array(looming, dtype=np.int64)),
        giant_fibre=np.sort(np.array(giant, dtype=np.int64)),
        types={int(b): t for b, t, k in zip(body, typ, keep, strict=True) if k and t},
    )


def summary(pops: Populations) -> str:
    lines = [f"retained {pops.n:,} neurons"]
    for channel, name in CHANNEL_ORNS.items():
        lines.append(f"  {channel:<15} {name:<10} n={len(pops.orn[name])}")
    lines.append(f"  drive        ORN rootSide L n={len(pops.orn_left)} R n={len(pops.orn_right)}")
    lines.append(f"  vision       T4/T5       L n={len(pops.t4t5_left)} R n={len(pops.t4t5_right)}")
    lines.append(f"  alarm        looming n={len(pops.looming)} -> DNp01 n={len(pops.giant_fibre)}")
    lines.append(f"  readout      DNa family  L n={len(pops.dna_left)} R n={len(pops.dna_right)}")
    lines.append(f"  (audit only) all DNs     L n={len(pops.dn_left)} R n={len(pops.dn_right)}")
    return "\n".join(lines)
