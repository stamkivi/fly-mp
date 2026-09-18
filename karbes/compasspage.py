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

    ratio = across / within if not math.isnan(within) and within > 0 else math.nan
    pv = bundle.get("permutation_p")
    chance = (
        f" Relabelling which brains count as the reruns gives a ratio this large in "
        f"{_fmt(100 * pv, 1)}% of {int(1 / max(pv, 1e-9)):,} draws." if pv else ""
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
        "__HEAD_VERDICT__": html.escape(verdict),
        "__N_REWIRED__": str(len(rewired)),
        "__N_REAL__": str(len(real)),
        "__N_BILLS__": str(karbes["votes"]),
        "__KARBES_PARTY__": html.escape(karbes["nearest_party"]),
        "__KARBES_AUC__": _fmt(karbes["auc_advances"], 3),
        "__WITHIN__": "—" if math.isnan(within) else _fmt(within),
        "__ACROSS__": _fmt(across),
        "__SPACING__": _fmt(spacing),
        "__ERR_X__": _fmt(ex),
        "__ERR_Y__": _fmt(ey),
        "__N_MEMBERS__": str(len(bundle["members"])),
        "__PARTIES_HIT__": html.escape(
            ", ".join(sorted({f["nearest_party"] for f in rewired}))
        ),
        "__AUC_REG__": _fmt(base.get("content + who tabled it", float("nan")), 3),
        "__AUC_BIT__": _fmt(base.get("who tabled it alone", float("nan")), 3),
        "__AUC_CONTENT__": _fmt(base.get("content only", float("nan")), 3),
        "__AUC_BEST_FLY__": _fmt(max(f["auc_advances"] for f in flies), 3),
        "__RATIO__": "—" if math.isnan(ratio) else _fmt(ratio, 1),
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
