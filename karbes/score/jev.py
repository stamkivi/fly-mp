"""TypeSafe Jev scorer: typed decisions with calibrated confidence.

Chosen over a general LLM after a head-to-head on real bills. Three reasons, in order of
importance to this project:

1. **Per-channel calibrated confidence.** Stage 1's failure mode was that two LLMs
   disagreed on abstract channels and nothing in the output said so. Jev states its own
   uncertainty per question — `place` came back 0.99 confident on a nuclear bill (correctly:
   it is not a geographic bill) and `who_decides` 0.26 (honestly unsure). That lets ORN drive
   be weighted by confidence instead of treating every channel as equally trustworthy.
2. **Self-consistency.** Repeat calls differ by a mean of 0.039 on a [-1,1] scale.
3. **Cost and latency.** ~$0.05 for the full 784-bill corpus against $0.90 for the LLM pass,
   and ~700 ms for nine questions in one call.

Spot checks were semantically right where it matters: a VAT cut scores `pay` -0.76, the
weapons act scores `security` +0.90 with everything else near zero.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from karbes.riigikogu.model import Bill
from karbes.score import rubric2

log = logging.getLogger(__name__)

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
MAX_ATTEMPTS = 4

#: Five ordered levels, so a score of 0-4 maps linearly onto [-1, +1].
LEVELS = (
    "strongly lowers / reduces",
    "slightly lowers",
    "does not change this",
    "slightly raises",
    "strongly raises / increases",
)
SALIENCE_LEVELS = (
    "pure housekeeping: renumbering, cross-references, a shifted deadline",
    "minor technical change",
    "moderate policy change",
    "significant policy change",
    "central political controversy",
)


class MissingKey(RuntimeError):
    pass


def api_key() -> str:
    """Environment first, then the project's gitignored `.env`.

    `.env` is in .gitignore and never committed, so the key stays local without depending
    on a file outside the project.
    """
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        env = Path(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("TYPESAFE_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not key:
        raise MissingKey(
            "TYPESAFE_API_KEY is not set. Put it in .env (gitignored) as\n"
            "  TYPESAFE_API_KEY=..."
        )
    return key


def questions() -> dict:
    qs = {
        k: {
            "type": "score",
            "instructions": f"{q} Negative means: {neg}. Positive means: {pos}.",
            "criteria": list(LEVELS),
        }
        for k, q, neg, pos in rubric2.QUESTIONS
    }
    qs["salience"] = {
        "type": "score",
        "instructions": "How much does this bill actually change?",
        "criteria": list(SALIENCE_LEVELS),
    }
    return qs


@dataclass
class Scored:
    scores: dict[str, float]  # channel -> [-1, +1]
    confidence: dict[str, float]  # channel -> [0, 1]
    input_tokens: int

    def drive_weight(self, channel: str) -> float:
        """Confidence-weighted magnitude: an uncertain channel drives the fly weakly."""
        return self.scores.get(channel, 0.0) * self.confidence.get(channel, 0.0)


@dataclass
class JevScorer:
    cache_root: Path
    usage_tokens: int = 0
    calls: int = 0
    failures: dict[str, str] = field(default_factory=dict)
    _client: httpx.Client | None = None

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _path(self, bill: Bill, qs: dict) -> Path:
        h = hashlib.sha256(
            json.dumps(
                [MODEL, qs, rubric2.bill_prompt(bill)], sort_keys=True, ensure_ascii=False
            ).encode()
        ).hexdigest()[:32]
        return self.cache_root / "jev" / f"{h}.json"

    def score(self, bill: Bill) -> Scored | None:
        qs = questions()
        path = self._path(bill, qs)
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                return Scored(d["scores"], d["confidence"], d["input_tokens"])
            except (json.JSONDecodeError, KeyError):
                path.unlink(missing_ok=True)

        payload = {"state": rubric2.bill_prompt(bill), "model": MODEL, "questions": qs}
        assert self._client is not None
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                r = self._client.post(ENDPOINT, json=payload)
                if r.status_code in (429, 529):
                    time.sleep(2**attempt)
                    continue
                r.raise_for_status()
                d = r.json()
                break
            except httpx.HTTPError as exc:
                last = exc
                # A rejected request fails identically on retry; only back off on 429.
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and 400 <= exc.response.status_code < 500
                    and exc.response.status_code != 429
                ):
                    self.failures[bill.uuid] = (
                        f"{exc.response.status_code}: {exc.response.text[:200]}"
                    )
                    return None
                time.sleep(2**attempt)
        else:
            self.failures[bill.uuid] = f"gave up: {last}"
            return None

        answers = d.get("answers") or {}
        try:
            # Levels are 0-4; centre and rescale to [-1, +1]. Salience stays [0, 1].
            scores, conf = {}, {}
            for k, a in answers.items():
                raw = float(a["score"])
                scores[k] = raw / 4.0 if k == "salience" else (raw - 2.0) / 2.0
                conf[k] = float(a.get("confidence", 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            self.failures[bill.uuid] = f"bad answer shape: {exc}"
            return None

        tokens = int((d.get("usage") or {}).get("input_tokens", 0))
        self.usage_tokens += tokens
        self.calls += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {"scores": scores, "confidence": conf, "input_tokens": tokens}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return Scored(scores, conf, tokens)

    @property
    def cost_usd(self) -> float:
        return self.usage_tokens * 0.042 / 1e6
