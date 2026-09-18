"""The arena: eight questions as eight smells, and a fly that walks to one of them.

Stage 2b's fly was handed a single 500 ms whiff and asked for a verdict, and it declined
every time — the median bill uses 2.3% of the encoder's range, which is not enough to beat
the network's own spread in one run. **The loop is the fix, and it is the fly's own.**
Chemotaxis works under appalling per-step signal-to-noise because a small bias, integrated
over many steps with positive feedback, becomes a committed trajectory: as the fly turns
toward a source, that source reaches its near antenna more strongly still.

The arrangement:

* Eight pots stand at fixed, equally spaced bearings around a ring. One per rubric channel.
* Each pot emits in proportion to `|score x confidence x salience|` — **magnitude only**.
  The fly is not deciding whether it approves; it is deciding *which question it cares
  about*, which is the thing a fly can actually do.
* A pot reaches the near antenna more than the far one, by bearing. That projection depends
  on the fly's heading, so it changes as the fly turns — this is the feedback.
* The procedural sense runs alongside as constant optic flow, biasing every turn like a
  crosswind, so a coalition signal can pull the fly off the pot that substance alone would
  have chosen.
* The vote falls out of where it ends up: the sign of the channel it settled on, with the
  rejection-motion flip applied exactly as everywhere else.

Two honest limits, stated here rather than discovered later. The engine has no state that
survives between calls, so each step is a fresh run from rest and the fly has no adaptation
or short-term memory across steps; the first milliseconds of every step are a transient.
And the geometry is a convenience — a real fly does not stand in a ring of labelled pots.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from karbes import decode, encode, vision
from karbes.engine import Engine
from karbes.graph.populations import CHANNEL_ORNS, Populations
from karbes.riigikogu.model import Bill
from karbes.score.jev import Scored

log = logging.getLogger(__name__)

#: Neural time simulated per step of the walk.
STEP_SECONDS = 0.15

#: Steps per bill. Sixteen at 150 ms is 2.4 s of neural time, which is long enough for the
#: feedback to commit and short enough to watch.
STEPS = 16

#: **Approach, not avoidance.** Measured: odour on the fly's right makes the turn index
#: *more positive* by 0.125, and heading is a standard maths angle, so `heading += turn`
#: rotates counter-clockwise — toward the fly's left, away from the source. The first
#: version therefore ran anti-chemotaxis and the fly fled the pots in circles. Which sign
#: means "toward" is a property of the engineered readout, not of the fly, and it is fixed
#: here on the only defensible criterion: the animal should approach what attracts it.
TURN_SIGN = -1.0

#: Radians of turn per unit of baseline-subtracted turn index, per step.
#:
#: At 2.2 a typical turn index of 0.3 swings the fly 38 degrees in one step, so it spiralled
#: instead of curving and closed a full circle in under ten steps. 1.2 lets the gradient
#: steer it rather than spin it.
TURN_GAIN = 1.2

#: Body lengths travelled per step.
#:
#: **Chosen so the fly can actually cross the arena**, which is the only defensible
#: criterion available and is outcome-blind: at 0.055 its whole 16-step budget covered 0.88
#: against a ring of 1.0, so it never reached a pot and "nearest" was decided by which way
#: it happened to be drifting near the centre. At 0.12 it can reach the ring and overshoot.
SPEED = 0.12

#: Ring radius the pots sit on, in the same units.
RING = 1.0

#: How sharply a pot favours the near antenna. 1.0 is a pure left/right split by bearing.
ANTENNA_SHARPNESS = 0.85

#: Emission floor, so a channel scored at zero is still a faint presence rather than absent.
POT_FLOOR = 0.06

#: Raster frames captured per step.
FRAMES_PER_STEP = 6

#: The step at which the fly learns who tabled the bill.
#:
#: **The procedural signal is an event, not a state.** Constant rotational optic flow makes
#: a fly turn continuously — that is the optomotor response to a rotating drum, and it is
#: what the first version did: the seeing fly simply orbited. So the bit arrives partway
#: through, as a transient, and the two arms are bit-identical before it. Their paths then
#: diverge from exactly one frame, which is the whole thing worth watching.
REVEAL_STEP = 8

#: How many steps the procedural stimulus lasts once it arrives. A looming object passes.
REVEAL_STEPS = 4


def turn_baseline(pops: Populations, engine: Engine, seeds: int = 8) -> float:
    """Turn index under a symmetric arena odour field.

    **Not the same baseline `karbes calibrate` measures.** That one is taken under the
    single-whiff encoder; here both antennae sit at the arena's mid drive, and the constant
    offset is quite different — -0.39 against -0.08. Subtracting the wrong one leaves a
    residual that rotates the fly continuously, which is what made it circle.
    """
    import numpy as np

    from karbes import engine as E

    orn_l, orn_r = engine.positions(pops.orn_left), engine.positions(pops.orn_right)
    dna_l, dna_r = engine.positions(pops.dna_left), engine.positions(pops.dna_right)
    mean_n = (len(orn_l) + len(orn_r)) / 2
    mid = encode.BACKGROUND_HZ + encode.PEAK_HZ * 0.5
    targets = np.concatenate([orn_l, orn_r])
    rates = np.concatenate(
        [np.full(len(orn_l), mid * mean_n / len(orn_l)), np.full(len(orn_r), mid * mean_n / len(orn_r))]
    )
    order = np.argsort(targets)
    turns = [
        decode.turn_index(
            E.run(engine, targets[order].astype(np.int32), rates[order], seed=s, duration=STEP_SECONDS).counts,
            dna_l,
            dna_r,
        ).raw
        for s in range(seeds)
    ]
    return float(np.mean(turns))


def bearings() -> dict[str, float]:
    """Each channel's fixed place on the ring, in radians. Arbitrary and pre-registered."""
    names = list(CHANNEL_ORNS)
    return {name: 2 * math.pi * i / len(names) for i, name in enumerate(names)}


