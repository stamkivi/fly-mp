"""Record one sitting: score every speech's tone (cached), then play it to the brain.

uv run python scripts/record_sitting.py <steno.json> <out.json> [pinpricks]
"""

import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("karbes.scripts")
from karbes import atlas as A
from karbes import chair, sitting
from karbes import engine as E
from karbes.graph import populations as P
from karbes.tone import ToneCache

src, out = Path(sys.argv[1]), Path(sys.argv[2])
if len(sys.argv) > 3:
    chair.PINPRICKS = int(sys.argv[3])
raw = json.loads(src.read_text(encoding="utf-8"))
full = [
    e["text"]
    for sit in raw
    for ai in sit["agendaItems"]
    for e in ai["events"]
    if e["type"] == "SPEECH"
    and e.get("text")
    and not e["speaker"].startswith(("Esimees", "Aseesimees"))
]
tc = ToneCache(Path("data/raw"))
tc.score_all(full)
log.info("tone: %d speeches, %d live calls", len(full), tc.calls)
s = sitting.load(src)
miss = sitting.attach_tone(s)
log.info(
    "%s: %d events, %d stimuli, %d unscored, %.0f min span, %.0f s bio",
    s.date,
    len(s.events),
    len(s.stimuli),
    miss,
    (s.events[-1].t - s.events[0].t) / 60,
    sum(e.bio + 0.15 for e in s.events if e.bio),
)
eng = E.load()
pops = P.load(Path("data/malecns"))
atl = A.load(Path("data/malecns"))
bias = json.loads(Path("runs/calibration.json").read_text())["baseline_bias"]
t0 = time.time()
rec = chair.record(s, eng, pops, atl, bias)
chair.save(rec, out)
log.info(
    "done: %d reactions, %d frames, %.1f min -> %s",
    len(rec.reactions),
    len(rec.raster),
    (time.time() - t0) / 60,
    out,
)
