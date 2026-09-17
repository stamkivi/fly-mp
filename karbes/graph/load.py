"""Compile the MaleCNS edge list into a CSR matrix the kernel can walk.

The weights file is 1 GB on disk and 151.9M rows — 3.6 GB if materialised as int64, on a
machine that has already been OOM-killed once this session. So it is memory-mapped and
walked in batches, never loaded whole, and never passed through a pandas DataFrame (the
intermediate frame is the memory spike, not the final matrix).

Most of those rows are edges touching bodies that the retention policy drops. Filtering to
retained-to-retained leaves the ~25.6M the community reports.

Output is CSR with int32 indices and float32 weights: about 205 MB per connectome, which
is what makes twenty rewired instances tractable one at a time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.feather as pf

from karbes.graph import pin

log = logging.getLogger(__name__)

WEIGHTS = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
BATCH = 4_000_000
COMPILED = "csr-malecns-v1.0.npz"


@dataclass
class Graph:
    """Connectome as CSR, indexed by position in `bodies` rather than by body ID."""

    indptr: np.ndarray  # int64 (n+1,)
    indices: np.ndarray  # int32 (nnz,) postsynaptic index
    weights: np.ndarray  # float32 (nnz,) synaptic contact counts
    bodies: np.ndarray  # int64 (n,) sorted body IDs
    sign: np.ndarray  # float32 (n,) per presynaptic neuron, Dale's law

    @property
    def n(self) -> int:
        return len(self.bodies)

    @property
    def nnz(self) -> int:
        return len(self.indices)

    def index_of(self, body_ids: np.ndarray) -> np.ndarray:
        """Positions of the given body IDs. Raises if any is not in the graph."""
        idx = np.searchsorted(self.bodies, body_ids)
        idx = np.clip(idx, 0, self.n - 1)
        if not np.array_equal(self.bodies[idx], body_ids):
            missing = body_ids[self.bodies[idx] != body_ids]
            raise KeyError(f"{len(missing)} body IDs not in the graph, e.g. {missing[:3]}")
        return idx.astype(np.int32)

    def out_degree(self) -> np.ndarray:
        return np.diff(self.indptr)


def _map_to_index(bodies: np.ndarray, col: np.ndarray) -> np.ndarray:
    """Position of each value in sorted `bodies`, or -1 when absent."""
    idx = np.searchsorted(bodies, col)
    np.clip(idx, 0, len(bodies) - 1, out=idx)
    idx = idx.astype(np.int64)
    idx[bodies[idx] != col] = -1
    return idx


def compile_graph(root: Path, retained: np.ndarray, sign: np.ndarray) -> Graph:
    """Walk the edge list in batches and build CSR. Nothing is held whole."""
    path = root / WEIGHTS
    table = pf.read_table(path, memory_map=True)
    total = table.num_rows
    log.info(
        "edge list: %s rows, filtering to %s retained neurons", f"{total:,}", f"{len(retained):,}"
    )

    pre_parts, post_parts, w_parts = [], [], []
    kept = 0
    for start in range(0, total, BATCH):
        chunk = table.slice(start, BATCH)
        pre = _map_to_index(retained, chunk.column("body_pre").to_numpy())
        post = _map_to_index(retained, chunk.column("body_post").to_numpy())
        ok = (pre >= 0) & (post >= 0)
        if ok.any():
            pre_parts.append(pre[ok].astype(np.int32))
            post_parts.append(post[ok].astype(np.int32))
            w_parts.append(chunk.column("weight").to_numpy()[ok].astype(np.float32))
            kept += int(ok.sum())
        if (start // BATCH) % 8 == 0:
            log.info("  %s / %s rows, %s edges kept", f"{start:,}", f"{total:,}", f"{kept:,}")
    del table

    pre = np.concatenate(pre_parts)
    del pre_parts
    post = np.concatenate(post_parts)
    del post_parts
    w = np.concatenate(w_parts)
    del w_parts
    log.info("retained %s of %s edges (%.1f%%)", f"{kept:,}", f"{total:,}", 100 * kept / total)

    # Sort by presynaptic index to form CSR rows.
    order = np.argsort(pre, kind="stable")
    pre, post, w = pre[order], post[order], w[order]
    del order

    n = len(retained)
    counts = np.bincount(pre, minlength=n)
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(counts, out=indptr[1:])

    return Graph(indptr=indptr, indices=post, weights=w, bodies=retained, sign=sign)


def save(graph: Graph, root: Path) -> Path:
    out = root / COMPILED
    np.savez(
        out,
        indptr=graph.indptr,
        indices=graph.indices,
        weights=graph.weights,
        bodies=graph.bodies,
        sign=graph.sign,
    )
    pin.record(root, COMPILED, out, derived_from=[WEIGHTS])
    return out


def load_compiled(root: Path) -> Graph | None:
    """Reuse the compiled CSR only when its recorded sources still match."""
    out = root / COMPILED
    if not out.exists():
        return None
    if not pin.sources_unchanged(root, COMPILED):
        log.warning("compiled graph is stale against its sources; recompiling")
        return None
    z = np.load(out)
    return Graph(
        indptr=z["indptr"],
        indices=z["indices"],
        weights=z["weights"],
        bodies=z["bodies"],
        sign=z["sign"],
    )
