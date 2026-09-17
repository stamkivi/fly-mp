"""The engineered I/O mapping, guarded at both ends.

The encoder turns scores into per-antenna rates and the decoder turns descending-neuron
spikes into a vote. The properties tested are the ones that would silently produce a
confident, meaningless voting record if they broke.
"""

from __future__ import annotations

import numpy as np
import pytest

from karbes import decode, encode
from karbes.graph.populations import CHANNEL_ORNS, Populations
from karbes.riigikogu.model import EI_HAALETANUD, POOLT, VASTU
from karbes.score import rubric2
from karbes.score.jev import Scored

EVERY_ORN = [name for pair in CHANNEL_ORNS.values() for name in pair]
PER_SIDE = 10


class FakeEngine:
    """Positions are body IDs; the pack ordering does not matter to these tests."""

    def positions(self, bodies):
        return np.asarray(bodies, dtype=np.int32)


@pytest.fixture
def pops() -> Populations:
    """Equal-sized stand-in populations with a clean left/right split."""
    orn, left, right = {}, [], []
    for i, name in enumerate(EVERY_ORN):
        base = i * 2 * PER_SIDE
        ids = np.arange(base, base + 2 * PER_SIDE, dtype=np.int64)
        orn[name] = ids
        left.extend(ids[:PER_SIDE].tolist())
        right.extend(ids[PER_SIDE:].tolist())
    return Populations(
        retained=np.arange(len(EVERY_ORN) * 2 * PER_SIDE, dtype=np.int64),
        orn=orn,
        dn_left=np.array([], dtype=np.int64),
        dn_right=np.array([], dtype=np.int64),
        dna_left=np.array([0], dtype=np.int64),
        dna_right=np.array([1], dtype=np.int64),
        orn_left=np.array(sorted(left), dtype=np.int64),
        orn_right=np.array(sorted(right), dtype=np.int64),
        types={},
    )


def scored(**overrides: float) -> Scored:
    scores = dict.fromkeys(rubric2.KEYS, 0.0) | {"salience": 1.0}
    conf = dict.fromkeys(rubric2.KEYS, 1.0) | {"salience": 1.0}
    for key, value in overrides.items():
        scores[key] = value
    return Scored(scores=scores, confidence=conf, input_tokens=0)


def rates_by_body(s, pops):
    targets, rates = encode.stimulus(s, pops, FakeEngine())
    return dict(zip(targets.tolist(), rates.tolist(), strict=True))


def test_a_zero_score_drives_both_antennae_equally(pops):
    """The sign picks a side, so a score of zero must not pick one."""
    r = rates_by_body(scored(), pops)
    assert set(r) == set(range(len(EVERY_ORN) * 2 * PER_SIDE))
    assert all(hz == pytest.approx(encode.BACKGROUND_HZ) for hz in r.values())


def test_a_positive_score_leads_with_the_right_antenna(pops):
    r = rates_by_body(scored(security=1.0), pops)
    ids = pops.orn[CHANNEL_ORNS["security"][0]]
    left, right = ids[:PER_SIDE], ids[PER_SIDE:]
    assert all(r[int(b)] == pytest.approx(encode.BACKGROUND_HZ + encode.PEAK_HZ) for b in right)
    assert all(r[int(b)] == pytest.approx(encode.BACKGROUND_HZ) for b in left)


def test_a_negative_score_leads_with_the_left_antenna(pops):
    r = rates_by_body(scored(pay=-1.0), pops)
    ids = pops.orn[CHANNEL_ORNS["pay"][0]]
    left, right = ids[:PER_SIDE], ids[PER_SIDE:]
    assert all(r[int(b)] == pytest.approx(encode.BACKGROUND_HZ + encode.PEAK_HZ) for b in left)
    assert all(r[int(b)] == pytest.approx(encode.BACKGROUND_HZ) for b in right)


def test_confidence_scales_the_drive_and_zero_confidence_silences_it(pops):
    """The whole reason Jev replaced the LLM rubric: a channel the model could not read
    must drive the fly weakly, not drive it with noise dressed as signal."""
    s = scored(security=1.0)
    s.confidence["security"] = 0.25
    right = pops.orn[CHANNEL_ORNS["security"][0]][PER_SIDE:]
    r = rates_by_body(s, pops)
    assert r[int(right[0])] == pytest.approx(encode.BACKGROUND_HZ + 0.25 * encode.PEAK_HZ)

    s.confidence["security"] = 0.0
    assert rates_by_body(s, pops)[int(right[0])] == pytest.approx(encode.BACKGROUND_HZ)