@dataclass
class Step:
    """One tick of the walk, kept so the page can replay it."""

    x: float
    y: float
    heading: float
    turn: float
    left_hz: float
    right_hz: float
    nearest: str
    spikes: int
    escaped: bool
    #: Whether the procedural stimulus was present on this step.
    seeing: bool = False
    #: Per drawn atlas group, the firing rate in each captured frame of this step.
    group_hz: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class Walk:
    """A whole trajectory and what it decided."""

    steps: list[Step] = field(default_factory=list)
    settled_on: str | None = None
    escaped: bool = False
    pots: dict[str, float] = field(default_factory=dict)
    bearings: dict[str, float] = field(default_factory=dict)
    #: One continuous raster across the whole walk, `FRAMES_PER_STEP` frames per step.
    raster: list[np.ndarray] = field(default_factory=list)
    reveal_step: int = REVEAL_STEP

    @property
    def path(self) -> list[tuple[float, float]]:
        return [(s.x, s.y) for s in self.steps]


def _antenna_split(bearing_to_pot: float, heading: float) -> tuple[float, float]:
    """Share of a pot's odour reaching (left, right) antenna at this heading.

    A source off the fly's right side reaches the right antenna more. `sin` of the relative
    bearing is the lateral component; the sharpness constant decides how much of the odour
    is lateralised at all rather than shared.
    """
    lateral = math.sin(bearing_to_pot - heading)
    right = 0.5 * (1.0 + ANTENNA_SHARPNESS * lateral)
    return 1.0 - right, right


