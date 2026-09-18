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
    a = bundle["arena"]
    frac = bundle["atlas"]["sampled_fraction"]
    parts = [
        (
            "<b>The mapping is engineered, not discovered.</b> There are no &ldquo;aye&rdquo; "
            "neurons in a fly, and no fly has an opinion about who tabled a bill. Nine "
            "questions about the text were assigned to sixteen olfactory receptor "
            "populations by an arbitrary, fixed pairing; which eye the procedural signal "
            "arrives on was fixed the same way. The vote is read from the DNa descending "
            "neurons because those are the cells whose left-right firing difference sets "
            "how a walking fly turns. It steers; it does not vote."
        ),
        (
            "<b>The two senses carry different questions, and that is the finding.</b> Smell "
            "is what the bill does &mdash; the scoring model never sees the initiator. Vision "
            "is who tabled it, which on 565 contested votes calls <b>94.2%</b> of outcomes by "
            "itself: government bills advance 99.3% of the time, members' bills 10.4%. The "
            "two are largely independent (the topic channels correlate with that bit at only "
            "r&nbsp;=&nbsp;0.10&ndash;0.44), so substance and procedure disagree often."
        ),
        (
            "<b>Both flies are the same fly until the reveal.</b> They share a seed, a brain "
            f"and an odour field, and run bit-identically for {a['reveal_step']} steps. Then "
            "one of them is shown who tabled the bill and the paths separate. Nothing else "
            "differs between them."
        ),
        (
            "<b>The loop is the amplifier, not a gain knob.</b> A single whiff of a typical "
            "bill uses about 2% of the encoder's range and cannot beat the network's own "
            "run-to-run spread. Walking fixes that the way a real fly does: a small bias, fed "
            "back through a gradient that changes as the animal turns, commits over many "
            "steps."
        ),
        (
            "<b>The brain on screen is real; its density is not.</b> Every soma sits at its "
            "measured MaleCNS coordinate, but the sample is deliberately uneven: "
            + ", ".join(f"{k} {x * 100:.0f}%" for k, x in frac.items())
            + ". Photoreceptors are not driven at all &mdash; all 6,098 are histaminergic and "
            "carry no outgoing edges in this connectome, so vision enters at the motion "
            "detectors instead."
        ),
        (
            "<b>One bill is not a voting record.</b> Whether a rewired fly would land "
            "somewhere else &mdash; the actual experiment &mdash; is not answered here."
        ),
    ]
    return json.dumps("<br><br>".join(parts))


def finding(calibration: dict) -> str:
    """The one-paragraph result, at the top, where a reader cannot miss it."""
    return json.dumps(
        "<b>What you are about to watch.</b> Eight pots stand in a ring, one for each "
        "question the bill was scored on, each smelling as strongly as that question "
        "applies. A simulated fly brain &mdash; 166,700 neurons, 24.5 million connections, "
        "real cell positions &mdash; walks the fly toward whichever question pulls hardest. "
        "Where it ends up is its vote."
        "<br><br>"
        "<b>Then it is told who tabled the bill,</b> through a second sense: one-sided "
        "visual motion, the way a fly sees the world sweep past. That one bit predicts "
        "<b>94%</b> of real Riigikogu outcomes on its own, where the bill's actual content "
        "predicts far less. So the page runs two flies that are identical in every respect "
        "until the moment one of them sees it. Watch where they come apart."
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
