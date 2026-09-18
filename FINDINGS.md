# Fly brain, or particle soup?

*Stage 2b, the one-bill replay slice. uv-mac-mini, 2026-09-17/18, MaleCNS v1.0.*

## Iteration 3 — two senses and an arena (2026-09-18)

*Design locked in SPEC §"Iteration 3". Everything below §"The short answer" is the Stage 2b
record and stands as written, except where this section supersedes it.*

### The problem

Stage 2b's fly declined on every bill and every phase. The cause is arithmetic: net drive
spans ±8.0 across eight channels and **the median real bill delivers +0.187 — 2.3% of the
range**, which predicts a per-bill effect of ~0.006 against the 0.005 actually measured. A
fly that always abstains is not a member of parliament.

### The one bit, re-measured on 565 contested votes

| | |
|---|---:|
| P(advances \| **government**-tabled) | **0.993** |
| P(advances \| member or committee) | **0.104** |
| accuracy of that bit alone | **0.942** |
| majority baseline | 0.526 |

EKRE backs 94.7% of members' bills and 2.0% of government ones, mirroring Reform's
99.1%/10.9%. The scoring model is initiator-blind by construction, and the topic channels
correlate with the bit at only r = 0.10–0.44, so routing it through a second sense adds
information rather than laundering the first.

### Three arms, 60 bills, AUC against "does the bill advance"

| arm | AUC | pre-registered |
|---|---:|---:|
| smell (substance) | 0.564 | ~.74 for a *fitted* content model; a single whiff gets far less |
| **vision (who tabled it)** | **0.983** | ~.94 |
| both | 0.930 | ~.90 |

The procedural sense is not a little better than the substantive one. It is decisive.

### Vision, measured

* **Photoreceptors are unusable.** All 6,098 are histaminergic and this pack keeps only ACh,
  GABA and glutamate as presynaptic sources, so every one has **zero outgoing edges**.
  Vision enters at the motion detectors instead.
* **T4/T5**: 13,580 cholinergic cells, 13× the olfactory input surface. Driving them
  asymmetrically by eye moves the turn index with **d′ 9.67 (t 19.3)** against olfaction's
  2.63.
* **LC4 (6,362 contacts) + LPLC2 (4,862) → DNp01** monosynaptically, onto two cells. Silent
  at rest, 117 spikes at 5 Hz of drive, 635 at 150 Hz.

### The arena

Eight pots on a ring, one per channel, emitting by `|score × confidence × salience|`; which
antenna each reaches depends on the fly's heading, so the projection changes as it turns.
**The loop is the amplifier** — chemotaxis works under bad per-step SNR because a small bias
with positive feedback commits over many steps.

Four bugs stood between that idea and a fly that walks, and all four were real:

1. **The sign was inverted.** Odour on the right makes the turn index *more positive* by
   0.125, and heading is a standard maths angle, so the fly steered away from what attracted
   it. It was running anti-chemotaxis, which is why it circled.
2. **The odour field saturated.** Clamping each antenna at a ceiling meant both sides pinned
   as the fly neared a pot, so the gradient vanished exactly where it was needed. Bilateral
   comparison is a ratio and is now coded as one.
3. **The wrong baseline was subtracted.** The single-whiff offset is −0.08; under the
   arena's mid drive it is −0.48, and the residual rotated the fly continuously.
4. **It could not cross its own arena.** 0.055 body lengths per step covered 0.88 against a
   ring of 1.0, so "nearest pot" was decided by drift.

With those fixed, on the shipped bill the seeing fly homes on `who_decides` — the strongest
pot at 0.33 — while the blind fly wanders off to `burden`. The two are bit-identical for
eight steps and then separate at the reveal.

**And one more absolute threshold that fired on everything:** one-sided optic flow alone
drives DNp01 to **376 spikes**, because strong lateral motion is itself a threat cue. Alarm
has to be the excess over that, not a raw count. With it flow-relative, 4.5% of the corpus
looms hard enough to bolt.

### Not claimed

