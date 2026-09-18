"""Twenty flies from one connectome: the same brain, rewired, voting the same season.

SPEC calls the rewired-graph arm "not validation, it is the experiment", and this is the
form the experiment finally takes. Earlier the shuffle was run three times and read as a
control on *accuracy* — it beat the real connectome on AUC, which retired the idea that the
wiring makes the fly a better predictor of the chamber. What it did not retire is the more
interesting reading: the three shuffles landed in three different places. Wiring does not
decide whether the fly is right. It decides **who the fly is**.

So: one degree-preserving shuffle per seed, each a different brain with identical statistics
— same in-degree, out-degree, sign and total output per neuron, only the addressees changed
— each given the identical corpus, the identical encoder, the identical calibration and the
identical decoder. Whatever separates them is the connectivity and nothing else.

Packs are 190 MB each, so a pack is built, run, and deleted. The record is what we keep.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import asdict
from pathlib import Path

log = logging.getLogger(__name__)

#: Where `lif` keeps compiled packs. The shuffler writes its output beside the source.
PACKS = Path.home() / "git" / "drosophila-brain-mlx" / "data" / "pack"
SOURCE = "male_cns_v1"
OUT = Path("runs/chorus")


def pack_path(seed: int) -> Path:
    return PACKS / f"{SOURCE}-shuffled-seed{seed}"


def ensure_pack(seed: int) -> Path:
    """Build the degree-preserving shuffle for `seed` unless it is already on disk."""
    path = pack_path(seed)
    if (path / "manifest.json").exists():
        return path
    from lif.shuffle_pack import write_shuffled_pack

    t0 = time.time()
    manifest = write_shuffled_pack(PACKS / SOURCE, path, seed)
    s = manifest["shuffle"]
    log.info(
        "shuffled seed %d in %.0fs: %s edges land where they already were, %s self-loops, "
        "%s repair rounds",
        seed,
        time.time() - t0,
        f"{s['edges_kept']:,}",
        f"{s['self_loops']:,}",
        s["repair_rounds"],
    )
    return path


def record(name: str) -> Path:
    return OUT / f"{name}.json"


def run_one(name: str, pack: Path | None, pops, bills, votes, scores, cal, *, seed: int = 0):
    """One fly's full season. Returns the ballots; writes them before returning."""
    from karbes import engine as E
    from karbes import season

    existing = record(name)
    if existing.exists():
        log.info("%s already voted, keeping the record", name)
        return json.loads(existing.read_text(encoding="utf-8"))

    engine = E.load(pack)
    ballots = season.run(
        engine, pops, bills, votes, scores,
        bias=cal["baseline_bias"], dead_band=cal["dead_band"],
        sees_initiator=True, seed=seed, label=name,
    )
    rows = [asdict(b) if hasattr(b, "__dataclass_fields__") else b.__dict__ for b in ballots]
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = existing.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows), encoding="utf-8")
    tmp.replace(existing)
    return rows


def drop_pack(seed: int) -> None:
    """A pack is 190 MB and reproducible from its seed; the record is not."""
    path = pack_path(seed)
    if path.exists() and (path / "manifest.json").exists():
        shutil.rmtree(path)
