"""The chorus page: twenty brains on the Estonian political compass.

The season page asked whether the fly votes like the chamber and answered no — a sixteen-
parameter logistic regression on the same scores beats it, and the degree-preserving
shuffles beat it too. That retired accuracy as the question. What the shuffles did *not*
do was land in the same place: three of them produced three different politicians, which
is the one thing a connectome can demonstrate and a regression cannot.

So this page makes that the subject. Its claim is conditional and the copy below is
generated from the measurements rather than written ahead of them: the separation between
wirings only means something if it is larger than the separation between two runs of the
*same* wiring, and that control is on the same page with the same fitting.
"""

from __future__ import annotations

import base64
import html
import json
import logging
import math
from pathlib import Path

log = logging.getLogger(__name__)

TEMPLATE = Path("page/compass.html")
BRAIN = Path("page/assets/brain.jpg")
FLY = Path("page/assets/fly.png")


def _fmt(x: float, n: int = 2) -> str:
    return f"{x:.{n}f}"


#: The headline counts the brains that finished, so a run that loses one does not ship a
#: title claiming otherwise.
_WORDS = {
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
    11: "Eleven",
    12: "Twelve",
    13: "Thirteen",
    14: "Fourteen",
    15: "Fifteen",
    16: "Sixteen",
    17: "Seventeen",
    18: "Eighteen",
    19: "Nineteen",
    20: "Twenty",
    21: "Twenty-one",
    22: "Twenty-two",
    23: "Twenty-three",
    24: "Twenty-four",
}


