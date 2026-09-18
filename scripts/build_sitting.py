"""Build the chair page for one recorded sitting.

    uv run python scripts/build_sitting.py <steno.json> <recording.json> <out.html> [others.json]

`others.json` maps a date label to {"url": ..., "summary": ...} for the cross-links.
"""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
from karbes import atlas as A
from karbes import chairpage, page, sitting
from karbes.chair import Reaction, Recording

src, recp, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
others = json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None
raw = json.loads(src.read_text(encoding="utf-8"))
start = raw[0]["agendaItems"][0]["events"][0]["date"]
s = sitting.load(src)
miss = sitting.attach_tone(s)
d = json.loads(recp.read_text(encoding="utf-8"))
rec = Recording(
    date=d["date"],
    reactions=[Reaction(**r) for r in d["reactions"]],
    group_hz=d["group_hz"],
    raster=d["raster"],
    frame_event=d["frame_event"],
    onset=d.get("onset", []),
)
b = chairpage.bundle(s, rec, A.load(Path("data/malecns")), start)
print(
    s.date,
    "| unscored",
    miss,
    "|",
    {
        k: b["summary"][k]
        for k in (
            "stimuli",
            "fly_bells",
            "chair_order",
            "chair_bell",
            "chair_time",
            "coincide",
            "heckles",
            "hostile",
            "bio_seconds",
        )
    },
)
for k, v in b["summary"]["by_kind"].items():
    print(f"   {k:15s} n={v['n']:4d} GF {v['gf']:6.1f} bells {v['bells']}")
page.write(out, chairpage.build(b, others))
Path(str(out) + ".summary.json").write_text(json.dumps(b["summary"]), encoding="utf-8")
print("bytes:", out.stat().st_size)
