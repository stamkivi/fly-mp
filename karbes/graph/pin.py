"""SHA-256 pinning for the connectome files and everything compiled from them.

The spec requires both ends pinned: if a source feather changes, every cached array
derived from it must be invalidated rather than silently reused. A stale compiled matrix
paired with fresh annotations would produce a fly wired to the wrong neurons, and nothing
in the output would look wrong.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

LOCK = "sha256.lock.json"
CHUNK = 1 << 20


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def read_lock(root: Path) -> dict:
    p = root / LOCK
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_lock(root: Path, entries: dict) -> None:
    (root / LOCK).write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")


def record(root: Path, name: str, path: Path, derived_from: list[str] | None = None) -> str:
    """Hash `path` and store it under `name`, noting which sources it was built from."""
    lock = read_lock(root)
    d = digest(path)
    lock[name] = {"sha256": d, "bytes": path.stat().st_size}
    if derived_from:
        lock[name]["derived_from"] = {s: lock.get(s, {}).get("sha256") for s in derived_from}
    write_lock(root, lock)
    return d


def verify(root: Path, name: str, path: Path) -> bool:
    entry = read_lock(root).get(name)
    return bool(entry) and path.exists() and digest(path) == entry["sha256"]


def sources_unchanged(root: Path, name: str) -> bool:
    """True when a compiled artefact's recorded sources still hash to the same values."""
    lock = read_lock(root)
    entry = lock.get(name)
    if not entry or "derived_from" not in entry:
        return False
    return all(
        lock.get(src, {}).get("sha256") == want for src, want in entry["derived_from"].items()
    )
