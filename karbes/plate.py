"""Render the connectome as a confocal plate, from the real cell-body coordinates.

The brain on the page was a set of coloured density blobs. That is a diagram, and it reads
as one. This renders the same 139,662 real soma positions the way a fly brain is actually
*photographed*: a dorsal view, accumulated through depth, tone-mapped, bloomed and grained,
so the picture has the shape and the texture of a specimen rather than of a chart.

The imaging metaphor is not decoration, it is the honest one. A nuclear counterstain (DAPI)
of a *Drosophila* CNS shows precisely what this file has — cell bodies, which sit in a rind
around the neuropil — so a soma cloud rendered as fluorescence is a faithful likeness of a
real preparation rather than a stylisation of one. The second channel plays the part of a
driver line: the populations this project actually drives and reads, labelled over the
counterstain, which is how such a figure is composed in the literature.

Nothing here is registered to anyone else's image. Every point is a MaleCNS v1.0
`somaLocation` at 8 nm, projected orthographically. Depth attenuation and bloom are optical
effects applied to real coordinates, not invented structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

WIDTH = 1500  # final plate width in px; height follows the brain's aspect
SUPERSAMPLE = 2
MARGIN = 0.03

#: Counterstain and driver-line colours, linear RGB. Cool cyan-white against warm magenta
#: is the standard two-channel pairing and survives being printed.
COUNTERSTAIN = np.array([0.42, 0.72, 1.00])
DRIVER = np.array([1.00, 0.30, 0.62])

SPLAT = 1.35  # soma radius in supersampled px, before depth
BLOOM_SIGMA = 9.0
BLOOM_GAIN = 0.55
GRAIN = 0.010
EXPOSURE = 3.2

#: How far a cell dims with depth. Real attenuation through a 100 um preparation is far
#: stronger than this, but a faithful falloff loses the ventral nerve cord entirely, so the
#: cue is kept as form-giving rather than photometric and the page says so.
DEPTH_FLOOR = 0.42

#: Above this fraction of the dynamic range a fluorophore reads white rather than coloured.
#: Without it the densest rind stays saturated blue, which no real plate does.
WHITE_KNEE = 0.62


@dataclass
class Plate:
    rgb: np.ndarray  # (h, w, 3) float in [0, 1]
    bounds: tuple[float, float, float, float]  # minX, maxX, minZ, maxZ in voxels
    n_counterstain: int
    n_driver: int

    def png(self, path: Path) -> Path:
        from PIL import Image

        img = (np.clip(self.rgb, 0, 1) * 255).astype(np.uint8)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img).save(path, optimize=True)
        return path


def _splat(xy: np.ndarray, depth: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Accumulate points into a float image, dimmer with depth, with a soft footprint.

    Bilinear deposition rather than nearest, then one small blur: at 139,662 points a
    per-point Gaussian costs minutes and looks identical to depositing sharp and blurring
    once, because every footprint is the same size.
    """
    from scipy.ndimage import gaussian_filter

    h, w = shape
    buf = np.zeros((h, w), dtype=np.float32)
    x, y = xy[:, 0], xy[:, 1]
    inside = (x >= 0) & (x < w - 1) & (y >= 0) & (y < h - 1)
    x, y, weight = x[inside], y[inside], depth[inside]

    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    for dx, dy, f in (
        (0, 0, (1 - fx) * (1 - fy)),
        (1, 0, fx * (1 - fy)),
        (0, 1, (1 - fx) * fy),
        (1, 1, fx * fy),
    ):
        np.add.at(buf, (y0 + dy, x0 + dx), (f * weight).astype(np.float32))
    return gaussian_filter(buf, SPLAT)


def render(
    xyz: np.ndarray,
    driver: np.ndarray | None = None,
    width: int = WIDTH,
) -> Plate:
    """`xyz` is (n, 3) voxel coordinates; `driver` a boolean mask of the labelled cells.

    The view is dorsal: x across the image, z down it, y into the page. That is the
    orientation this connectome is published in, and it keeps the two optic lobes, the
    central brain and the nerve cord in the arrangement a reader has seen before.
    """
    from scipy.ndimage import gaussian_filter

    xyz = np.asarray(xyz, dtype=np.float64)
    driver = np.zeros(len(xyz), dtype=bool) if driver is None else np.asarray(driver, dtype=bool)

    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    minX, maxX, minZ, maxZ = x.min(), x.max(), z.min(), z.max()
    span_x, span_z = maxX - minX, maxZ - minZ
    w = width * SUPERSAMPLE
    scale = w * (1 - 2 * MARGIN) / span_x
    h = round(float(span_z * scale + 2 * MARGIN * w))
    px = (x - minX) * scale + MARGIN * w
    py = (z - minZ) * scale + MARGIN * w

    # Depth cue: dorsal cells (small y) are nearest the objective and brightest. The falloff
    # is what gives a flat point cloud its solidity.
    near = (y.max() - y) / max(y.max() - y.min(), 1.0)
    bright = DEPTH_FLOOR + (1 - DEPTH_FLOOR) * near**1.3

    xy = np.stack([px, py], axis=1)
    counter = _splat(xy[~driver], bright[~driver], (h, w))
    labelled = _splat(xy[driver], bright[driver] * 3.0, (h, w)) if driver.any() else None

    def tone(a: np.ndarray) -> np.ndarray:
        # Filmic-ish: linear near zero, compressive at the top, so dense regions stay
        # legible instead of clipping to a white slab.
        v = a * EXPOSURE / max(np.percentile(a[a > 0], 99.0), 1e-6)
        return v / (1.0 + v)

    def channel(a: np.ndarray, colour: np.ndarray) -> np.ndarray:
        t = tone(a)
        hot = np.clip((t - WHITE_KNEE) / (1 - WHITE_KNEE), 0, 1)
        tint = colour[None, None, :] * (1 - hot[..., None]) + hot[..., None]
        return t[..., None] * tint

    rgb = channel(counter, COUNTERSTAIN)
    if labelled is not None:
        rgb = rgb + channel(labelled, DRIVER)

    bloom = gaussian_filter(np.clip(rgb - 0.45, 0, None), (BLOOM_SIGMA, BLOOM_SIGMA, 0))
    rgb = rgb + BLOOM_GAIN * bloom

    rgb = rgb.reshape(h // SUPERSAMPLE, SUPERSAMPLE, w // SUPERSAMPLE, SUPERSAMPLE, 3).mean((1, 3))
    rng = np.random.default_rng(0)
    rgb = rgb + rng.normal(0, GRAIN, rgb.shape)

    log.info(
        "plate %dx%d from %d somas (%d labelled)",
        rgb.shape[1], rgb.shape[0], len(xyz), int(driver.sum()),
    )
    return Plate(
        rgb=np.clip(rgb, 0, 1),
        bounds=(float(minX), float(maxX), float(minZ), float(maxZ)),
        n_counterstain=int((~driver).sum()),
        n_driver=int(driver.sum()),
    )


def somas(root: Path) -> tuple[np.ndarray, np.ndarray]:
    """Every located soma in the annotations, as (bodyId, xyz). Not the page's sample."""
    from pyarrow import feather

    from karbes.graph.populations import ANNOTATIONS

    d = feather.read_table(root / ANNOTATIONS, columns=["bodyId", "somaLocation"]).to_pydict()
    bodies, coords = [], []
    for body, loc in zip(d["bodyId"], d["somaLocation"], strict=True):
        if loc is None:
            continue
        bodies.append(body)
        coords.append(loc)
    return np.asarray(bodies, dtype=np.int64), np.asarray(coords, dtype=np.int64)
