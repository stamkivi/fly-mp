"""How a speech treats the people it addresses, scored once and cached forever.

This is the only place a language model enters iteration 5, and it enters as a sensory
transducer for one quantity, not as a judge of anything. Jev answers one five-level
question about a speech — from openly insulting to constructive — with a calibrated
confidence. What the fly does with it is a matter for the connectome.

Validated where the record allows: the most confident "openly insulting" on 20 May 2026,
0.09 at 0.92, was the speech the chair reprimanded minutes later.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import httpx

from karbes.score.jev import ENDPOINT, MAX_ATTEMPTS, MODEL, api_key

log = logging.getLogger(__name__)

QUESTION = {
    "tone": {
        "type": "score",
        "instructions": "How does this speaker treat the people they are addressing or discussing?",
        "criteria": [
            "openly insulting or contemptuous",
            "hostile or accusatory",
            "neutral, procedural",
            "respectful and engaged",
            "constructive: proposes, credits others, seeks agreement",
        ],
    }
}
MIN_WORDS = 5
MAX_CHARS = 3000


def key(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:32]


def hostility(score: float, confidence: float) -> float:
    """[0, 1]: how much of a threat this speech is, as the fly will receive it.

    Levels 0-4 centre at 2 ("neutral, procedural"). Anything at or above neutral is no
    threat at all; below it, the distance from neutral times the confidence.
    """
    return max(0.0, (2.0 - score) / 2.0) * confidence


class ToneCache:
    def __init__(self, root: Path):
        self.dir = root / "jev_tone"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0

    def get(self, text: str) -> dict | None:
        p = self.dir / f"{key(text)}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def score_all(self, texts: list[str]) -> dict[str, dict]:
        """Score every text not yet cached. Returns key -> {score, confidence}."""
        out: dict[str, dict] = {}
        todo = []
        for t in texts:
            if len(t.split()) < MIN_WORDS:
                continue
            k = key(t)
            got = self.get(t)
            if got:
                out[k] = got
            else:
                todo.append((k, t))
        if not todo:
            return out
        log.info("tone: %d cached, %d to score", len(out), len(todo))
        with httpx.Client(timeout=120, headers={"Authorization": f"Bearer {api_key()}"}) as c:
            for i, (k, t) in enumerate(todo, 1):
                d = None
                for attempt in range(MAX_ATTEMPTS):
                    try:
                        r = c.post(ENDPOINT, json={"state": t[:MAX_CHARS], "model": MODEL, "questions": QUESTION})
                        if r.status_code in (429, 529):
                            time.sleep(2**attempt)
                            continue
                        r.raise_for_status()
                        d = r.json()
                        break
                    except httpx.HTTPError as exc:
                        log.warning("tone: %s", exc)
                        time.sleep(2**attempt)
                if not d:
                    continue
                a = (d.get("answers") or {}).get("tone")
                if not a or "score" not in a or "confidence" not in a:
                    continue  # never invent a neutral score for a failed call
                rec = {"score": float(a["score"]), "confidence": float(a["confidence"])}
                tmp = self.dir / f"{k}.json.tmp"
                tmp.write_text(json.dumps(rec), encoding="utf-8")
                os.replace(tmp, self.dir / f"{k}.json")
                out[k] = rec
                self.calls += 1
                if i % 50 == 0:
                    log.info("tone: %d/%d", i, len(todo))
        return out