def test_salience_scales_the_stimulus_but_never_the_background(pops):
    s = scored(security=1.0)
    s.scores["salience"] = 0.0
    right = pops.orn[CHANNEL_ORNS["security"][0]][PER_SIDE:]
    r = rates_by_body(s, pops)
    assert r[int(right[0])] == pytest.approx(
        encode.BACKGROUND_HZ + encode.SALIENCE_FLOOR * encode.PEAK_HZ
    )


def test_every_rate_stays_inside_the_measured_orn_range(pops):
    """Pre-registered, not tuned: ORNs are measured firing at roughly 5-200 Hz."""
    for key in rubric2.KEYS:
        for value in (-1.0, 1.0):
            for hz in rates_by_body(scored(**{key: value}), pops).values():
                assert 5.0 <= hz <= 200.0


def test_an_uneven_side_is_not_itself_a_stimulus(pops):
    """rootSide gives 363 left ORNs against 525 right. If drive were a flat per-neuron
    rate, the right antenna would shout permanently and the fly would always turn."""
    name = CHANNEL_ORNS["pay"][0]
    ids = pops.orn[name]
    # Make this glomerulus lopsided: 3 left, 17 right.
    pops.orn_left = np.array(
        sorted(set(pops.orn_left.tolist()) - set(ids[3:PER_SIDE].tolist())), dtype=np.int64
    )
    pops.orn_right = np.array(
        sorted(set(pops.orn_right.tolist()) | set(ids[3:PER_SIDE].tolist())), dtype=np.int64
    )
    r = rates_by_body(scored(), pops)
    left_total = sum(r[int(b)] for b in ids[:3])
    right_total = sum(r[int(b)] for b in ids[3:])
    assert left_total == pytest.approx(right_total)


def turn_of(value: float, dead_band: float = 0.1) -> decode.Turn:
    """A Turn whose baseline-subtracted index is exactly `value`."""
    total = 1000
    right = round(total * (1 + value) / 2)
    return decode.Turn(
        left_spikes=total - right, right_spikes=right, baseline=0.0, dead_band=dead_band
    )


@pytest.mark.parametrize(
    ("value", "inverted", "expected"),
    [
        (0.5, False, POOLT),
        (-0.5, False, VASTU),
        # A rejection motion: wanting the bill means voting against killing it.
        (0.5, True, VASTU),
        (-0.5, True, POOLT),
        (0.05, False, EI_HAALETANUD),
        (-0.05, True, EI_HAALETANUD),
    ],
)
def test_the_rejection_flip_lives_in_the_decoder(value, inverted, expected):
    """`Tagasi lukkamine` inverts polarity, and the flip must be in one place so every
    control arm inherits it identically."""
    assert turn_of(value).vote(inverted) == expected


def test_a_turn_inside_the_dead_band_is_not_a_decision():
    assert turn_of(0.09, dead_band=0.1).supports_bill is None
    assert turn_of(0.11, dead_band=0.1).supports_bill is True
    assert turn_of(-0.11, dead_band=0.1).supports_bill is False


def test_the_baseline_bias_is_subtracted():
    """A blank bill still turns this fly, because the wiring is not symmetric. If that
    bias were left in, every verdict would inherit it."""
    t = decode.Turn(left_spikes=600, right_spikes=400, baseline=-0.2, dead_band=0.1)
    assert t.raw == pytest.approx(-0.2)
    assert t.turn == pytest.approx(0.0)
    assert t.supports_bill is None


def test_a_silent_readout_decides_nothing():
    """Sixteen DNa cells a side are sparse. No spikes must not read as a tie."""
    t = decode.Turn(left_spikes=0, right_spikes=0, baseline=0.0, dead_band=0.1)
    assert not np.isfinite(t.raw)
    assert t.supports_bill is None
    assert t.vote(inverted=False) == EI_HAALETANUD
