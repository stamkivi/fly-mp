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
    """The paragraph that keeps the page honest, with live numbers in it."""
    snr = calibration["snr"]
    noise = calibration["noise_hz"]
    signal = calibration["signal_hz"]
    band = bundle["race"]["dead_band_hz"]
    frac = bundle["atlas"]["sampled_fraction"]
    parts = [
        (
            "<b>The input/output mapping is engineered, not discovered.</b> There are no "
            "&ldquo;aye&rdquo; neurons in a fly. Nine questions about the bill were assigned to "
            "sixteen olfactory receptor populations by an arbitrary, fixed pairing, and the vote "
            "is read off two pools of descending neurons because they are the cells that steer a "
            "walking fly. Nothing here is a claim about what the fly experiences."
        ),
        (
            f"<b>The fly wavers, and that is real.</b> Moving a channel from &minus;1 to +1 shifts "
            f"the readout by {signal:.2f}&nbsp;Hz on average. Re-running the same bill with a "
            f"different input phase shifts it by {noise:.2f}&nbsp;Hz. The signal-to-noise ratio is "
            f"<b>{snr:.2f}</b>: the noise is larger than the signal. That is measured, it has not "
            "been averaged away, and a different seed can genuinely produce a different vote."
        ),
        (
            f"<b>The threshold comes from the brain, never from the chamber.</b> A race closer than "
            f"{band:.2f}&nbsp;Hz is recorded as declining to vote. That figure is one standard "
            "deviation of what this network does when the bill says nothing at all &mdash; it was "
            "never tuned to make the voting record agree with anybody."
        ),
        (
            "<b>The brain on screen is real, its density is not.</b> Every soma is at its measured "
            "MaleCNS coordinate, but the sample is deliberately uneven: "
            + ", ".join(f"{k} {v * 100:.0f}%" for k, v in frac.items())
            + ". Optic-lobe cells are two thirds of the brain, and sampling them evenly would draw "
            "two enormous eyes and hide the cells the vote is actually read from."
        ),
        (
            "<b>One bill is not a voting record.</b> This is a single bill, simulated once, with "
            "the fly's position marked where the MPs who voted the same way happen to sit. "
            "Whether a rewired fly would land somewhere else &mdash; the actual experiment &mdash; "
            "is not answered here."
        ),
    ]
    return json.dumps("<br><br>".join(parts))


def build(bundle: dict, raster: bytes, atlas: Atlas, calibration: dict) -> str:
    """Fill the template. Returns the finished HTML."""
    template = TEMPLATE.read_text(encoding="utf-8")
    # The bundle rides in a `application/json` script tag, so only `</script>` and a lone
    # `<` can break out of it.
    doc = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    for token, value in (
        ("__BUNDLE_JSON__", doc),
        ("__ATLAS_B64__", base64.b64encode(atlas.web_bytes()).decode()),
        ("__RASTER_B64__", base64.b64encode(raster).decode()),
        ("__CAVEATS__", caveats(bundle, calibration)),
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
