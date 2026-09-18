"""The replay bundle: its binary layout, and the rules the committed fixture must obey.

The fixture is a real bundle from a real bill, so these double as an end-to-end guard on
the pipeline that produced it. They run without the connectome or the corpus.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest

from karbes import replay
from karbes.riigikogu.model import FLY_STATES
from karbes.score import rubric2

FIXTURES = Path(__file__).parent / "fixtures"

#: The artifact budget is 16 MB for everything. One bill must stay far inside it.
MAX_BUNDLE_BYTES = 1_000_000


def unpack(blob: bytes) -> list[np.ndarray]:
    assert blob[:4] == replay.RASTER_MAGIC
    (frames,) = struct.unpack("<I", blob[4:8])
    end = 8 + 4 * (frames + 1)
    offsets = np.frombuffer(blob, dtype="<u4", count=frames + 1, offset=8)
    slots = np.frombuffer(blob, dtype="<u2", offset=end)
    return [slots[offsets[i] : offsets[i + 1]] for i in range(frames)]


def test_raster_round_trips():
    frames = [
        np.array([3, 9, 12], dtype=np.uint16),
        np.empty(0, dtype=np.uint16),
        np.array([1], dtype=np.uint16),
    ]
    got = unpack(replay.pack_raster(frames))
    assert len(got) == len(frames)
    for a, b in zip(frames, got, strict=True):
        assert np.array_equal(a, b)


def test_an_empty_raster_still_packs():
    got = unpack(replay.pack_raster([np.empty(0, dtype=np.uint16)] * 4))
    assert len(got) == 4
    assert all(len(f) == 0 for f in got)


@pytest.fixture(scope="module")
def bundle() -> dict:
    docs = sorted(FIXTURES.glob("*.json"))
    assert docs, f"no replay fixture in {FIXTURES}; run `karbes replay`"
    return json.loads(docs[0].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raster(bundle) -> list[np.ndarray]:
    blob = min(FIXTURES.glob("*.raster.bin")).read_bytes()
    return unpack(blob)


def test_the_fixture_is_this_schema(bundle):
    assert bundle["schema"] == replay.SCHEMA


def test_body_ids_are_real_integers(bundle):
    """A float body ID silently mismatches every join back to the annotations."""
    ids = [b for ids in bundle["audit"]["driven_bodies"].values() for b in ids]
    ids += bundle["audit"]["dna_left_bodies"] + bundle["audit"]["dna_right_bodies"]
    assert ids
    assert all(isinstance(b, int) and b > 0 for b in ids)


def test_the_readout_is_the_dna_family(bundle):
    """Not all 1,304 descending neurons. flybrain scores that readout at d' -1.70 on this
    connectome — significant with the wrong sign, because a whole-population average tracks
    residual anatomical asymmetry rather than steering."""
    assert len(bundle["audit"]["dna_left_bodies"]) == 16
    assert len(bundle["audit"]["dna_right_bodies"]) == 16


def test_both_senses_are_wired_in(bundle):
    """Smell carries what the bill does; vision carries who tabled it. The scoring model
    never sees the initiator, so the second sense adds information rather than laundering
    the first."""
    assert bundle["drive"]["orn_left"] > 0 and bundle["drive"]["orn_right"] > 0
    assert "rootSide" in bundle["drive"]["laterality"]
    assert bundle["audit"]["t4t5_cells"] > 10_000
    assert bundle["audit"]["looming_cells"] > 0
    assert bundle["vision"]["flow"] in (-1.0, 1.0)


def test_the_two_flies_are_one_fly_until_the_reveal(bundle):
    """The only difference between the arms is the procedural bit, and it arrives partway
    through. If the paths differ before that, something else is leaking between them."""
    a = bundle["arena"]
    reveal = a["reveal_step"]
    assert 0 < reveal < a["seeing"]["steps"]
    for i in range(reveal):
        assert a["blind"]["path"][i] == a["seeing"]["path"][i], f"diverged at step {i}"
        assert a["blind"]["turn"][i] == a["seeing"]["turn"][i]
    assert not any(a["blind"]["seeing"])
    assert any(a["seeing"]["seeing"])


def test_the_walk_actually_goes_somewhere(bundle):
    """A fly that never leaves the middle has not chosen a pot; "nearest" would then be
    decided by which way it happened to be drifting."""
    import math

    a = bundle["arena"]
    for arm in ("blind", "seeing"):
        reach = max(math.hypot(x, y) for x, y in a[arm]["path"])
        assert reach > 0.3 * a["ring"], f"{arm} never left the centre ({reach:.2f})"
        assert a[arm]["settled_on"] in bundle["arena"]["pots"] or a[arm]["escaped"]


def test_every_pot_is_a_rubric_channel(bundle):
    assert set(bundle["arena"]["pots"]) == set(rubric2.KEYS)
    assert set(bundle["arena"]["bearings"]) == set(rubric2.KEYS)
    assert all(v > 0 for v in bundle["arena"]["pots"].values())


def test_both_arms_emit_a_real_vote(bundle):
    v = bundle["verdict"]
    assert v["blind"] in FLY_STATES and v["seeing"] in FLY_STATES
    assert v["flipped"] == (v["blind"] != v["seeing"])


def test_group_rates_are_probed_not_derived_from_the_raster(bundle):
    """The raster is deduplicated per frame, so counting it understates the rate — and
    understates it worst where the rate is highest. The bundle carries separately probed
    per-group counts so the page does not have to."""
    hz = bundle["atlas"]["group_hz"]
    assert set(hz) == set(bundle["atlas"]["groups"])
    frames = bundle["sim"]["frames"]
    assert all(len(series) == frames for series in hz.values())
    # Every group sits in a physiological band. This replaced an assertion that the optic
    # lobes stay near-silent while the central brain blazes, which was true only of the
    # kernel this project used to carry: on the published engine the optic lobes are the
    # *most* active group at ~6 Hz and the descending neurons the least at ~1 Hz, and the
    # whole network is sparse rather than one region saturating.
    for group, series in hz.items():
        peak = max(series)
        assert 0.1 < peak < 30.0, f"{group} peaks at {peak} Hz"


def test_the_fly_actually_turns(bundle):
    """A walk whose turn index never moves is a fly being carried, not steering. That is
    what a silently broken readout looks like from here: the path still exists and the
    verdict still prints."""
    turns = bundle["arena"]["seeing"]["turn"]
    assert any(t != 0.0 for t in turns), "the readout never moved"
    assert max(turns) != min(turns), "the turn index is constant"


def test_the_bundle_fits_the_page_budget(bundle):
    docs = sorted(FIXTURES.glob("*.json"))
    blobs = sorted(FIXTURES.glob("*.raster.bin"))
    total = docs[0].stat().st_size + blobs[0].stat().st_size
    assert total < MAX_BUNDLE_BYTES, f"bundle is {total:,} bytes"
