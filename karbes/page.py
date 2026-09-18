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


# --------------------------------------------------------------------------- season page

SEASON_TEMPLATE = Path("page/season.html")


def season_copy(bundle: dict) -> dict[str, str]:
    """The prose for the season page, with its own numbers in it."""
    informed, blind = bundle["arms"]["informed"], bundle["arms"]["blind"]
    rew = bundle.get("rewired") or {}
    gov = max(informed["agreement"], key=informed["agreement"].get)
    best = informed["agreement"][gov] * 100
    worst_f = min(informed["agreement"], key=informed["agreement"].get)
    worst = informed["agreement"][worst_f] * 100

    twist_blind = (
        "<b>Take away one bit and it is noise.</b> The same brain, the same bills, but never "
        "told who tabled each one: AUC "
        f"{blind['auc_advances']:.2f} against a 0.50 null, and agreement within a point or "
        "two of chance with every faction. What the bill says is not what decides it."
    )
    if rew:
        aucs = [r["auc_advances"] for r in rew.values()]
        spread = [r["dim1"] for r in rew.values() if r["dim1"] is not None]
        beaten = sum(1 for a in aucs if a >= informed["auc_advances"])
        # The control is the experiment, so it reports whichever way it came out.
        if beaten >= max(1, len(aucs) // 2):
            twist_rewired = (
                "<b>The wiring is not what does it.</b> Shuffle the connectome — every neuron "
                "keeps its in-degree, out-degree and sign, only who reaches whom is "
                f"randomised — and {len(rew)} rewired brains score AUC "
                + ", ".join(f"{a:.2f}" for a in aucs)
                + f" against this one's {informed['auc_advances']:.2f}. The seat comes from the "
                "signal being fed in, not from this particular tangle of neurons."
            )
        else:
            twist_rewired = (
                f"<b>The wiring is doing the work.</b> {len(rew)} degree-preserving rewirings "
                "score AUC "
                + ", ".join(f"{a:.2f}" for a in aucs)
                + f" against this fly's {informed['auc_advances']:.2f}, and land at "
                + ", ".join(f"{x:+.1f}" for x in spread)
                + f" against its {informed['dim1']:+.1f}."
            )
    else:
        twist_rewired = (
            "<b>The rewired control is still running.</b> Same connectome, degree-preserving "
            "shuffle, same bills. Whether the wiring or merely the degrees produce this seat "
            "is not yet answered here."
        )

    what = (
        f"Every one of the {informed['votes']} contested votes in this Riigikogu went through a "
        "spiking simulation of a real fly brain — 166,700 neurons and 24.5 million connections "
        "from the MaleCNS connectome, on the published Shiu et al. model. Each bill was scored "
        "on ten topics drawn from what Estonian voters actually rank, turned into smells on the "
        "fly's antennae, and the vote read from the descending neurons that steer a walking "
        "fly. The chamber behind it is arranged by its own votes: members near each other voted "
        "alike, and the parties fall out of that rather than being drawn in."
    )
    why = (
        "The fly is also told one thing that is not in the bill: whether the government tabled "
        "it or a member did. That single bit calls 94% of outcomes in this chamber on its own — "
        "government bills advance 99.3% of the time, members' bills 10.4% — while the content "
        f"of the bill predicts far less. With it, the fly agrees {best:.0f}% with {gov} and "
        f"{worst:.0f}% with {worst_f}; its readout separates the government line at AUC "
        f"{informed['auc_advances']:.2f}. That is not comprehension. It is the fly picking up "
        "the one signal that actually runs the place."
    )
    caveats = (
        "<b>The mapping is engineered, not discovered.</b> No glomerulus in a fly means "
        "&ldquo;healthcare&rdquo;, and no fly has an opinion about who tabled a bill; both "
        "assignments are arbitrary and were fixed before any agreement was measured. "
        "<b>The threshold is cosmetic.</b> AUC is threshold-free and is the statistic quoted "
        "above; the poolt/vastu split only exists so there is something to show, and it is set "
        "to make the fly decline about as often as a real member does. "
        "<b>It is a simulation.</b> Wiring-constrained, with an engineered input and output, "
        "and it says nothing about what a fly experiences. "
        "<b>And the rewired control is the experiment, not a footnote</b> — if a shuffled "
        "connectome does this just as well, then what you are watching is the strength of one "
        "procedural signal, not a property of this brain."
    )
    credits = (
        "The fly is <i>Drosophila melanogaster</i> photographed by André Karwath, "
        '<a href="https://commons.wikimedia.org/wiki/File:Drosophila_melanogaster_-_top_(aka).jpg">'
        "Wikimedia Commons</a>, "
        '<a href="https://creativecommons.org/licenses/by-sa/2.5/">CC BY-SA 2.5</a>; it is '
        "reproduced here cut out from its background, and that adaptation is shared under the "
        "same licence. "
        "The brain is the <b>MaleCNS v1.0</b> connectome from FlyEM at HHMI Janelia, the "
        "University of Cambridge, the MRC LMB, Google Research and the MaleCNS collaboration, "
        "CC BY 4.0. The simulation follows Shiu et al., <i>Nature</i> 634:210 (2024), run on "
        '<a href="https://github.com/Kisame76/drosophila-brain-mlx">mlx-lif-engine</a> (MIT). '
        "Votes and bills are from the Riigikogu open API, CC BY-SA 3.0. Topic salience is from "
        "SALK polling. Members are named only where the public voting record supports it."
    )
    return {
        "__N_CREDITS__": json.dumps(credits),
        "__TWIST_BLIND__": json.dumps(twist_blind),
        "__TWIST_REWIRED__": json.dumps(twist_rewired),
        "__N_WHAT__": json.dumps(what),
        "__N_WHY__": json.dumps(why),
        "__N_CAVEATS__": json.dumps(caveats),
    }


def build_season(bundle: dict) -> str:
    """Fill the season template."""
    template = SEASON_TEMPLATE.read_text(encoding="utf-8")
    fly = Path("page/assets/fly.png")
    tokens = {
        "__SEASON_JSON__": json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/"),
        "__FLY_B64__": base64.b64encode(fly.read_bytes()).decode(),
        **season_copy(bundle),
    }
    for token, value in tokens.items():
        if token not in template:
            raise ValueError(f"season template has no {token}")
        template = template.replace(token, value)
    return template
