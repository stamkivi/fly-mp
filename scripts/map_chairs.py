"""Find the chairs in the hall photograph, so a speaker's lamp lands on a chair.

The rows of desks are horizontal in the photograph. Within a row band, chair backs are the
wide dark runs of the column-darkness profile; the narrow dark runs are the gaps between
desks. Each band's aisle edges are read off the image (the aisle widens towards the desk).
Writes page/assets/chairs.json: {"L": [[x, y], ...], "R": [...]} as fractions of the
photograph, front row first, left to right within a row.

    uv run python scripts/map_chairs.py [--debug /tmp/chairs.png]
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "page" / "assets" / "hall.jpg"
OUT = ROOT / "page" / "assets" / "chairs.json"

# (top, bottom, left block's aisle edge, right block's aisle edge), front row first
BANDS = [
    (0.660, 0.705, 0.400, 0.535),
    (0.607, 0.648, 0.418, 0.528),
    (0.566, 0.602, 0.432, 0.522),
    (0.538, 0.564, 0.442, 0.518),
    (0.517, 0.537, 0.450, 0.514),
    (0.500, 0.516, 0.455, 0.512),
]
DARK = 72  # luminance below which a pixel is chair rather than desk or floor


def chairs(photo: Path = PHOTO) -> dict[str, list[list[float]]]:
    im = Image.open(photo).convert("RGB")
    w, h = im.size
    lum = np.asarray(im).astype(float) @ [0.299, 0.587, 0.114]
    dark = lum < DARK
    out: dict[str, list[list[float]]] = {"L": [], "R": []}
    for r, (y0, y1, aisle_l, aisle_r) in enumerate(BANDS):
        prof = dark[int(y0 * h) : int(y1 * h)].mean(axis=0)
        cw = w * (0.046 - 0.021 * r / 5)  # chair-back width shrinks with depth
        k = int(max(3, cw * 0.35))
        sm = np.convolve(prof, np.ones(k) / k, mode="same")
        yc = (y0 + y1) / 2
        for side, lo, hi in (("L", 0.0, aisle_l), ("R", aisle_r, 1.0)):
            seg = sm.copy()
            seg[: int(lo * w)] = 0
            seg[int(hi * w) :] = 0
            on = seg > 0.5 * seg.max()
            i = 0
            while i < w:
                if not on[i]:
                    i += 1
                    continue
                j = i
                while j < w and on[j]:
                    j += 1
                run = j - i
                if run >= 0.45 * cw:  # a chair back is wide; a desk gap is not
                    n = max(1, round(run / cw))  # a merged pair splits by width
                    for m in range(n):
                        out[side].append([round((i + run * (m + 0.5) / n) / w, 4), round(yc, 4)])
                i = j
    return out


def main() -> None:
    c = chairs()
    OUT.write_text(json.dumps(c), encoding="utf-8")
    print(OUT, {s: len(v) for s, v in c.items()})
    if "--debug" in sys.argv:
        im = Image.open(PHOTO).convert("RGB")
        w, h = im.size
        d = ImageDraw.Draw(im)
        for v in c.values():
            for x, y in v:
                d.ellipse(
                    [x * w - 5, y * h - 5, x * w + 5, y * h + 5], outline=(255, 230, 0), width=2
                )
        p = Path(sys.argv[sys.argv.index("--debug") + 1])
        im.crop((0, int(h * 0.46), w, int(h * 0.74))).save(p)
        print(p)


if __name__ == "__main__":
    main()