def copy(bundle: dict) -> dict[str, str]:
    """Every sentence on the page that quotes a number, written from the numbers."""
    within = bundle["within_brain_spread"] or math.nan
    across = bundle["across_wiring_spread"] or math.nan
    spacing = bundle["party_spacing"]
    flies = bundle["flies"]
    real = [f for f in flies if f["kind"] == "real"]
    rewired = [f for f in flies if f["kind"] == "rewired"]
    karbes = next(f for f in real if f["name"] == "karbes")
    ex, ey = bundle["axis_error"]
    base = bundle.get("baseline") or {}

    def shuffle_name(raw: str | None) -> str:
        return "shuffle " + (raw or "").replace("rewired", "").rjust(2, "0") if raw else "—"

    pn = bundle.get("partisanship") or {}
    partisan = (
        f"There is a reason it scores badly, and it is not modesty. Across the rewirings, the "
        f"further a brain lands from the middle of the chamber the better it predicts which "
        f"bills advance (r = {_fmt(pn['r'])}). Being a good predictor of this parliament means "
        f"having picked a side in it. Kärbes lands {_fmt(pn['karbes_from_midline'])} from the "
        f"midline — it has not picked one, and it predicts accordingly."
        if pn
        else ""
    )

    ty = bundle.get("typicality") or {}
    typical = ""
    if ty:
        pct = ty["percentile"]
        where = (
            "further from the centre of that cloud than most of them"
            if pct >= 0.6
            else "nearer the centre of that cloud than most of them"
            if pct <= 0.4
            else "at an unremarkable distance from the centre of that cloud"
        )
        typical = (
            f"The measured connectome sits {_fmt(ty['karbes_from_centre'])} compass units "
            f"from the middle of its own shuffles, which average "
            f"{_fmt(ty['shuffles_from_centre'])} — {where}. It is one politician among them, "
            f"not a distinguished one. What a connectome buys is a particular individual, "
            f"reproducibly. It does not buy a privileged one."
        )

    pb = bundle.get("per_bill") or {}
    per_bill = (
        f"On any one bill it is close to a coin flip: re-run, the fly lands on the same side "
        f"of {int(pb['bills'])} bills only {_fmt(100 * pb['same_side'], 0)}% of the time "
        f"(correlation r = {_fmt(pb['r'])}). The individual votes are noise. The record of "
        f"{html.escape(str(karbes['votes']))} of them is not."
        if pb
        else ""
    )

    rows = []
    for r in bundle.get("split") or []:
        who = "government" if r["government"] else "a member or committee"
        rows.append(
            '<li><span class="vs"><b>{a}</b> / <b>{b}</b></span>'
            '<span class="what">{ch}<i>{title}</i>'
            "<u>{when} · tabled by {who}</u></span></li>".format(
                a=html.escape(r["a"]),
                b=html.escape(r["b"]),
                ch=html.escape(r["channel"] or "unscored"),
                title=html.escape(r["title"] or "untitled"),
                when=html.escape(r["when"]),
                who=who,
            )
        )

    ratio = across / within if not math.isnan(within) and within > 0 else math.nan
    pv = bundle.get("permutation_p")
    chance = (
        f" Relabelling at random which brains count as the reruns gives a ratio at least "
        f"this large in {_fmt(100 * pv, 1)}% of 20,000 draws."
        if pv
        else ""
    )
    if not math.isnan(ratio) and ratio >= 2:
        verdict = (
            f"Rewiring moves a fly {_fmt(ratio, 1)} times further than re-running the same "
            f"brain does. The scatter is the wiring, not the noise.{chance}"
        )
    elif not math.isnan(ratio) and ratio >= 1.2:
        verdict = (
            f"Rewiring moves a fly {_fmt(ratio, 1)} times further than re-running the same "
            f"brain does. That is a real difference and a modest one: the wiring shifts the "
            f"seat, but a rerun of one brain is not a fixed point either.{chance}"
        )
    elif math.isnan(within):
        # The within-brain control has not finished. Say that, rather than print a ratio.
        verdict = (
            f"They spread {_fmt(across)} compass units apart. Whether that is the wiring or "
            f"the readout's own noise is not decided until the same brain has been run twice, "
            f"which is the next panel."
        )
    else:
        verdict = (
            f"Re-running one brain moves it {_fmt(within)} units; rewiring it moves it "
            f"{_fmt(across)}. Those are the same number. On this evidence the scatter across "
            f"wirings is the readout's own noise, and the pre-registered claim fails."
        )

    return {
        # Escaped for text, not for an attribute: the verdict lands inside a <p>,
        # and escaping quotes there turns every apostrophe into mojibake.
        "__HEAD_VERDICT__": html.escape(verdict, quote=False),
        "__N_REWIRED__": str(len(rewired)),
        "__N_WORD__": _WORDS.get(len(rewired), str(len(rewired))),
        "__N_WORD_LOWER__": _WORDS.get(len(rewired), str(len(rewired))).lower(),
        "__N_REAL__": str(len(real)),
        "__N_BILLS__": str(karbes["votes"]),
        "__KARBES_PARTY__": html.escape(karbes["nearest_party"]),
        "__KARBES_AUC__": _fmt(karbes["auc_advances"], 3),
        "__WITHIN__": "—" if math.isnan(within) else _fmt(within),
        "__PER_BILL__": per_bill,
        "__TYPICAL__": typical,
        "__PARTISAN__": partisan,
        "__ACROSS__": _fmt(across),
        "__SPACING__": _fmt(spacing),
        "__ERR_X__": _fmt(ex),
        "__ERR_Y__": _fmt(ey),
        "__RANGE_X__": _fmt(bundle["axis_range"][0]),
        "__RANGE_Y__": _fmt(bundle["axis_range"][1]),
        "__N_MEMBERS__": str(len(bundle["members"])),
        "__PARTIES_HIT__": html.escape(", ".join(sorted({f["nearest_party"] for f in rewired}))),
        "__AUC_REG__": _fmt(base.get("content + who tabled it", float("nan")), 3),
        "__AUC_BIT__": _fmt(base.get("who tabled it alone", float("nan")), 3),
        "__AUC_CONTENT__": _fmt(base.get("content only", float("nan")), 3),
        "__AUC_BEST_FLY__": _fmt(max(f["auc_advances"] for f in flies), 3),
        "__RATIO__": "—" if math.isnan(ratio) else _fmt(ratio, 1),
        "__FURTHEST__": html.escape(shuffle_name(bundle.get("furthest"))),
        "__SHUFFLE_RERUN__": (
            f"One of the shuffles was itself re-run under new input noise; those runs sit "
            f"{_fmt(bundle['within_shuffle_spread'])} apart, so a rewiring is an individual "
            f"rather than a fresh draw each time it is asked."
            if bundle.get("within_shuffle_spread")
            else ""
        ),
        "__SPLIT_ROWS__": "\n".join(rows) or "<li>no clean disagreement yet</li>",
    }


def build(bundle: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    tokens = {
        "__CHORUS_JSON__": json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/"),
        "__BRAIN_B64__": base64.b64encode(BRAIN.read_bytes()).decode(),
        "__FLY_B64__": base64.b64encode(FLY.read_bytes()).decode(),
        **copy(bundle),
    }
    for token, value in tokens.items():
        if token not in template:
            raise ValueError(f"compass template has no {token}")
        template = template.replace(token, value)
    return template
