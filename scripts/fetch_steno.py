"""Every plenary sitting's verbatim record for the term. Cache-first, atomic, resumable, and no
more than 12 requests a minute on this endpoint path, which is the binding limit."""
import json, logging, time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)
cal = json.load(open("data/raw/meta/events_calendar_term.json"))
days = [d["date"] for d in cal if str(d.get("hasEvents")).lower() == "true"]
out = Path("data/raw/steno"); out.mkdir(exist_ok=True)
todo = [d for d in days if not (out / f"{d}.json").exists()]
logging.info("%d days with events, %d not yet cached", len(days), len(todo))
with httpx.Client(timeout=90) as c:
    for i, d in enumerate(todo, 1):
        for attempt in range(4):
            try:
                r = c.get(f"https://api.riigikogu.ee/api/steno/verbatims?startDate={d}&endDate={d}&lang=et")
                if r.status_code == 429:
                    time.sleep(60); continue
                r.raise_for_status(); break
            except httpx.HTTPError as exc:
                logging.warning("%s: %s (attempt %d)", d, exc, attempt + 1); time.sleep(15 * (attempt + 1))
        else:
            continue
        tmp = out / f"{d}.json.tmp"; tmp.write_text(r.text, encoding="utf-8"); tmp.replace(out / f"{d}.json")
        if i % 25 == 0:
            logging.info("%d/%d (%s)", i, len(todo), d)
        time.sleep(5.1)
logging.info("steno fetch done")
