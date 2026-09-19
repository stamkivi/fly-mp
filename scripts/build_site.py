"""Build every page from page/sittings.json.

    uv run python scripts/build_site.py

Writes the GitHub Pages site under docs/ (index.html, one chair.html shell, data/<date>.json per
sitting) and one self-contained chair-<date>.html per sitting under runs/page/ for Display.dev.
Needs the steno cache, the recordings and the MaleCNS atlas; all three are gitignored inputs.
"""

import json
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
from karbes import atlas as A
from karbes import chairpage, landing, page, sitting
from karbes.chair import Reaction, Recording

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/stamkivi/fly-mp"
CFG = json.loads((ROOT / "page" / "sittings.json").read_text(encoding="utf-8"))
DOCS, SINGLE = ROOT / "docs", ROOT / "runs" / "page"
KEYS = (
    "stimuli",
    "fly_bells",
    "chair_order",
    "chair_bell",
    "chair_time",
    "coincide",
    "heckles",
    "hostile",
)

atlas = A.load(ROOT / "data" / "malecns")
bundles: dict[str, dict] = {}
for c in CFG:
    src = ROOT / c["steno"]
    raw = json.loads(src.read_text(encoding="utf-8"))
    start = raw[0]["agendaItems"][0]["events"][0]["date"]
    s = sitting.load(src)
    miss = sitting.attach_tone(s)
    d = json.loads((ROOT / c["recording"]).read_text(encoding="utf-8"))
    rec = Recording(
        date=d["date"],
        reactions=[Reaction(**r) for r in d["reactions"]],
        group_hz=d["group_hz"],
        raster=d["raster"],
        frame_event=d["frame_event"],
        onset=d.get("onset", []),
    )
    b = chairpage.bundle(s, rec, atlas, start)
    assert b["iso"] == c["iso"], (b["iso"], c["iso"])
    bundles[c["iso"]] = b
    print(c["iso"], "| unscored", miss, "|", {k: b["summary"][k] for k in KEYS})


def entries(href, data=None):
    out = []
    for c in CFG:
        b = bundles[c["iso"]]
        e = {
            "iso": c["iso"],
            "date": b["date"],
            "date_et": b["date_et"],
            "href": href(c),
            "summary": b["summary"],
            "default": bool(c.get("default", False)),
            "blurb_en": c.get("blurb_en", ""),
            "blurb_et": c.get("blurb_et", ""),
        }
        if data:
            e["data"] = data(c)
        out.append(e)
    return out


# the site: one shell, one data file per sitting, a landing page
site = entries(lambda c: f"chair.html?d={c['iso']}", lambda c: f"data/{c['iso']}.json")
if DOCS.exists():
    shutil.rmtree(DOCS / "data", ignore_errors=True)
(DOCS / "data").mkdir(parents=True, exist_ok=True)
for c in CFG:
    out = DOCS / "data" / f"{c['iso']}.json"
    out.write_text(
        json.dumps(chairpage.with_others(bundles[c["iso"]], site), ensure_ascii=False),
        encoding="utf-8",
    )
    print("data:", out, out.stat().st_size, "bytes")
default = next(x for x in site if x["default"])
page.write(DOCS / "chair.html", chairpage.build(bundles[default["iso"]], site, inline=False))
page.write(DOCS / "index.html", landing.build(site, REPO_URL))
(DOCS / ".nojekyll").touch()
print("site:", DOCS / "index.html", (DOCS / "chair.html").stat().st_size, "bytes shell")

# Display.dev: self-contained files that link to each other by public URL
single = entries(lambda c: c["display_url"])
for c in CFG:
    out = page.write(
        SINGLE / f"chair-{c['iso']}.html", chairpage.build(bundles[c["iso"]], single, inline=True)
    )
    Path(str(out) + ".summary.json").write_text(
        json.dumps(bundles[c["iso"]]["summary"]), encoding="utf-8"
    )
    print("single:", out, out.stat().st_size, "bytes")
