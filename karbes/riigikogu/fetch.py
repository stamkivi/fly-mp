"""Rate-limited, resumable Riigikogu API client.

The API allows 1 request/second per IP *and* 12 requests/minute per endpoint path.
The per-path limit is the binding one: a naive sleep(1) satisfies the global limit and
violates the path limit by 5x. Both are enforced here.

Everything is cached by UUID and never refetched. Cache writes are atomic, because a
process killed mid-write otherwise leaves a truncated file that parses as valid-but-
incomplete on the next run.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Self

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.riigikogu.ee"
GLOBAL_MIN_INTERVAL = 1.05  # seconds between any two requests (limit: 1/s)
PER_PATH_MAX = 12  # requests per minute per endpoint path
PER_PATH_WINDOW = 60.0
MAX_ATTEMPTS = 4


class RateLimiter:
    """Global 1/s gate plus a per-path sliding window of 12/minute."""

    def __init__(
        self,
        global_interval: float = GLOBAL_MIN_INTERVAL,
        per_path_max: int = PER_PATH_MAX,
        window: float = PER_PATH_WINDOW,
    ) -> None:
        self.global_interval = global_interval
        self.per_path_max = per_path_max
        self.window = window
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._path_hits: dict[str, deque[float]] = {}

    def acquire(self, path_key: str) -> None:
        """Block until a request to `path_key` is allowed under both limits."""
        while True:
            with self._lock:
                now = time.monotonic()
                hits = self._path_hits.setdefault(path_key, deque())
                while hits and now - hits[0] >= self.window:
                    hits.popleft()

                wait_global = self._last_request + self.global_interval - now
                wait_path = hits[0] + self.window - now if len(hits) >= self.per_path_max else 0.0
                wait = max(wait_global, wait_path, 0.0)

                if wait <= 0:
                    self._last_request = now
                    hits.append(now)
                    return
            time.sleep(min(wait, 5.0))


def path_key(url: str) -> str:
    """Collapse a URL to its endpoint *template*, so /votings/{uuid} shares one budget.

    The docs are ambiguous about whether the 12/min limit is per template or per distinct
    URL; the conservative reading is per template, which is what we assume.
    """
    path = url.split("?", 1)[0].removeprefix(BASE).strip("/")
    parts = []
    for part in path.split("/"):
        # UUIDs and bare numbers are identifiers, not distinct endpoints.
        if len(part) == 36 and part.count("-") == 4:
            parts.append("{id}")
        elif part.isdigit():
            parts.append("{n}")
        else:
            parts.append(part)
    return "/".join(parts)


class Cache:
    """Content-addressed JSON cache. Writes are atomic; reads never hit the network."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.hits = 0
        self.misses = 0

    def _path(self, kind: str, key: str) -> Path:
        return self.root / kind / f"{key}.json"

    def get(self, kind: str, key: str) -> Any | None:
        p = self._path(kind, key)
        if not p.exists():
            return None
        try:
            with p.open(encoding="utf-8") as fh:
                value = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            # A truncated entry from an interrupted run. Treat as a miss and refetch.
            log.warning("discarding corrupt cache entry %s: %s", p, exc)
            p.unlink(missing_ok=True)
            return None
        self.hits += 1
        return value

    def put(self, kind: str, key: str, value: Any) -> None:
        p = self._path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False)
        os.replace(tmp, p)


class Client:
    """Fetches Riigikogu resources, preferring the cache and honouring both rate limits."""

    def __init__(self, cache: Cache, limiter: RateLimiter | None = None) -> None:
        self.cache = cache
        self.limiter = limiter or RateLimiter()
        self.http = httpx.Client(timeout=60.0, headers={"Accept": "application/json"})
        self.gaps: dict[str, str] = {}
        self.requests_made = 0

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, url: str, params: dict[str, str] | None = None) -> Any:
        key = path_key(url)
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            self.limiter.acquire(key)
            try:
                resp = self.http.get(url, params=params)
                self.requests_made += 1
                if resp.status_code == 429:
                    delay = float(resp.headers.get("Retry-After", 2**attempt))
                    log.warning("429 on %s, sleeping %.1fs", key, delay)
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_exc = exc
                backoff = 2**attempt
                log.warning(
                    "%s on %s (attempt %d/%d), retrying in %ds",
                    type(exc).__name__,
                    key,
                    attempt + 1,
                    MAX_ATTEMPTS,
                    backoff,
                )
                time.sleep(backoff)
        raise RuntimeError(f"giving up on {url}") from last_exc

    def _cached(self, kind: str, key: str, url: str) -> Any | None:
        """Fetch `url` unless cached. A persistent failure is recorded as a gap, not a crash."""
        hit = self.cache.get(kind, key)
        if hit is not None:
            return hit
        self.cache.misses += 1
        try:
            value = self._request(url)
        except RuntimeError as exc:
            log.error("gap: %s %s -> %s", kind, key, exc)
            self.gaps[f"{kind}/{key}"] = str(exc)
            return None
        self.cache.put(kind, key, value)
        return value

    # -- resources -------------------------------------------------------------

    def votings_in_range(self, start: str, end: str) -> list[dict]:
        """Sittings with their votings nested. Cached per date range."""
        key = f"{start}_{end}"
        cached = self.cache.get("votings_range", key)
        if cached is not None:
            return cached
        self.cache.misses += 1
        value = self._request(
            f"{BASE}/api/votings", params={"startDate": start, "endDate": end, "lang": "et"}
        )
        self.cache.put("votings_range", key, value)
        return value

    def voting(self, uuid: str) -> dict | None:
        """One voting with all 101 members' decisions and their factions at that vote."""
        return self._cached("voting", uuid, f"{BASE}/api/votings/{uuid}?lang=et")

    def draft(self, uuid: str) -> dict | None:
        """A bill dossier, including the plain-text `introduction` and subject descriptors."""
        return self._cached("draft", uuid, f"{BASE}/api/volumes/drafts/{uuid}?lang=et")

    def hallplan(self) -> list[dict] | None:
        """The 101 occupied seats, with faction shortName and colorHex."""
        return self._cached("meta", "hallplan", f"{BASE}/api/hallplan?lang=et")
