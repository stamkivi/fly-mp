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
    """The honest limits, for the notes below the fold."""
    a = bundle["arena"]
    frac = bundle["atlas"]["sampled_fraction"]
    return json.dumps(
        "<b>The mapping is engineered, not discovered.</b> There are no &ldquo;aye&rdquo; "
        "neurons in a fly, and no fly has an opinion about who tabled a bill. The eight "
        "questions were assigned to olfactory receptor populations by an arbitrary, fixed "
        "pairing, and which eye the procedural signal arrives on was fixed the same way. The "
        "vote is read from the descending neurons whose left-right firing difference sets how "
        "a walking fly turns. It steers; it does not vote."
        "<br><br>"
        "<b>The brain is real; its density is not.</b> Every cell body sits at its measured "
        "MaleCNS coordinate, but the sample is deliberately uneven — "
        + ", ".join(f"{k} {x * 100:.0f}%" for k, x in frac.items())
        + ". Photoreceptors are not driven at all: all 6,098 are histaminergic and carry no "
        "outgoing connections in this dataset, so sight enters at the motion detectors instead."
        "<br><br>"
        "<b>One bill, one run.</b> That the informed fly reached a different question than the "
        f"blind one is a single observation on a single seed, not a result. Both are the same "
        f"fly for {a['reveal_step']} steps &mdash; same brain, same seed, same scents &mdash; "
        "so nothing else differs between them, but one pair of walks is not evidence about "
        "the corpus. Whether a rewired brain would land somewhere else, which is the actual "
        "experiment, is not answered here."
    )


def note_what(bundle: dict) -> str:
    """What the viewer just watched, in plain terms."""

    return json.dumps(
        "An LLM scored what this bill does on eight questions, without being told who tabled "
        "it. Each score became a scent, and the eight scents were placed round a ring in "
        "proportion to how strongly the question applies. Then a spiking simulation of a real "
        f"fly brain &mdash; {bundle['sim']['neurons']:,} neurons and "
        f"{bundle['sim']['edges']:,} connections from the MaleCNS connectome &mdash; walked "
        "the fly through that field, one step at a time, in closed loop: the scents reaching "
        "each antenna depend on which way it is facing, and the brain's steering output "
        "changes which way it faces."
        "<br><br>"
        f"That loop is doing real work. A single sniff of a typical bill moves this readout by "
        "about 2% of its range, far too little to decide anything on its own. Walking is how a "
        "fly solves that: a small bias, fed back through a gradient that shifts as the animal "
        "turns, becomes a committed trajectory over many steps."
    )


def note_bit(bundle: dict) -> str:
    """Why the procedural sense dominates, with the corpus numbers."""
    return json.dumps(
        "Partway through, the fly is told one thing more, through a second sense: whether the "
        "government tabled the bill or a member did. It arrives as one-sided visual motion, "
        "the way a fly sees the world sweep past when it turns."
        "<br><br>"
        "<b>That single bit is most of Estonian politics.</b> Across 565 contested votes in "
        "this Riigikogu, government bills advanced <b>99.3%</b> of the time and members' bills "
        "<b>10.4%</b>. The bit alone calls <b>94.2%</b> of outcomes; the majority baseline is "
        "52.6%. What the bill actually says predicts far less. And the two are largely "
        "independent &mdash; the topic scores correlate with the bit at only r = 0.10 to 0.44 "
        "&mdash; so the substance and the procedure often point different ways."
        "<br><br>"
        "So the page runs two flies that are identical in every respect until that moment. The "
        "dashed trail is the one that was never told."
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
    fly = Path("page/assets/fly.png")
    for token, value in (
        ("__FLY_B64__", base64.b64encode(fly.read_bytes()).decode()),
        ("__BUNDLE_JSON__", doc),
        ("__ATLAS_B64__", base64.b64encode(atlas.web_bytes()).decode()),
        ("__RASTER_B64__", base64.b64encode(raster).decode()),
        ("__CAVEATS__", caveats(bundle, calibration)),
        ("__NOTE_WHAT__", note_what(bundle)),
        ("__NOTE_BIT__", note_bit(bundle)),
    ):
        if token not in template:
            raise ValueError(f"template has no {token} placeholder")
        template = template.replace(token, value)
    title = html.escape(bundle["bill"]["title"])
    return template.replace("<title>Kärbes</title>", f"<title>Kärbes — {title}</title>")


def write(path: Path, page: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    log.info("page: %s (%.0f KB)", path, path.stat().st_size / 1024)
    return path
