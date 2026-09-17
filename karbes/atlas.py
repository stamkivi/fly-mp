"""The soma atlas: a sample of the real 3-D cell-body positions, for the brain on screen.

139,662 of the 166,700 retained neurons carry a real `somaLocation` in the annotations, so
the brain the page draws is the actual fly brain rather than a schematic. The full set is
under 1 MB quantised; a ~16,000-cell sample is ~112 KB, which is what ships.

**The sample is stratified, and the page has to say so.** Optic-lobe neurons are 65% of
all located somas, so a uniform sample would draw two enormous eyes, a thin central brain
and a nerve cord of barely 1,500 points — and would put roughly 150 descending neurons on
screen when the descending pool *is* the readout. Allocation is therefore proportional to
the square root of each group's size, with every descending neuron kept. Relative density
on screen is a sampling decision, not anatomy.

Coordinates are MaleCNS voxel indices at 8 nm. They are quantised to uint16 on a single
shared scale, so the brain keeps its proportions instead of being stretched per axis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyarrow import feather

from karbes.graph.populations import ANNOTATIONS

log = logging.getLogger(__name__)

COMPILED = "atlas-malecns-v1.0.npz"
DEFAULT_SAMPLE = 16_000
VOXEL_NM = 8

#: Superclasses collapsed into the groups the page labels. Anything unlisted is dropped
#: rather than silently bucketed — there are 12 such cells and they are not worth a lie.
GROUPS: dict[str, tuple[str, ...]] = {
    "optic": (
        "ol_intrinsic",
        "visual_projection",
        "visual_centrifugal",
        "ol_sensory",
        "visual_projection_tbc",
    ),
    "central": ("cb_intrinsic", "cb_motor", "cb_endocrine", "cb_efferent", "ENS"),
    "cord": (
        "vnc_intrinsic",
        "vnc_motor",
        "vnc_efferent",
        "vnc_endocrine",
        "vnc_sensory",
        "vnc_tbc",
    ),
    "ascending": ("ascending_neuron", "efferent_ascending"),
    "descending": ("descending_neuron", "efferent_descending"),
}

#: Kept whole: this is the pool the vote is read from, and it has to be visible.
KEEP_ALL = ("descending",)

GROUP_NAMES: tuple[str, ...] = tuple(GROUPS)


@dataclass
class Atlas:
    """A sampled, quantised set of real soma positions."""

    bodies: np.ndarray  # (k,) int64 body IDs — real, and joinable back to annotations
    xyz: np.ndarray  # (k, 3) uint16, shared scale
    group: np.ndarray  # (k,) uint8 index into GROUP_NAMES
    origin: np.ndarray  # (3,) int64 voxel coordinate of quantised zero
    scale: float  # voxels per quantisation step
    population: dict[str, int]  # group -> how many such neurons exist in the annotations

    @property
    def k(self) -> int:
        return len(self.bodies)

    def group_names(self) -> tuple[str, ...]:
        return GROUP_NAMES

    def fractions(self) -> dict[str, float]:
        """Share of each group actually sampled. The page states these."""
        counts = np.bincount(self.group, minlength=len(GROUP_NAMES))
        return {
            name: float(counts[i]) / self.population[name] for i, name in enumerate(GROUP_NAMES)
        }

    def web_bytes(self) -> bytes:
        """The page-facing blob: xyz as uint16 little-endian, then one uint8 group each."""
        return self.xyz.astype("<u2").tobytes() + self.group.astype(np.uint8).tobytes()


def _allocate(sizes: dict[str, int], total: int) -> dict[str, int]:
    """Square-root stratification, with `KEEP_ALL` groups taken whole first."""
    quota = {name: sizes[name] for name in KEEP_ALL}
    remaining = total - sum(quota.values())
    rest = {n: s for n, s in sizes.items() if n not in quota}
    weights = {n: float(np.sqrt(s)) for n, s in rest.items()}
    scale = remaining / sum(weights.values())
    for name, w in weights.items():
        quota[name] = min(rest[name], round(w * scale))
    return quota


def build(root: Path, sample: int = DEFAULT_SAMPLE, seed: int = 0) -> Atlas:
    """Read the annotations and draw the sample. Deterministic given `seed`."""
    table = feather.read_table(root / ANNOTATIONS, columns=["bodyId", "superclass", "somaLocation"])
    d = table.to_pydict()

    of_group = {sup: name for name, sups in GROUPS.items() for sup in sups}
    bodies_by_group: dict[str, list[int]] = {name: [] for name in GROUP_NAMES}
    coords_by_group: dict[str, list[list[int]]] = {name: [] for name in GROUP_NAMES}
    for body, sup, loc in zip(d["bodyId"], d["superclass"], d["somaLocation"], strict=True):
        name = of_group.get(sup)
        if name is None or loc is None:
            continue
        bodies_by_group[name].append(body)
        coords_by_group[name].append(loc)

    population = {name: len(v) for name, v in bodies_by_group.items()}
    log.info("located somas by group: %s", population)
    quota = _allocate(population, sample)

    rng = np.random.default_rng(seed)
    bodies, coords, groups = [], [], []
    for gid, name in enumerate(GROUP_NAMES):
        pool = np.asarray(bodies_by_group[name], dtype=np.int64)
        xyz = np.asarray(coords_by_group[name], dtype=np.int64)
        take = quota[name]
        pick = np.sort(rng.choice(len(pool), size=take, replace=False))
        bodies.append(pool[pick])
        coords.append(xyz[pick])
        groups.append(np.full(take, gid, dtype=np.uint8))

    bodies = np.concatenate(bodies)
    coords = np.concatenate(coords)
    groups = np.concatenate(groups)

    # One scale for all three axes, so the brain keeps its proportions.
    origin = coords.min(axis=0)
    scale = float((coords - origin).max()) / np.iinfo(np.uint16).max
    quantised = np.rint((coords - origin) / scale).astype(np.uint16)

    log.info(
        "atlas: %d somas of %d located, extent %s voxels",
        len(bodies),
        sum(population.values()),
        (coords.max(axis=0) - origin).tolist(),
    )
    return Atlas(
        bodies=bodies,
        xyz=quantised,
        group=groups,
        origin=origin,
        scale=scale,
        population=population,
    )


def save(atlas: Atlas, root: Path) -> Path:
    out = root / COMPILED
    np.savez(
        out,
        bodies=atlas.bodies,
        xyz=atlas.xyz,
        group=atlas.group,
        origin=atlas.origin,
        scale=atlas.scale,
        population_names=np.array(list(atlas.population), dtype=object),
        population_counts=np.array(list(atlas.population.values()), dtype=np.int64),
    )
    return out


def load(root: Path) -> Atlas | None:
    out = root / COMPILED
    if not out.exists():
        return None
    z = np.load(out, allow_pickle=True)
    return Atlas(
        bodies=z["bodies"],
        xyz=z["xyz"],
        group=z["group"],
        origin=z["origin"],
        scale=float(z["scale"]),
        population=dict(
            zip(z["population_names"].tolist(), z["population_counts"].tolist(), strict=True)
        ),
    )
