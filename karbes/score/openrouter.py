"""Cached OpenRouter client for bill scoring.

Two things here matter beyond plumbing:

`provider: {require_parameters: true}` is sent on every call. Structured-output support on
OpenRouter is per *provider endpoint*, not per model, so without it a request can silently
route to a provider that ignores the JSON schema and returns prose.

A bill that fails to score is recorded as failed and excluded. It is never defaulted to a
zero vector — a rubric failure that quietly becomes "neutral on everything" produces a
confident, plausible, meaningless voting record with nothing to flag it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import httpx

log = logging.getLogger(__name__)

BASE = "https://openrouter.ai/api/v1"
MAX_ATTEMPTS = 4


class MissingKey(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        env = Path(".env")
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not key:
        raise MissingKey(
            "OPENROUTER_API_KEY is not set. Put it in the environment or in .env "
            "(see .env.example); it is never passed on the command line."
        )
    return key


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0

    def add(self, u: dict) -> None:
        self.calls += 1
        self.prompt_tokens += int(u.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(u.get("completion_tokens", 0) or 0)
        self.cost += float(u.get("cost", 0) or 0)


@dataclass
class Scorer:
    """Scores prompts against one model, caching every response on disk."""

    model: str
    cache_root: Path
    temperature: float = 0.0
    usage: Usage = field(default_factory=Usage)
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

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _key(self, system: str, user: str, tag: str) -> str:
        blob = json.dumps([self.model, self.temperature, system, user, tag], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def _cache_path(self, key: str) -> Path:
        return self.cache_root / "llm" / f"{key}.json"

    def _post(self, payload: dict) -> dict:
        assert self._client is not None
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                r = self._client.post(f"{BASE}/chat/completions", json=payload)
                if r.status_code == 429:
                    delay = float(r.headers.get("Retry-After", 2**attempt))
                    log.warning("429, sleeping %.1fs", delay)
                    time.sleep(delay)
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last = exc
                body = ""
                if isinstance(exc, httpx.HTTPStatusError):
                    body = exc.response.text[:300]
                    code = exc.response.status_code
                    if 400 <= code < 500 and code != 429:
                        # A rejected request fails identically on retry.
                        raise RuntimeError(f"{code}: {body}") from exc
                log.warning(
                    "%s (attempt %d/%d) %s", type(exc).__name__, attempt + 1, MAX_ATTEMPTS, body
                )
                time.sleep(2**attempt)
        raise RuntimeError(f"OpenRouter call failed: {last}")

    def complete(
        self,
        system: str,
        user: str,
        schema: dict | None = None,
        tag: str = "",
        max_tokens: int = 700,
    ) -> Any | None:
        """Return parsed JSON (with `schema`) or text. None means the call failed."""
        key = self._key(system, user, tag)
        path = self._cache_path(key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))["value"]
            except (json.JSONDecodeError, KeyError, OSError):
                path.unlink(missing_ok=True)

        supports = supported_parameters(self.model)
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            # Schema support is per provider endpoint, not per model.
            "provider": {"require_parameters": True},
        }
        # Only send parameters the model accepts; an unsupported one plus
        # require_parameters leaves no eligible endpoint and the call 404s.
        if "temperature" in supports:
            payload["temperature"] = self.temperature
        elif self.temperature:
            log.debug("%s ignores temperature; sampling variation unavailable", self.model)
        if "reasoning" in supports:
            # Reasoning tokens are billed against max_tokens, so a reasoning model can
            # spend the whole budget thinking and return content: null. Keep effort low
            # and leave headroom — this is a classification task, not a puzzle.
            payload["reasoning"] = {"effort": "low"}
            payload["max_tokens"] = max(max_tokens, 4000)
        if schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": schema}

        try:
            resp = self._post(payload)
        except RuntimeError as exc:
            self.failures[tag or key] = str(exc)
            return None

        self.usage.add(resp.get("usage") or {})
        try:
            choice = resp["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError) as exc:
            self.failures[tag or key] = f"malformed response: {exc}"
            return None
        if not content:
            # Empty content usually means the token budget went entirely on reasoning,
            # or the provider truncated. Record it; never fabricate a score.
            reason = choice.get("finish_reason") or choice.get("native_finish_reason")
            self.failures[tag or key] = f"empty content (finish_reason={reason})"
            return None

        value: Any = content
        if schema:
            try:
                value = json.loads(content)
            except json.JSONDecodeError:
                # Some providers wrap JSON in prose or fences despite the schema.
                cleaned = content.strip().removeprefix("```json").removeprefix("```")
                cleaned = cleaned.removesuffix("```").strip()
                start, end = cleaned.find("{"), cleaned.rfind("}")
                if start == -1 or end == -1:
                    self.failures[tag or key] = "no JSON object in response"
                    return None
                try:
                    value = json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError as exc:
                    self.failures[tag or key] = f"unparseable JSON: {exc}"
                    return None

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"model": self.model, "value": value}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return value


_CATALOGUE: dict[str, dict] | None = None


def catalogue() -> dict[str, dict]:
    """The public model catalogue, fetched once. No key required."""
    global _CATALOGUE
    if _CATALOGUE is None:
        r = httpx.get(f"{BASE}/models", timeout=60.0)
        r.raise_for_status()
        _CATALOGUE = {m["id"]: m for m in r.json()["data"]}
    return _CATALOGUE


def supported_parameters(model: str) -> set[str]:
    """What a model will actually accept.

    Sending an unsupported parameter alongside `require_parameters: true` filters out every
    endpoint and the request 404s — GPT-5 models reject `temperature`, for instance. The
    404 is the guard working as intended, so the fix is to send only what fits.
    """
    m = catalogue().get(model)
    return set(m.get("supported_parameters") or []) if m else set()


def resolve_models(prefer: list[str]) -> list[dict]:
    """Look up live pricing for candidate slugs so nothing is hardcoded in the manifest."""
    r = httpx.get(f"{BASE}/models", timeout=60.0)
    r.raise_for_status()
    by_id = {m["id"]: m for m in r.json()["data"]}
    out = []
    for slug in prefer:
        m = by_id.get(slug)
        if not m:
            log.warning("model %s is not in the catalogue", slug)
            continue
        p = m.get("pricing", {})
        out.append(
            {
                "id": slug,
                "prompt_per_m": round(float(p.get("prompt", 0)) * 1e6, 4),
                "completion_per_m": round(float(p.get("completion", 0)) * 1e6, 4),
                "context": m.get("context_length"),
            }
        )
    return out
