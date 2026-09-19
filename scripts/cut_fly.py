"""Matte the Karwath dorsal Drosophila (CC BY-SA 2.5) off its light background.

The photograph was taken on a light, slightly graded background. A pixel we see is
C = a*F + (1-a)*B: the fly's own colour F mixed with the background B by coverage a.
We estimate B per pixel from the image border, take a from how far C sits from B
(luminance and chroma), and solve for F. Wings come out translucent, bristles keep
their soft edge, and there is no white fringe over a dark desk.

    uv run python scripts/cut_fly.py data/raw/assets/karwath_top.jpg page/assets/fly.png [--preview /tmp/fly_preview.png]
    uv run python scripts/cut_fly.py data/raw/assets/orkin_house_fly.png page/assets/fly.png --white   # illustration on white
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def grow(seed: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """Flood `seed` outward one pixel at a time, never leaving `allowed`, until stable."""
    cur = seed & allowed
    for _ in range(2000):
        nxt = (
            np.asarray(
                Image.fromarray((cur * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(3))
            )
            > 0
        ) & allowed
        if (nxt == cur).all():
            return cur
        cur = nxt
    return cur


def matte_white(im: np.ndarray) -> np.ndarray:
    """An illustration on pure white: coverage is how far a pixel drops below white in its
    lightest channel (a translucent grey wing is a light grey; a red eye is dark in green and
    blue), and the colour is what remains once that much white is taken out."""
    dark = 255.0 - im.min(axis=2)
    a = np.clip((dark - 8.0) / 80.0, 0, 1)  # wing membrane stays thin, a thorax highlight is solid
    a = a * a * (3 - 2 * a)
    a3 = a[:, :, None]
    F = np.where(a3 > 0.02, (im - (1 - a3) * 255.0) / np.maximum(a3, 0.02), im)
    return np.dstack([np.clip(F, 0, 255), a * 255]).astype(np.uint8)


def main(src: Path, out: Path, preview: Path | None, white: bool = False) -> None:
    im = np.asarray(Image.open(src).convert("RGB")).astype(np.float64)
    h, w, _ = im.shape
    if white:
        rgba = matte_white(im)
        a = rgba[:, :, 3] / 255.0
        finish(rgba, a, out, preview)
        return
    # background: bilinear plane through the mean colour of each edge band
    band = 6
    top, bot = im[:band].mean(axis=(0, 1)), im[-band:].mean(axis=(0, 1))
    left, right = im[:, :band].mean(axis=(0, 1)), im[:, -band:].mean(axis=(0, 1))
    ty = np.linspace(0, 1, h)[:, None, None]
    tx = np.linspace(0, 1, w)[None, :, None]
    bg = (top * (1 - ty) + bot * ty) * 0.5 + (left * (1 - tx) + right * tx) * 0.5
    lum = im @ np.array([0.299, 0.587, 0.114])
    lum_bg = bg @ np.array([0.299, 0.587, 0.114])
    # coverage from darkness relative to the background, and from colour distance (the red
    # eyes, the iridescent wing). A dead zone below `lo` drops the dust and the photograph's
    # own shadow; `hi` is where a pixel counts as solid fly.
    lo, hi = 30.0, 105.0
    lumdiff = lum_bg - lum
    # colour distance with the brightness component removed: a brighter patch of the
    # background under the fly is still background
    chroma = (im - bg) - (lum - lum_bg)[:, :, None]
    chroma_n = np.linalg.norm(chroma, axis=2)
    d = np.maximum(lumdiff, chroma_n * 1.2)
    a = np.clip((d - lo) / (hi - lo), 0, 1)
    a = a * a * (3 - 2 * a)
    # the body has colour; the cast shadow on the surface has none. Close the coloured firm
    # mask so dull patches inside the body count as body, then everything grey outside it
    # is shadow: it becomes translucent black rather than opaque grey.
    chromatic = chroma_n > 15
    body_firm = Image.fromarray(((a > 0.85) & chromatic).astype(np.uint8) * 255, "L")
    body_mask = (
        np.asarray(body_firm.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))) > 0
    )
    # how much of a pixel is shadow rather than fly: grey outside the body is shadow, colour
    # is fly, with a soft ramp between so the boundary does not pixelate
    w_shadow = np.clip((26.0 - chroma_n) / 16.0, 0, 1)
    body_soft = (
        np.asarray(
            Image.fromarray(body_mask.astype(np.uint8) * 255, "L").filter(
                ImageFilter.GaussianBlur(2.5)
            )
        )
        / 255.0
    )
    w_shadow *= 1 - body_soft
    # keep only what touches the body: grow the body mask outward, one pixel at a time,
    # never past the soft mask; dust that floats free is left behind
    grown = grow(body_mask, a > 0.02)
    a = np.where(grown, a, 0.0)
    a_shadow = np.clip((lumdiff - 20.0) / 150.0, 0, 1) * 0.55 * grown
    a = w_shadow * a_shadow + (1 - w_shadow) * a
    a = (
        np.asarray(
            Image.fromarray((a * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.8))
        )
        / 255.0
    )
    # solve for the fly's own colour; shadow pixels are black by definition
    a3 = a[:, :, None]
    F = np.where(a3 > 0.02, (im - (1 - a3) * bg) / np.maximum(a3, 0.02), im)
    F = (1 - w_shadow[:, :, None]) * F
    # a small hole the body encloses is a specular highlight: opaque, its own colour
    border = np.zeros_like(body_mask)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    holes = ~grow(border, ~body_mask) & ~body_mask
    a = np.where(holes, 1.0, a)
    F = np.where(holes[:, :, None], im, F)
    F = np.clip(F, 0, 255)
    rgba = np.dstack([F, a * 255]).astype(np.uint8)
    finish(rgba, a, out, preview)


def finish(rgba: np.ndarray, a: np.ndarray, out: Path, preview: Path | None) -> None:
    h, w = a.shape
    # crop to the fly with a margin
    ys, xs = np.where(a > 0.03)
    m = 10
    y0, y1 = max(0, ys.min() - m), min(h, ys.max() + m)
    x0, x1 = max(0, xs.min() - m), min(w, xs.max() + m)
    fly = Image.fromarray(rgba[y0:y1, x0:x1], "RGBA")
    fly.save(out, optimize=True)
    print(out, fly.size, "alpha>0.5:", int((a[y0:y1, x0:x1] > 0.5).sum()), "px")
    if preview:
        hall = Image.open("page/assets/hall.jpg").convert("RGB")
        W, H = hall.size
        fw = int(W * 0.16)
        f = fly.resize((fw, int(fw * fly.height / fly.width)), Image.LANCZOS)
        cx, cy = int(W * 0.5), int(H * 0.90)
        # contact shadow: the fly's own silhouette, darkened, blurred, offset
        sh = Image.new("RGBA", f.size, (0, 0, 0, 0))
        sh.putalpha(f.getchannel("A").point(lambda v: int(v * 0.55)))
        sh = sh.filter(ImageFilter.GaussianBlur(fw * 0.03))
        hall.paste(sh, (cx - fw // 2 + int(fw * 0.02), cy - f.height // 2 + int(fw * 0.05)), sh)
        hall.paste(f, (cx - fw // 2, cy - f.height // 2), f)
        crop = hall.crop((cx - fw, cy - fw // 2 - 40, cx + fw, cy + fw // 2 + 20))
        wood = Image.new("RGB", (fly.width + 40, fly.height + 40), (112, 78, 44))
        wood.paste(fly, (20, 20), fly)
        dark = Image.new("RGB", (fly.width + 40, fly.height + 40), (12, 16, 23))
        dark.paste(fly, (20, 20), fly)
        light = Image.new("RGB", (fly.width + 40, fly.height + 40), (246, 244, 239))
        light.paste(fly, (20, 20), fly)
        strip = Image.new("RGB", (wood.width * 3, wood.height), (0, 0, 0))
        for i, p in enumerate((wood, dark, light)):
            strip.paste(p, (i * wood.width, 0))
        sheet = Image.new(
            "RGB", (max(strip.width, crop.width), strip.height + crop.height), (0, 0, 0)
        )
        sheet.paste(strip, (0, 0))
        sheet.paste(crop, (0, strip.height))
        sheet.save(preview)
        print(preview, sheet.size)


if __name__ == "__main__":
    args = sys.argv[1:]
    prev = Path(args[args.index("--preview") + 1]) if "--preview" in args else None
    main(Path(args[0]), Path(args[1]), prev, white="--white" in args)
