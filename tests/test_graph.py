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


def test_channel_keys_track_the_rubric(pops):
    """The ORN table and the scoring rubric must name the same channels. They have drifted
    apart once already, when the rubric was rewritten as concrete questions."""
    from karbes.score import rubric2

    assert tuple(P.CHANNEL_ORNS) == rubric2.KEYS


def test_every_channel_has_two_distinct_poles(pops):
    channels = pops.channels()
    assert set(channels) == set(P.CHANNEL_ORNS)
    seen = set()
    for neg, pos in channels.values():
        assert len(neg) > 0 and len(pos) > 0
        assert not set(neg.tolist()) & set(pos.tolist())
        seen |= set(neg.tolist()) | set(pos.tolist())
    # 16 disjoint populations, so the union is the sum of the parts.
    assert len(seen) == sum(len(v) for v in pops.orn.values())


def test_channels_are_comparable_in_size(pops):
    """No channel should be louder than another purely through cell count."""
    sizes = [len(v) for v in pops.orn.values()]
    assert max(sizes) / min(sizes) < 2.5, f"channel sizes span {min(sizes)}-{max(sizes)}"


def test_the_readout_is_the_dna_family(pops):
    """15 DNa types, 16 cells a side, balanced. This, not all 1,304 descending neurons,
    is what the vote is read from: flybrain scores the whole population at d' -1.70 on this
    connectome, significant with the wrong sign."""
    assert len(pops.dna_left) == len(pops.dna_right) == 16
    assert not set(pops.dna_left.tolist()) & set(pops.dna_right.tolist())
    assert set(pops.dna_left.tolist()) <= set(pops.dn_left.tolist())


def test_orns_are_lateralised_by_rootside(pops):
    """ORNs carry no somaSide at all — their somas sit in the antenna — so rootSide is the
    only laterality available. Without it the fly is spatially blind and a left-minus-right
    readout cannot move."""
    assert len(pops.orn_left) > 0 and len(pops.orn_right) > 0
    assert not set(pops.orn_left.tolist()) & set(pops.orn_right.tolist())
    driven = {b for ids in pops.orn.values() for b in ids.tolist()}
    assert set(pops.orn_left.tolist()) | set(pops.orn_right.tolist()) <= driven


def test_all_descending_neurons_are_still_resolved_for_audit(pops):
    assert len(pops.dn_left) + len(pops.dn_right) == 1_304


def test_readout_has_both_sides_and_is_balanced(pops):
    assert len(pops.dn_left) > 5 and len(pops.dn_right) > 5
    ratio = len(pops.dn_left) / len(pops.dn_right)
    assert 0.6 < ratio < 1.7, f"DN pools unbalanced: {len(pops.dn_left)}/{len(pops.dn_right)}"


def test_readout_and_input_do_not_overlap(pops):
    """If a stimulated cell were also read out, the readout would echo the input."""
    stim = {b for ids in pops.orn.values() for b in ids.tolist()}
    read = set(pops.dna_left.tolist()) | set(pops.dna_right.tolist())
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