def walk(
    bill: Bill,
    scored: Scored,
    pops: Populations,
    engine: Engine,
    *,
    see_initiator: bool = True,
    bias: float = 0.0,
    escape_baseline: float = 0.0,
    seed: int = 0,
    steps: int = STEPS,
    atlas=None,
) -> Walk:
    """Run the closed loop for one bill.

    `see_initiator=False` is the coalition-blind arm: the fly walks on substance alone, which
    is what §T1d's SDE-boundary natural experiment requires and what must not be lost when
    the procedural sense is added.
    """
    drive = encode.channel_drive(scored)
    pots = {k: max(POT_FLOOR, abs(v)) for k, v in drive.items()}
    where = bearings()
    dna_l = engine.positions(pops.dna_left)
    dna_r = engine.positions(pops.dna_right)
    giant = engine.positions(pops.giant_fibre)

    orn_l = engine.positions(pops.orn_left)
    orn_r = engine.positions(pops.orn_right)
    visual = vision.stimulus(bill, scored.scores.get("salience", 0.0), pops, engine)

    atlas_idx = engine.positions(atlas.bodies) if atlas is not None else np.array([], dtype=np.int32)
    rng = np.random.default_rng(seed)
    heading = float(rng.uniform(0, 2 * math.pi))
    x = y = 0.0
    out = Walk(pots=pots, bearings=where)

    for step in range(steps):
        # Lateral odour field: every pot, split by its bearing relative to the fly.
        left_total = right_total = 0.0
        for name, strength in pots.items():
            px, py = RING * math.cos(where[name]), RING * math.sin(where[name])
            dx, dy = px - x, py - y
            distance = max(0.25, math.hypot(dx, dy))
            # Inverse-square falloff, so getting closer really does commit the fly.
            reaching = strength / (distance * distance)
            share_l, share_r = _antenna_split(math.atan2(dy, dx), heading)
            left_total += reaching * share_l
            right_total += reaching * share_r

        # **Ratio, not absolute intensity.** Clamping each side at a ceiling meant that as
        # soon as the fly got near a pot both antennae saturated and the gradient vanished
        # exactly where it was needed — the fly would approach, go blind, and drift off.
        # A bilateral *comparison* is scale-free and is what the antennae actually do.
        total = left_total + right_total
        balance = (right_total - left_total) / total if total else 0.0
        left_hz = encode.BACKGROUND_HZ + encode.PEAK_HZ * (0.5 - 0.5 * balance)
        right_hz = encode.BACKGROUND_HZ + encode.PEAK_HZ * (0.5 + 0.5 * balance)
        mean_n = (len(orn_l) + len(orn_r)) / 2
        targets = np.concatenate([orn_l, orn_r])
        rates = np.concatenate(
            [
                np.full(len(orn_l), left_hz * mean_n / len(orn_l)),
                np.full(len(orn_r), right_hz * mean_n / len(orn_r)),
            ]
        )
        seeing_now = see_initiator and REVEAL_STEP <= step < REVEAL_STEP + REVEAL_STEPS
        if seeing_now:
            targets = np.concatenate([targets, visual[0]])
            rates = np.concatenate([rates, visual[1]])
        order = np.argsort(targets)

        from karbes import engine as E

        run = E.run(
            engine,
            targets[order].astype(np.int32),
            rates[order],
            seed=seed * 1000 + step,
            duration=STEP_SECONDS,
        )
        turn = decode.turn_index(run.counts, dna_l, dna_r, baseline=bias).turn
        # The escape baseline is measured over a second; a step is a fraction of one.
        escaped, _ = vision.bolted(
            run.counts, giant, baseline=escape_baseline * STEP_SECONDS if seeing_now else 0.0
        )

        group_hz: dict[str, list[float]] = {}
        if atlas is not None:
            out.raster.extend(run.raster(atlas_idx, FRAMES_PER_STEP))
            frame_s = STEP_SECONDS / FRAMES_PER_STEP
            for gid, name in enumerate(atlas.group_names()):
                members = atlas_idx[atlas.group == gid]
                if len(members):
                    counts = run.frame_counts(members, FRAMES_PER_STEP)
                    group_hz[name] = [round(float(c) / (len(members) * frame_s), 2) for c in counts]

        heading += TURN_SIGN * TURN_GAIN * turn
        x += SPEED * math.cos(heading)
        y += SPEED * math.sin(heading)
        nearest = min(
            pots, key=lambda n: math.hypot(RING * math.cos(where[n]) - x, RING * math.sin(where[n]) - y)
        )
        out.steps.append(
            Step(
                x=x, y=y, heading=heading, turn=turn,
                left_hz=left_hz, right_hz=right_hz,
                nearest=nearest, spikes=int(run.counts.sum()), escaped=escaped,
                seeing=seeing_now, group_hz=group_hz,
            )
        )
        if escaped:
            out.escaped = True
            log.info("bill %s: the fly bolted at step %d", bill.uuid[:8], step)
            break

    if not out.escaped and out.steps:
        out.settled_on = out.steps[-1].nearest
    return out


def verdict(w: Walk, scored: Scored, inverted: bool) -> str:
    """The vote implied by where the fly ended up.

    The pot it settled on names the question that carried it; the sign of that channel's
    score says which way that question points. The rejection-motion flip is applied by the
    decoder, identically to every other arm.
    """
    from karbes.riigikogu.model import EI_HAALETANUD

    if w.escaped or w.settled_on is None:
        return EI_HAALETANUD
    signed = scored.scores.get(w.settled_on, 0.0)
    if signed == 0.0:
        return EI_HAALETANUD
    turn = decode.Turn(
        left_spikes=0 if signed > 0 else 1, right_spikes=1 if signed > 0 else 0,
        baseline=0.0, dead_band=0.0,
    )
    return turn.vote(inverted)
