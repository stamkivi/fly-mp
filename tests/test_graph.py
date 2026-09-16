"""Guards on the connectome layer.

Skipped without the MaleCNS files, which are gitignored — they are 1 GB and freely
downloadable, so the repo pins their hashes rather than carrying them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from karbes.graph import populations as P

ROOT = Path("data/malecns")
pytestmark = pytest.mark.skipif(
    not (ROOT / P.ANNOTATIONS).exists(), reason="MaleCNS annotations not downloaded"
)


@pytest.fixture(scope="module")
def pops():
    return P.load(ROOT)


def test_retention_matches_the_published_neuron_count(pops):
    """Keeping every body with an assigned superclass yields exactly the 166,700 the
    community reports. If this drifts, the retention policy changed underneath us."""
    assert pops.n == 166_700


def test_body_ids_stay_integers(pops):
    """A float body ID silently mismatches every join downstream."""
    assert pops.retained.dtype == np.int64
    for ids in pops.orn.values():
        assert ids.dtype == np.int64


def test_every_axis_has_two_distinct_channels(pops):
    channels = pops.axis_channels()
    assert set(channels) == set(P.AXIS_ORNS)
    seen = set()
    for neg, pos in channels.values():
        assert len(neg) > 0 and len(pos) > 0
        assert not set(neg.tolist()) & set(pos.tolist())
        seen |= set(neg.tolist()) | set(pos.tolist())
    # 16 disjoint populations, so the union is the sum of the parts.
    assert len(seen) == sum(len(v) for v in pops.orn.values())


def test_channels_are_comparable_in_size(pops):
    """No axis should be louder than another purely through cell count."""
    sizes = [len(v) for v in pops.orn.values()]
    assert max(sizes) / min(sizes) < 2.5, f"channel sizes span {min(sizes)}-{max(sizes)}"


def test_readout_has_both_sides_and_is_balanced(pops):
    assert len(pops.dn_left) > 5 and len(pops.dn_right) > 5
    ratio = len(pops.dn_left) / len(pops.dn_right)
    assert 0.6 < ratio < 1.7, f"DN pools unbalanced: {len(pops.dn_left)}/{len(pops.dn_right)}"


def test_readout_and_input_do_not_overlap(pops):
    """If a stimulated cell were also read out, the readout would echo the input."""
    stim = {b for ids in pops.orn.values() for b in ids.tolist()}
    read = set(pops.dn_left.tolist()) | set(pops.dn_right.tolist())
    assert not stim & read


@pytest.mark.skipif(
    not (ROOT / "body-neurotransmitters-male-cns-v1.0.feather").exists(),
    reason="neurotransmitter file not downloaded",
)
def test_signs_cover_nearly_every_neuron_and_obey_dale(pops):
    from karbes.graph import sign as S

    s, report = S.signs(ROOT, pops.retained)
    assert len(s) == pops.n
    assert report["coverage"] > 0.95
    # Dale's law: one sign per neuron, drawn from exactly three values.
    assert set(np.unique(s).tolist()) <= {-1.0, 0.0, 1.0}
    # Fly cortex is predominantly cholinergic; a flipped mapping would invert this.
    assert report["excitatory"] > report["inhibitory"]
