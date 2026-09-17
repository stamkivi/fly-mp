"""The engineered I/O mapping, guarded at both ends.

Nothing here needs the connectome: the encoder turns scores into rates and the decoder
turns rates into a vote, and both are pure. The properties tested are the ones that would
silently produce a confident, meaningless voting record if they broke.
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


@pytest.fixture
def pops() -> Populations:
    """Equal-sized stand-in populations, so size normalisation is a no-op here."""
    return Populations(
        retained=np.arange(len(EVERY_ORN) * 10, dtype=np.int64),
        orn={
            name: np.arange(i * 10, (i + 1) * 10, dtype=np.int64)
            for i, name in enumerate(EVERY_ORN)
        },
        dn_left=np.array([], dtype=np.int64),
        dn_right=np.array([], dtype=np.int64),
        types={},
    )


def scored(**overrides: float) -> Scored:
    scores = dict.fromkeys(rubric2.KEYS, 0.0) | {"salience": 1.0}
    conf = dict.fromkeys(rubric2.KEYS, 1.0) | {"salience": 1.0}
    for key, value in overrides.items():
        scores[key] = value
    return Scored(scores=scores, confidence=conf, input_tokens=0)


def test_a_zero_score_leaves_both_poles_at_background(pops):
    rates = encode.orn_rates(scored(), pops)
    assert set(rates) == set(EVERY_ORN)
    assert all(hz == pytest.approx(encode.BACKGROUND_HZ) for hz in rates.values())


def test_a_positive_score_drives_the_positive_pole_only(pops):
    neg, pos = CHANNEL_ORNS["security"]
    rates = encode.orn_rates(scored(security=1.0), pops)
    assert rates[pos] == pytest.approx(encode.BACKGROUND_HZ + encode.PEAK_HZ)
    assert rates[neg] == pytest.approx(encode.BACKGROUND_HZ)
    # The other seven channels are untouched.
    others = [n for n in EVERY_ORN if n not in (neg, pos)]
    assert all(rates[n] == pytest.approx(encode.BACKGROUND_HZ) for n in others)


def test_a_negative_score_drives_the_negative_pole(pops):
    neg, pos = CHANNEL_ORNS["pay"]
    rates = encode.orn_rates(scored(pay=-1.0), pops)
    assert rates[neg] > rates[pos] == pytest.approx(encode.BACKGROUND_HZ)


def test_confidence_scales_the_drive_and_zero_confidence_silences_it(pops):
    """The whole reason Jev replaced the LLM rubric. A channel the model could not read
    must drive the fly weakly, not drive it with noise dressed as signal."""
    s = scored(security=1.0)
    s.confidence["security"] = 0.25
    quarter = encode.orn_rates(s, pops)[CHANNEL_ORNS["security"][1]]
    assert quarter == pytest.approx(encode.BACKGROUND_HZ + 0.25 * encode.PEAK_HZ)

    s.confidence["security"] = 0.0
    assert encode.orn_rates(s, pops)[CHANNEL_ORNS["security"][1]] == pytest.approx(
        encode.BACKGROUND_HZ
    )


def test_salience_scales_the_stimulus_but_never_the_background(pops):
    s = scored(security=1.0)
    s.scores["salience"] = 0.0
    rates = encode.orn_rates(s, pops)
    pos = CHANNEL_ORNS["security"][1]
    assert rates[pos] == pytest.approx(
        encode.BACKGROUND_HZ + encode.SALIENCE_FLOOR * encode.PEAK_HZ
    )
    assert rates[CHANNEL_ORNS["security"][0]] == pytest.approx(encode.BACKGROUND_HZ)


def test_every_rate_stays_inside_the_measured_orn_range(pops):
    """Pre-registered, not tuned: ORNs are measured firing at roughly 5-200 Hz."""
    extremes = [scored(**{k: v}) for k in rubric2.KEYS for v in (-1.0, 1.0)]
    for s in extremes:
        for hz in encode.orn_rates(s, pops).values():
            assert 5.0 <= hz <= 200.0


def test_larger_populations_are_driven_more_gently_per_neuron():
    """No channel gets weight purely from having more cells."""
    sizes = {name: 40 + 10 * i for i, name in enumerate(EVERY_ORN)}
    start = 0
    orn = {}
    for name, size in sizes.items():
        orn[name] = np.arange(start, start + size, dtype=np.int64)
        start += size
    pops = Populations(
        retained=np.arange(start, dtype=np.int64),
        orn=orn,
        dn_left=np.array([], dtype=np.int64),
        dn_right=np.array([], dtype=np.int64),
        types={},
    )
    rates = encode.orn_rates(scored(), pops)
    biggest, smallest = max(sizes, key=sizes.get), min(sizes, key=sizes.get)
    assert rates[biggest] < rates[smallest]
    # Population drive, not per-neuron rate, is what is equalised.
    assert rates[biggest] * sizes[biggest] == pytest.approx(rates[smallest] * sizes[smallest])


def race_of(delta: float, dead_band: float = 1.0) -> decode.Race:
    """A race whose settled readout is exactly `delta` Hz."""
    frames = 100
    left = np.zeros(frames)
    right = np.full(frames, delta)
    return decode.Race(
        left_hz=left,
        right_hz=right,
        delta_hz=right - left,
        delta=delta,
        settled_from=30,
        dead_band=dead_band,
    )


@pytest.mark.parametrize(
    ("delta", "inverted", "expected"),
    [
        # A normal final vote: right wins -> the fly wants the bill -> POOLT.
        (5.0, False, POOLT),
        (-5.0, False, VASTU),
        # A rejection motion: wanting the bill means voting against killing it.
        (5.0, True, VASTU),
        (-5.0, True, POOLT),
        # Inside the fly's own noise floor, either way round.
        (0.5, False, EI_HAALETANUD),
        (-0.5, True, EI_HAALETANUD),
    ],
)
def test_the_rejection_flip_lives_in_the_decoder(delta, inverted, expected):
    """`Tagasi lukkamine` inverts polarity, and the flip must be in one place so every
    control arm inherits it identically."""
    assert race_of(delta).vote(inverted) == expected


def test_a_race_inside_the_dead_band_is_not_a_decision():
    assert race_of(0.9, dead_band=1.0).supports_bill is None
    assert race_of(1.1, dead_band=1.0).supports_bill is True
    assert race_of(-1.1, dead_band=1.0).supports_bill is False


def test_the_race_compares_rates_so_the_pool_imbalance_cannot_vote():
    """656 left cells against 648 right: counting spikes rather than rates would hand the
    fly a permanent lean that has nothing to do with the bill."""
    frames, duration = 100, 0.5
    counts = {
        "dn_left": np.full(frames, 656 // 8, dtype=np.int32),
        "dn_right": np.full(frames, 648 // 8, dtype=np.int32),
    }
    sizes = {"dn_left": 656, "dn_right": 648}
    race = decode.race(counts, sizes, duration)
    assert abs(race.delta) < 0.5


def test_the_verdict_ignores_the_frames_before_the_network_settles():
    frames, duration = 100, 0.5
    # A burst in the first 100 ms, then silence. The settled readout must not see it.
    left = np.zeros(frames, dtype=np.int32)
    right = np.zeros(frames, dtype=np.int32)
    right[:20] = 500
    race = decode.race(
        {"dn_left": left, "dn_right": right}, {"dn_left": 1, "dn_right": 1}, duration
    )
    assert race.settled_from == 30
    assert race.delta == pytest.approx(0.0)
    assert race.delta_hz[:20].max() > 0