One bill, one seed. That the seeing fly homes while the blind one wanders is a single
observation, not a result — it has not been run across the corpus. The channel-to-glomerulus
pairing and the choice of which eye means "government" stay arbitrary and pre-registered. No
fly has an opinion about who tabled a bill; the fly is the exhibit, not the evidence.

---

## The short answer

**A fly brain, and now a measurable vote.** The animation draws 15,999 real soma
coordinates out of the 139,662 that carry them, the network is silent until the bill
arrives and then fires sparsely, and a bill swung from one extreme to the other moves the
fly's steering readout by **+0.276 ± 0.043 (t = 6.45, d′ = 2.63)**.

Getting there meant throwing away most of a day's conclusions. The kernel this project
carried implemented the synapse wrongly, and every dynamical result measured on it —
including a confident write-up of "the network is bistable" — described that bug. All of
it was findable in the published model and in three existing GitHub projects built on this
same connectome. **The scan should have come before the experiments.** That is the most
useful thing in this document.

---

## 1. What was wrong, and how it was found

### 1.1 The synapse

Shiu et al. integrate a synaptic variable; they do not step the membrane:

```
dv/dt = (v_0 - v + g) / t_mbr     dg/dt = -g / tau     on_pre: g += w
```

`karbes/sim/lif.py` did `v += contacts * weight_scale` — instantaneous, unfiltered, no
membrane low-pass. Per-event charge is `w × t_mbr` rather than `w × tau`: **exactly 4×**.
[TheMrRaGe/flybrain](https://github.com/TheMrRaGe/flybrain) states the failure mode
verbatim — *"instantaneous voltage jumps produce ~4× excess conductance, forcing a bogus
gain fudge. The delay is not optional."*

`weight_scale = 0.05e-3`, which `HANDOFF.md` described as calibrated and told the next
session not to re-tune, **is that fudge**: 0.275 ÷ 5.5, compensating for an unrelated
error.

Everything downstream was therefore a measurement of the bug: a network self-igniting to
22 Hz, a central brain at 99–114 Hz, a flat stimulus sweep, an SNR of zero, and a
"22-cell sparse population code". None of it is retained.

### 1.2 The readout

We picked the one option the literature rules out. flybrain scores three steering readouts
on this connectome:

| readout | d′ |
|---|---:|
| DNa02 alone | 1.11 |
| **DNa family** | **4.21** |
| all 1,310 descending neurons | **−1.70 — significant, wrong sign** |

*"It tracks residual asymmetry, not steering."* `HANDOFF.md` required reading all ~1,304
descending neurons, citing a zero-input asymmetry of −4.577 → +0.011 Hz. That suppressed a
symptom by averaging the signal away with it. Rayshubskiy et al. (*Cell* 2024) are
specific: rotational velocity tracks the left–right firing difference of DNa01/DNa02,
near-linearly across the dynamic range.

### 1.3 The contradiction nobody had to simulate to find

`SPEC.md` drove ORNs **bilaterally and symmetrically** — *"a bill does not arrive from the
left or the right"* — and then read a **left-minus-right** difference. A symmetric stimulus
cannot systematically move an antisymmetric statistic. flybrain reports the same result
from the other end: get sensory laterality wrong and *"turn response to stimulus left vs
right was 0.0000, identical to four decimals."*

---

## 2. The rebuilt instrument

**Engine.** [Kisame76/drosophila-brain-mlx](https://github.com/Kisame76/drosophila-brain-mlx)
(MIT), Shiu et al.'s equations, validated against Brian2 to SHA-256-identical per-neuron
spike counts, running on MLX/Metal. Its MaleCNS pack's `neuron_ids` are **identical** to
the retained set `graph/populations.py` resolves, so body IDs join across both. Its edge
rule is stricter than ours — a presynaptic neuron with an unknown, modulatory or
histaminergic transmitter keeps its node but contributes no outgoing edges — giving
24,469,412 edges against our 25,582,938. Ours guessed excitatory for 2,850 neurons.

**Sanity, on the same connectome our kernel saturated:**

| ORN input | network rate | active |
|---:|---:|---:|
| 0 Hz | **0.000 Hz** | 0.0% |
| 5 Hz | 2.86 Hz | 6.0% |
| 150 Hz | 4.89 Hz | 6.7% |

Silent at rest, sparse, and graded with input. None of which our kernel did.

**Encoding.** The **side carries the sign**: a positive score drives the right antenna
harder, a negative score the left. Laterality comes from `rootSide`, the only side ORNs
carry — every one of the 2,635 has `somaSide` None — which resolves 363 left and 525 right
across our sixteen glomeruli, with 409 unknown dropped rather than guessed. Per-side rates
are normalised by that side's cell count so the 363/525 imbalance is not itself a permanent
stimulus. `CHANNEL_ORNS` keeps its pole pairs but the pair no longer carries the sign; the
table is left alone rather than re-drawn, because the assignment is pre-registered.

**Readout.** `turn = (R − L) / (R + L)` over the DNa family, 16 cells a side, with the
symmetric-stimulus baseline subtracted.

---

## 3. What it measures

**The instrument is alive.** Every channel to one extreme against every channel to the
other, 12 input phases per condition:

| | |
|---|---:|
| turn, all channels right | −0.194 |
| turn, all channels left | −0.470 |
| **difference** | **+0.276 ± 0.043** |
| **t** | **+6.45** |
| **d′** | **+2.63** |

Independently reproduced at +0.378 (d′ 3.20) under a slightly stronger drive, and in the
same class as flybrain's published 4.21 for this readout.

**A single channel is a much weaker thing**, because it drives two glomeruli of sixteen:

| channel | span | t | | channel | span | t |
|---|---:|---:|---|---|---:|---:|
| **burden** | **−0.154** | **−3.43** | | place | −0.040 | −0.82 |
| **pay** | **−0.098** | **−3.09** | | security | −0.015 | −0.31 |
| spend | −0.038 | −0.89 | | nature | −0.005 | −0.11 |
| who_decides | +0.019 | +0.48 | | power_over | −0.004 | −0.11 |

**2 of 8 channels separate from the run-to-run spread at 12 phases.** The rest are a power
statement, not a null: an eighth of the full-scale effect against a 0.104 noise SD needs
roughly 40 phases per pole to resolve at t = 2.

**The bias is real and subtracted.** A blank bill still turns this fly by **−0.081**,
because the wiring is not symmetric and the antennae do not carry equal numbers of receptor
neurons. The dead band is one SD of the blank-bill turn, **0.104**, measured on the network
alone and never against the chamber.

**On the shipped bill** (the highest-salience discriminative bill in the corpus, by the
pre-registered rule) the fly turns −0.005 and declines, on all 8 input phases, with the
turn ranging −0.077 to +0.031. An honest weak reading rather than a confident meaningless
one.

### A bug this caught

The first calibration reported the full-scale contrast as **−0.101 (d′ −1.33)** — opposite
in sign to the standalone test. The cause was mine: `blank_score()` leaves salience at 0,
`salience_gain` floors at 0.25, so every sweep ran at **quarter strength** and delivered
21,645 Hz where it should deliver 66,600. Under the noise, the sign was a coin flip. Fixed
with an explicit `probe_score` at full salience. Worth recording because the wrong number
was perfectly plausible and only a disagreement between two routes exposed it.

---

## 4. The animation

### 4.1 Density is not activity

The first render summed the resting cloud additively, so the optic lobes — half the somas
drawn and far denser in projection than anything else — came out brightest purely from
packing. **Any additive point-cloud render of a connectome will lie this way**, because
neuron density and neuron activity are uncorrelated and density wins.

The fix was to blend the resting cloud with `max` so density cannot read as brightness, and
let only spikes accumulate. The *second* mistake was to also darken the optic lobes, on a
measurement from the broken kernel saying they fire at 2 Hz against the central brain's 54.
On the published engine the ordering is reversed:

| group | mean Hz | peak Hz |
|---|---:|---:|
| optic | **6.17** | 6.87 |
| cord | 4.45 | 5.69 |
| central | 3.82 | 4.44 |
| ascending | 1.18 | 2.55 |
| descending | **0.96** | 1.60 |

The resting cloud now encodes no assumption about activity at all: hue separates the
groups, brightness is flat across them, and every claim about who is firing is carried by
the spike layer and by per-group meters measured from that run.

### 4.2 Presentation choices, stated

* **Playback is eased** — the opening frames are held long and the steady state is played
  fast — because the interesting transient is a small fraction of the run. The canvas clock
  always shows true neural time and is labelled while slowed.
* **The race is a running spike total**, not a rate. Sixteen DNa cells at ~1 Hz leave most
  10 ms frames empty, so a rate series is a comb of zeros; the cumulative count is what the
  turn index is a ratio of anyway.
* **The atlas sample is stratified**, not uniform: optic 8%, central 13%, cord 20%,
  ascending 54%, descending 100%. Relative density on screen is a sampling decision.

### 4.3 Defects found and fixed along the way

* **The raster undercounts.** It is deduplicated per frame, so a cell firing twice inside
  one frame is counted once — worst exactly where the rate is highest. Per-group rates are
  now probed separately, never derived from the raster.
* **Overlapping probe groups clobbered each other.** Adding per-group meters made the atlas
  `descending` group claim the cells `dn_left`/`dn_right` were counting, and the race read
  0.3 Hz instead of 39. A silent race still lands inside the dead band and prints a
  plausible number, so nothing downstream looked wrong; a text alternative reading *"the
  left pool is at 0.0 hertz"* is what exposed it.
* **`jev.py` defaulted a missing confidence to 0.0**, which is indistinguishable from Jev's
  honest 0.0 on a channel it cannot read. It now raises. (The API always sends it; checked
  live.)
* **The ORN table had drifted from the rubric**, still keyed on `fiscal`/`market` after the
  rubric was rewritten as concrete questions. A test now catches that.

---

## 5. Sizes, now that the network is sparse

| | |
|---|---:|
| spike events in the raster | 63,694 |
| raster blob | 125 KB |
| bundle JSON | 38 KB |
| finished page, everything embedded | 379 KB |

Thirty bills is about 4.8 MB against a 16 MB limit — comfortable, where the broken kernel's
22 Hz put it at 10.6 MB.

## 6. Open

* **Which cells, and whether a decoder generalises.** The DNa family is taken from the
  literature, not fitted here. A readout fitted to *maximise stimulus sensitivity* against
  the sweep is outcome-blind and legitimate; one fitted to agree with a faction is what
  SPEC §4 forbids. The distinction must survive into any future decoder.
* **Per-channel resolution** needs ~40 phases per pole, which is affordable and has not
  been run.
* **The rewired control.** The engine ships a degree-preserving shuffled-connectome pack
  (`lif.shuffle_pack`) — that is Stage 4, already built and unused here.
* **Whether the fly has a seat.** One bill does not identify a position, and a declined
  vote places nothing.

## Reproducing

```sh
uv pip install -e ../drosophila-brain-mlx
cd ../drosophila-brain-mlx && python -m lif.compile_pack_malecns   # reuses our feathers
uv run karbes calibrate     # bias, dead band, sweep, full-scale contrast  (~7 min)
uv run karbes replay        # bundle + page for one bill                   (~17 s)
uv run pytest
```

Measurements: `runs/calibration.json`. The retracted Stage 2b numbers and their raw data
(`runs/power_test.json`, `runs/readout_test.json`, `runs/ignition.json`,
`runs/perm_test.json`) are kept as the record of what a broken kernel produces.

Sources: [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model)
· [Shiu et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10187186/)
· [TheMrRaGe/flybrain](https://github.com/TheMrRaGe/flybrain)
· [Kisame76/drosophila-brain-mlx](https://github.com/Kisame76/drosophila-brain-mlx)
· [Rayshubskiy et al., *Cell* 2024](https://www.cell.com/cell/fulltext/S0092-8674(24)00962-0)
