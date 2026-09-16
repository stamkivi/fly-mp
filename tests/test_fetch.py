"""The fetcher's job is to be a good citizen and to never corrupt its own evidence base."""

from __future__ import annotations

import json
import time

import pytest

from karbes.riigikogu.fetch import Cache, RateLimiter, path_key


def test_path_key_collapses_identifiers():
    """UUIDs are identifiers, not distinct endpoints — they must share one budget."""
    a = path_key(
        "https://api.riigikogu.ee/api/votings/549c7f02-28a9-4a26-860f-0a62802c704e?lang=et"
    )
    b = path_key("https://api.riigikogu.ee/api/votings/679eeee7-62b9-4817-a660-745e6642a8d9")
    assert a == b == "api/votings/{id}"
    assert path_key("https://api.riigikogu.ee/api/votings?startDate=x") == "api/votings"


def test_rate_limiter_enforces_per_path_window():
    """A naive sleep(1) satisfies the global limit and violates the path limit by 5x."""
    rl = RateLimiter(global_interval=0.0, per_path_max=3, window=1.0)
    start = time.monotonic()
    for _ in range(7):
        rl.acquire("api/votings/{id}")
    # 7 requests at 3 per 1s window cannot complete in under 2 windows.
    assert time.monotonic() - start >= 2.0


def test_rate_limiter_paths_have_independent_budgets():
    """Interleaving two paths is what halves the harvest; it must not share a budget."""
    rl = RateLimiter(global_interval=0.0, per_path_max=2, window=5.0)
    start = time.monotonic()
    for _ in range(2):
        rl.acquire("api/votings/{id}")
        rl.acquire("api/volumes/drafts/{id}")
    assert time.monotonic() - start < 0.5


def test_rate_limiter_enforces_global_gate():
    rl = RateLimiter(global_interval=0.2, per_path_max=100, window=60.0)
    start = time.monotonic()
    for i in range(4):
        rl.acquire(f"path{i}")
    assert time.monotonic() - start >= 0.6


def test_cache_roundtrip_preserves_estonian(tmp_path):
    cache = Cache(tmp_path)
    payload = {"title": "Kriisiolukorra ja riigikaitse seadus", "kind": "Lõpphääletus"}
    cache.put("draft", "abc", payload)
    assert cache.get("draft", "abc") == payload


def test_cache_write_is_atomic(tmp_path):
    """No .tmp file survives a completed write, and no partial file is ever visible."""
    cache = Cache(tmp_path)
    cache.put("voting", "x", {"a": 1})
    assert not list(tmp_path.rglob("*.tmp"))


def test_truncated_cache_entry_is_discarded_not_returned(tmp_path):
    """An interrupted run leaves truncated JSON. Returning it would silently corrupt
    the corpus, so it must be treated as a miss."""
    cache = Cache(tmp_path)
    cache.put("voting", "x", {"voters": [1, 2, 3]})
    path = tmp_path / "voting" / "x.json"
    path.write_text('{"voters": [1, 2', encoding="utf-8")  # killed mid-write
    assert cache.get("voting", "x") is None
    assert not path.exists()


def test_cache_miss_on_absent_key(tmp_path):
    assert Cache(tmp_path).get("voting", "nope") is None


@pytest.mark.parametrize("kind", ["voting", "draft", "meta"])
def test_cache_kinds_are_isolated(tmp_path, kind):
    cache = Cache(tmp_path)
    cache.put(kind, "k", {"kind": kind})
    assert json.loads((tmp_path / kind / "k.json").read_text())["kind"] == kind
