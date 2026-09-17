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
    fs = calibration["full_scale"]
    band = bundle["race"]["dead_band"]
    bias = bundle["race"]["baseline_bias"]
    n = calibration["seeds"]
    resolved = calibration.get("channels_resolved_above_noise", [])
    frac = bundle["atlas"]["sampled_fraction"]
    parts = [
        (
            "<b>The input/output mapping is engineered, not discovered.</b> There are no "
            "&ldquo;aye&rdquo; neurons in a fly. Nine questions about the bill were assigned "
            "to sixteen olfactory receptor populations by an arbitrary, fixed pairing, and "
            "the sign of each score decides which antenna is driven harder. The vote is "
            "read off the DNa descending neurons because those are the cells whose "
            "left-right firing difference sets how a walking fly turns. Nothing here is a "
            "claim about what the fly experiences &mdash; it steers, it does not vote."
        ),
        (
            "<b>The fly does respond to a lateralised bill.</b> Driving every channel to one "
            f"extreme against the other moves the turn index by {fs['difference']:+.3f} "
            f"&plusmn;&nbsp;{fs['se']:.3f} (t&nbsp;=&nbsp;{fs['t']:+.1f}, "
            f"d&prime;&nbsp;=&nbsp;{fs['d_prime']:+.2f}) over {n} input phases. That is the "
            "instrument working. <b>A single channel is a different matter:</b> it drives two "
            "glomeruli of sixteen, so its effect is about an eighth of that, and at "
            f"{n} phases {len(resolved)} of the nine channels separate from the run-to-run "
            "spread. That is a statement about how many runs were done, not a null result, "
            "and it is why a single bill's verdict should not be read as an opinion."
        ),
        (
            f"<b>The left/right bias is subtracted, not ignored.</b> A bill that says nothing "
            f"still produces a turn index of {bias:+.3f}, because the wiring is not "
            "perfectly symmetric and the two antennae do not carry equal numbers of receptor "
            "neurons. That baseline is measured on a blank bill and removed. A turn closer "
            f"than {band:.3f} &mdash; one standard deviation of what this network does on a "
            "blank bill &mdash; counts as declining to vote, and was never tuned to make the "
            "voting record agree with anybody."
        ),
        (
            "<b>The brain on screen is real; its density is not.</b> Every soma sits at its "
            "measured MaleCNS coordinate, but the sample is deliberately uneven: "
            + ", ".join(f"{k} {v * 100:.0f}%" for k, v in frac.items())
            + ". Optic-lobe cells are two thirds of the brain, and sampling them evenly "
            "would draw two enormous eyes and hide the cells the vote is read from."
        ),
        (
            "<b>One bill is not a voting record.</b> This is a single bill, simulated once, "
            "with the fly's position marked where the MPs who voted the same way happen to "
            "sit. Whether a rewired fly would land somewhere else &mdash; the actual "
            "experiment &mdash; is not answered here."
        ),
    ]
    return json.dumps("<br><br>".join(parts))


def finding(calibration: dict) -> str:
    """The one-paragraph result, at the top, where a reader cannot miss it."""
    fs = calibration["full_scale"]
    n = calibration["seeds"]
    resolved = calibration.get("channels_resolved_above_noise", [])
    return json.dumps(
        "<b>What this is, stated before you watch it:</b> a spiking simulation of a real fly "
        "brain, with a real bill turned into a smell that arrives more strongly on one "
        "antenna than the other, and the vote read from the descending neurons that steer a "
        "walking fly. The brain is silent until the bill arrives and then fires sparsely, "
        "which is what this model is supposed to do."
        "<br><br>"
        "<b>The instrument works, and its limits are worth knowing.</b> Swung from one "
        f"extreme to the other the bill moves the fly's turn by {fs['difference']:+.3f} "
        f"&plusmn;&nbsp;{fs['se']:.3f} (d&prime;&nbsp;=&nbsp;{fs['d_prime']:+.2f}). But any "
        "single bill pushes far less hard than that, and at "
        f"{n} input phases {len(resolved)} of the nine topic channels can be told apart from "
        "the network's own run-to-run spread. So watch the fly decide, and treat the verdict "
        "as one noisy draw rather than as an opinion about the bill."
    )


def build(bundle: dict, raster: bytes, atlas: Atlas, calibration: dict) -> str:
    """Fill the template. Returns the finished HTML."""
    if "full_scale" not in calibration:
        # An earlier page quoted an SNR from a single-seed sweep on a kernel that
        # implemented the synapse wrongly. Refuse to publish from a calibration that
        # predates either fix rather than print a number with no error bar beside it.
        raise ValueError(
            "runs/calibration.json predates the current engine and readout. "
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
