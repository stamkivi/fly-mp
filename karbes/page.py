"""Build the standalone replay page: one HTML file with the data baked in.

No LLM call, no simulation and no network fetch at view time. The bundle, the raster and
the soma atlas are embedded, so the page is a single file that can be opened from disk or
served from anywhere and will still work in five years.

The caveats paragraph is generated rather than written into the template, because it
quotes the measured SNR and dead band. A page that states a stale SNR is worse than one
that states none.
"""

from __future__ import annotations

import base64
import html
import json
import logging
from pathlib import Path

from karbes.atlas import Atlas

log = logging.getLogger(__name__)

TEMPLATE = Path("page/template.html")


def caveats(bundle: dict, calibration: dict) -> str:
    """The paragraph that keeps the page honest, with live numbers in it.

    Rewritten after the sweep was measured properly. An earlier version quoted an SNR of
    0.88 and described the fly as "visibly making up its mind". Both were artefacts of a
    single-seed sweep; the full-scale stimulus effect is consistent with zero. A page that
    states a disproved number is worse than one that states none, so the headline finding
    is now the first thing in this list rather than absent from it.
    """
    band = bundle["race"]["dead_band_hz"]
    noise = calibration["noise_hz"]
    resolved = calibration.get("channels_resolved_above_noise", [])
    sweep = calibration["sweep"]
    n = calibration.get("sweep_seeds", 1)
    widest = max(sweep.values(), key=lambda v: abs(v.get("span", 0.0)))
    widest_key = next(k for k, v in sweep.items() if v is widest)
    frac = bundle["atlas"]["sampled_fraction"]
    parts = [
        (
            "<b>The bill does not measurably change what this fly's readout does.</b> Swept over "
            f"{n} input phases per point, the strongest of the nine channels "
            f"(<code>{widest_key}</code>) moves the readout by "
            f"{widest['span']:+.2f}&nbsp;Hz &plusmn;&nbsp;{widest['se']:.2f} &mdash; and "
            f"{'only ' + str(len(resolved)) if resolved else '<b>none</b>'} of the channels "
            "separate from the run-to-run spread at all. Driving every channel to its "
            "positive extreme against every channel at its negative extreme moves it by "
            "&minus;0.09&nbsp;Hz &plusmn;&nbsp;0.38. The animation above is real, and so is "
            "the verdict it produced, but what you are watching the brain respond to is "
            "being switched on &mdash; not to this bill. The signal is there and the average "
            "is what loses it: against a permutation null, 22 of the 1,304 descending "
            "neurons respond to the stimulus where three would be expected by chance."
        ),
        (
            "<b>Why: the network has two states and nothing in between.</b> With no input "
            "at all it is perfectly silent. With half a hertz on a thousand receptor "
            "neurons it runs at 21&nbsp;Hz. Raising the input two hundred-fold from there, "
            "to 100&nbsp;Hz, takes it to 24&nbsp;Hz. Once lit, the activity sustains itself "
            "through 25.6 million recurrent connections, and the thousand cells carrying "
            "the bill are a rounding error against 166,700 neurons driving each other."
        ),
        (
            "<b>The input/output mapping is engineered, not discovered.</b> There are no "
            "&ldquo;aye&rdquo; neurons in a fly. Nine questions about the bill were assigned "
            "to sixteen olfactory receptor populations by an arbitrary, fixed pairing, and "
            "the vote is read off two pools of descending neurons because those are the "
            "cells that steer a walking fly. Nothing here is a claim about what the fly "
            "experiences."
        ),
        (
            f"<b>The threshold comes from the brain, never from the chamber.</b> A race "
            f"closer than {band:.2f}&nbsp;Hz counts as declining to vote &mdash; one "
            f"standard deviation ({noise:.2f}&nbsp;Hz) of what this network does on a bill "
            "that says nothing. It was never tuned to make the voting record agree with "
            "anybody."
        ),
        (
            "<b>The brain on screen is real; its density is not.</b> Every soma sits at its "
            "measured MaleCNS coordinate, but the sample is deliberately uneven: "
            + ", ".join(f"{k} {v * 100:.0f}%" for k, v in frac.items())
            + ". Optic-lobe cells are two thirds of the brain, and sampling them evenly "
            "would draw two enormous eyes and hide the cells the vote is read from."
        ),
    ]
    return json.dumps("<br><br>".join(parts))


def finding(calibration: dict) -> str:
    """The one-paragraph result, at the top, where a reader cannot miss it."""
    n = calibration.get("sweep_seeds", 1)
    resolved = calibration.get("channels_resolved_above_noise", [])
    return json.dumps(
        "<b>Finding, stated before you watch anything:</b> the brain below is real and so is "
        "the firing &mdash; but <b>the verdict it produces is not yet reading the bill</b>. "
        "Driving every topic channel to one extreme against the other moves this readout by "
        "&minus;0.09&nbsp;Hz &plusmn;&nbsp;0.38, which is nothing, and over "
        f"{n} input phases per point {'only ' + str(len(resolved)) if resolved else 'none'} "
        "of the nine channels separate from the network's own run-to-run spread."
        "<br><br>"
        "The signal is not missing, though &mdash; it is being averaged away. The readout is "
        "the mean rate of 656 descending neurons minus the mean rate of 648, and against a "
        "permutation null <b>22 of those 1,304 cells do respond</b> to the stimulus where "
        "three would be expected by chance. The connectome transmits; this decoder discards. "
        "Fixing that is the next experiment, and until it is done the vote below should be "
        "read as an honest recording of a fly brain being switched on rather than as an "
        "opinion about the bill."
    )


def build(bundle: dict, raster: bytes, atlas: Atlas, calibration: dict) -> str:
    """Fill the template. Returns the finished HTML."""
    if "sweep_seeds" not in calibration:
        # A single-seed sweep is what produced the SNR figure the page used to print and
        # the measurements later disproved. Refuse to publish from one rather than quote
        # a number with no error bar beside it.
        raise ValueError(
            "runs/calibration.json predates the seeded sweep and has no standard errors. "
            "Re-run `karbes calibrate` before building the page."
        )
    template = TEMPLATE.read_text(encoding="utf-8")
    # The bundle rides in a `application/json` script tag, so only `</script>` and a lone
    # `<` can break out of it.
    doc = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    for token, value in (
        ("__BUNDLE_JSON__", doc),
        ("__ATLAS_B64__", base64.b64encode(atlas.web_bytes()).decode()),
        ("__RASTER_B64__", base64.b64encode(raster).decode()),
        ("__CAVEATS__", caveats(bundle, calibration)),
        ("__FINDING__", finding(calibration)),
    ):
        if token not in template:
            raise ValueError(f"template has no {token} placeholder")
        template = template.replace(token, value)
    title = html.escape(bundle["bill"]["title"])
    return template.replace(
        "<title>Kärbes — the 102nd member of the Riigikogu</title>",
        f"<title>Kärbes — {title}</title>",
    )


def write(path: Path, page: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    log.info("page: %s (%.0f KB)", path, path.stat().st_size / 1024)
    return path
