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
    ids += bundle["audit"]["dn_left_bodies"] + bundle["audit"]["dn_right_bodies"]
    assert ids
    assert all(isinstance(b, int) and b > 0 for b in ids)


def test_the_readout_is_the_whole_descending_pool(bundle):
    assert bundle["race"]["dn_left"] + bundle["race"]["dn_right"] == 1_304


def test_every_rubric_channel_is_present_with_a_confidence(bundle):
    keys = [c["key"] for c in bundle["channels"]]
    assert keys == [*rubric2.KEYS, "salience"]
    for channel in bundle["channels"]:
        assert -1.0 <= channel["score"] <= 1.0
        assert 0.0 <= channel["confidence"] <= 1.0


def test_drive_is_the_confidence_weighted_score(bundle):
    """What the page draws as bar length has to be what went into the neurons."""
    gain = next(c for c in bundle["channels"] if c["key"] == "salience")["drive"]
    for channel in bundle["channels"]:
        if channel["key"] == "salience":
            continue
        expected = channel["score"] * channel["confidence"] * gain
        assert channel["drive"] == pytest.approx(expected, abs=1e-3)


def test_no_channel_was_defaulted_to_zero(bundle):
    """A rubric failure that silently scores zeros produces a confident, plausible,
    meaningless vote. An unscored bill is excluded, never bundled.

    Note what this does *not* assert: a confidence of exactly 0.0 is a real answer, not a
    missing one. Jev returns it when it genuinely cannot read a channel from the text, and
    the confidence weighting then turns that channel's drive off, which is the intended
    behaviour. `jev.py` raises on an *absent* confidence rather than defaulting it, so the
    two cases cannot be confused upstream of here.
    """
    assert len(bundle["channels"]) == len(rubric2.KEYS) + 1
    assert any(c["score"] != 0.0 for c in bundle["channels"])
    assert any(c["confidence"] > 0.5 for c in bundle["channels"])
    assert all(c["confidence"] is not None for c in bundle["channels"])


def test_an_unreadable_channel_drives_nothing(bundle):
    """The whole reason Jev replaced the LLM rubric: a channel it cannot read must drive
    the fly weakly rather than driving it with noise dressed as signal."""
    for channel in bundle["channels"]:
        if channel["key"] != "salience" and channel["confidence"] == 0.0:
            assert channel["drive"] == 0.0


def test_the_wavering_was_measured(bundle):
    """SNR is below 1, so a single verdict is not the whole truth about this bill and the
    bundle has to carry the distribution rather than just the point estimate."""
    w = bundle["wavering"]
    assert w["seeds"] > 1
    assert len(w["runs"]) == w["seeds"] - 1
    assert sum(w["tally"].values()) == w["seeds"] - 1
    assert all(r["code"] in FLY_STATES for r in w["runs"])
    assert w["delta_max_hz"] >= w["delta_min_hz"]


def test_the_verdict_is_one_of_the_three_states_the_fly_can_emit(bundle):
    assert bundle["verdict"]["code"] in FLY_STATES


def test_the_dead_band_came_from_the_brain_not_the_chamber(bundle):
    assert bundle["race"]["dead_band_hz"] > 0
    supports = bundle["verdict"]["supports_bill"]
    delta, band = bundle["race"]["delta"], bundle["race"]["dead_band_hz"]
    if supports is None:
        assert abs(delta) <= band
    else:
        assert abs(delta) > band
        assert supports == (delta > 0)


def test_the_race_is_a_full_length_series(bundle):
    race = bundle["race"]
    frames = bundle["sim"]["frames"]
    assert len(race["left_hz"]) == len(race["right_hz"]) == len(race["delta_hz"]) == frames
    assert race["settled_from_frame"] < frames


def test_the_weight_scale_is_the_calibrated_one(bundle):
    """0.05 mV per contact, not the published 0.275. At 0.275 the network runs at ~50 Hz."""
    assert bundle["sim"]["weight_scale"] == pytest.approx(0.05e-3)


def test_the_raster_is_frame_aligned_and_in_range(bundle, raster):
    assert len(raster) == bundle["sim"]["frames"]
    somas = bundle["atlas"]["somas"]
    for frame in raster:
        assert frame.max(initial=0) < somas
        # Deduplicated per frame: the page asks whether a cell fired, not how often.
        assert len(np.unique(frame)) == len(frame)


def test_the_brain_actually_fires(bundle, raster):
    """A bundle of near-silence is not a replay of anything. Guards against a
    weight scale or a drive that quietly stopped reaching the network."""
    assert sum(len(f) for f in raster) > 100
    assert bundle["sim"]["total_spikes"] > 0


def test_group_rates_are_probed_not_derived_from_the_raster(bundle):
    """The raster is deduplicated per frame, so counting it understates the rate — and
    understates it worst where the rate is highest. The bundle carries separately probed
    per-group counts so the page does not have to."""
    hz = bundle["atlas"]["group_hz"]
    assert set(hz) == set(bundle["atlas"]["groups"])
    frames = bundle["sim"]["frames"]
    assert all(len(series) == frames for series in hz.values())
    # The optic lobes get no input in this simulation; the central brain gets all of it.
    assert max(hz["central"]) > 10 * max(hz["optic"])


def test_the_bundle_fits_the_page_budget(bundle):
    docs = sorted(FIXTURES.glob("*.json"))
    blobs = sorted(FIXTURES.glob("*.raster.bin"))
    total = docs[0].stat().st_size + blobs[0].stat().st_size
    assert total < MAX_BUNDLE_BYTES, f"bundle is {total:,} bytes"
