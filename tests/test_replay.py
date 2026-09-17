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
    connectome — significant with the wrong sign, because a whole-population average
    tracks residual anatomical asymmetry rather than steering. The DNa family scores
    4.21."""
    assert bundle["race"]["dna_left"] == 16
    assert bundle["race"]["dna_right"] == 16
    assert len(bundle["audit"]["dna_left_bodies"]) == 16


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
    assert w["turn_max"] >= w["turn_min"]


def test_the_verdict_is_one_of_the_three_states_the_fly_can_emit(bundle):
    assert bundle["verdict"]["code"] in FLY_STATES


def test_the_dead_band_came_from_the_brain_not_the_chamber(bundle):
    assert bundle["race"]["dead_band"] > 0
    supports = bundle["verdict"]["supports_bill"]
    turn, band = bundle["race"]["turn"], bundle["race"]["dead_band"]
    if supports is None:
        assert abs(turn) <= band
    else:
        assert abs(turn) > band
        assert supports == (turn > 0)


def test_the_baseline_bias_was_measured_and_subtracted(bundle):
    """A blank bill turns this fly on its own; leaving that in would bias every verdict."""
    race = bundle["race"]
    assert race["baseline_bias"] != 0.0
    assert race["turn"] == pytest.approx(race["raw_turn"] - race["baseline_bias"], abs=1e-4)


def test_the_race_is_a_full_length_series(bundle):
    race = bundle["race"]
    frames = bundle["sim"]["frames"]
    assert len(race["left_hz"]) == len(race["right_hz"]) == frames


def test_the_published_engine_was_used(bundle):
    """Karbes no longer carries its own kernel. The one it had implemented the synapse as
    an instantaneous voltage step, a documented failure mode of this model, and every
    dynamical conclusion drawn from it described that bug."""
    assert "mlx-lif-engine" in bundle["sim"]["engine"]


def test_the_network_is_sparse_not_saturated(bundle):
    """The published model rests at 0 Hz and responds sparsely. Our own kernel self-ignited
    to 22 Hz on background drive alone; if this climbs back there, the engine changed."""
    assert 0.5 < bundle["sim"]["mean_rate_hz"] < 12.0


def test_the_drive_is_lateralised(bundle):
    """A bilaterally symmetric stimulus cannot move a left-minus-right readout."""
    drive = bundle["drive"]
    assert drive["orn_left"] > 0 and drive["orn_right"] > 0
    assert "rootSide" in drive["laterality"]


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
    # Every group sits in a physiological band. This replaced an assertion that the optic
    # lobes stay near-silent while the central brain blazes, which was true only of the
    # kernel this project used to carry: on the published engine the optic lobes are the
    # *most* active group at ~6 Hz and the descending neurons the least at ~1 Hz, and the
    # whole network is sparse rather than one region saturating.
    for group, series in hz.items():
        peak = max(series)
        assert 0.1 < peak < 30.0, f"{group} peaks at {peak} Hz"


def test_both_descending_pools_actually_fire(bundle):
    """A silent readout still produces a verdict — "inside the dead band" — and a plausible
    number beside it, so nothing downstream looks wrong."""
    race = bundle["race"]
    assert race["left_spikes"] > 0, "left DNa pool never fired"
    assert race["right_spikes"] > 0, "right DNa pool never fired"


def test_the_bundle_fits_the_page_budget(bundle):
    docs = sorted(FIXTURES.glob("*.json"))
    blobs = sorted(FIXTURES.glob("*.raster.bin"))
    total = docs[0].stat().st_size + blobs[0].stat().st_size
    assert total < MAX_BUNDLE_BYTES, f"bundle is {total:,} bytes"
