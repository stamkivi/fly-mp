# Kärbes — findings

*uv-mac-mini, 2026-09-17/18, MaleCNS v1.0. Newest iteration first; earlier sections are kept
as the record of what was believed when, not deleted when superseded.*

## Iteration 5 — the fly takes the chair (2026-09-19)

*Design in SPEC §"Iteration 5", revised in the night of 18–19 September after the reading
question was retired. Every link below is measured; the page is built from the
measurements, not around them.*

### Why the fly is the Speaker

The model is a reflex machine. Tested directly: the ellipsoid-body ring attractor — the fly's
compass and its working memory — holds **nothing** after input stops (zero EPG spikes in the
600 ms after a 200 ms drive; Δ7 inhibition localises the bump, nothing sustains it). Its state
is a 20 ms membrane and a 5 ms synapse. It cannot hold a position.

The one role in a parliament that is *supposed* to be a reflex is the chair: react to conduct,
not content; give the floor; ring the bell. So the fly sits in the Speaker's seat and the
sitting is played to it.

### What the brain can and cannot show, measured before building

| pathway | result | used |
|---|---|---|
| smell → lean away (DA2/CO2, innately aversive) | dead: +0.43 at one seed, +0.29 at five, → 0.00 as dose and duration rise. Small-count noise, the same trap as the per-bill coin flip and the 16.5× ratio | no |
| hearing → which side (672 JO neurons, L/R) | unreliable: both ears give a leftward sign on 2–67 spikes | no |
| motion → which side is speaking (T4/T5, sustained) | switching left→right under steady drive: **nothing visible** — T4/T5 flat at ~20k, DNa noise | no |
| text → mushroom body pattern separation | saturated: 55–59% of Kenyon cells light for anything, overlap 0.96–0.98 at every drive down to 2 Hz | no |
| **onset from silence** | the wave: ORNs 0 ms → antennal-lobe LNs 5 ms → Kenyon cells 15 ms; centroid travels 15,693→33,550 voxels | **yes** |
| **looming → escape (LC4/LPLC2 → DNp01)** | cleanest result of the project: fires 5/5 at every dose from 2 Hz, graded 20→168 spikes, seed variance ±1–2; a 300 ms pulse gives 20–24 spikes/50 ms then **zero** within 100 ms — a discrete event | **yes** |
| **escape lateralises** | left eye → DNa turn +0.67 ± 0.07; right eye → −0.92 ± 0.00 | **yes** |

The brain displays **events, not states**. Anything true for a while — who is speaking, which
side — leaves no visible mark.

### The data

The Riigikogu API documents two endpoints in its README and serves 72 (`/v3/api-docs`).
`/api/steno/verbatims` is the verbatim record with **second-resolution timestamps**, speaker,
text, and disturbances, votes and the bell inline: 30,598 speaker events across the term,
556 on 20 May 2026 (12:00→00:04 UTC, 71,719 words, 63 speakers). `/api/hallplan` gives
seat number, member, faction and the official party colours; the numbered plan itself is not
published and positions are reconstructed from seat order and the photograph from the
Speaker's desk (two blocks, six rows). `texts[]` on every draft carries the full legal text —
50,297 words for the Crisis Act — which the earlier "no bill texts" claim missed.

### The stimulus, three rules, all declared

* A speech is a **scent from the speaker's side** (ORNs, 30 Hz, for a duration that grows
  with the log of its length). Its onset out of silence is the wave. Scent never reaches the
  giant fibre.
* **Hostility makes it loom.** One five-level question to Jev per speech — how does the speaker
  treat the people addressed — with calibrated confidence. `hostility = max(0, (2−score)/2) ×
  confidence`; looming rate zero below a knee of 0.3, 40 Hz at 1.0. Validated where the record
  allows: the day's most confident "openly insulting", 0.09 at 0.92, was *"Lugupeetud
  esikloun!"* — the speech the chair reprimanded minutes later.
* A **heckle lunges** from the heckler's seat (both sides if unseated); a **vote fills the
  hall** (scent, both sides, 90 Hz).

Every event starts the brain from rest, which its measured decay makes it do anyway, with
150 ms of silence after.

**The first encoding was wrong and the smoke test caught it.** Speeches through T4/T5 fired
the giant fibre 184–335 times on every civil sentence — one-sided optic flow drives DNp01 by
itself, which `vision.py` had already found the day before. Speeches moved to scent.

### 20 May 2026, played

566 events, 316 stimuli, 252 s of biological time for 724 minutes of sitting.

| | |
|---|---:|
| fly rang the bell (giant fibre ≥ 8 spikes) | **22** |
| of which heckles | 11 of 11 |
| real chair: called for order / rang the bell for order / called time | 0 / 0 / 7 |
| fly bells within two events of a chair *conduct* action | 0 — there were none to coincide with |
| recoil direction correct, hostile from the left (n=13) / right (n=4) | **100% / 100%** |

**A speech's own scent damps the escape.** Looming alone at 9 Hz one-sided gives ~40
giant-fibre spikes per 300 ms; the same looming *during* a speech's scent on the same side
gives a median of 5:

| hostility | n | looming Hz | GF median | bells |
|---|---:|---:|---:|---:|
| 0.3–0.4 | 9 | 2.9 | 1 | 0 |
| 0.4–0.5 | 28 | 9.2 | 5 | 1 |
| 0.5–0.7 | 10 | 15.6 | 7 | 3 |
| 0.7–1.0 | 7 | 29.2 | 68 | 7 |

The network, busy with the speaker, bolts only at a confident insult. That is the connectome
doing something the encoding did not ask for, and it stays.

Per faction, the share of speeches that ring: EKRE 46%, Isamaa 22%, KESK 18%, REF 2%, E200 0%,
SDE 5%. That is the opposition asking the questions in question time, and questions are
adversarial by role; it is recorded here and kept off the page as a table.

### The transcript's own rhythm, which is what the page plays

A speaker change every 80 s; the chair's utterances median 7 s (38 of them literally
*"NAME, palun!"*), members 65 s, ministers 102 s. 66% of speeches open with a thank-you or
honorific. The day's tempo: ~50 changes an hour, a dinner lull, then **81** in the seventh
hour. 13 recorded disturbances, 6 procedural fights, 6 time bells. The page's "what the page
remembers" tally is the memory the brain lacks: mean reaction by kind of event, bells by side,
recoil direction, ritual greetings counted, and the running comparison with the real chair.

### Not claimed

That the fly judges anything. The judgement of tone is a classifier's; the connectome
contributes a lateralised escape threshold with its own dynamics, the damping above, and
the wave. That the seat map is right — it is reconstructed. That 22 bells against zero real
conduct interventions means anything on its own — on 20 May 2026 the chair only called
time, which the fly cannot do. The comparison needs a day with disorder in it; 2023-06-19
(8 calls for order, 40 recorded heckles, 1,430 speeches) is being recorded for that.

---

## Iteration 4 — the connectome is not a better predictor, it is a different person (2026-09-18)

*Design pre-registered in SPEC §"Iteration 4" before the runs that test it finished. Complete:
20 degree-preserving shuffles, the real connectome run 5 times, and 4 of the shuffles run 3
times each — 33 full-corpus records, 461 bills apiece.*

### The accuracy question is settled, and the fly loses

Cross-validated on the same 461 contested bills, from the same Jev channel scores the fly
receives:

| model | AUC on "did the bill advance" |
|---|---:|
| content only, 22 features | 0.829 |
| who tabled it, 1 feature | 0.943 |
| content + who tabled it, 23 features | **0.970** |
| **the real connectome, 166,700 neurons** | **0.688** |
| best degree-preserving shuffle of it | 0.946 |

The regressions are fitted to the outcome and the fly never sees it, so the comparison
flatters them. It is still the right comparison: if prediction were the goal nobody would
simulate a brain to do it. **This is the negative result SPEC pre-committed to** — "the
connectome adds nothing over a 16-parameter linear readout" — and it is reported as such
rather than fished around.

Three shuffles scored 0.742, 0.946 and 0.927. Two of the three beat the real wiring. There is
no reading of that under which the connectome is contributing accuracy.

### What the shuffles did that the accuracy number cannot show

They landed in different places. Identical in-degrees, out-degrees, transmitter signs and total
output per neuron; identical bills, encoder, calibration and decoder — and twenty different
voting records nearest five different parties. A regression fitted twice on the same data gives
the same answer twice. A brain rewired twice does not.

The numbers are in §"The test, run and passed" below; what matters here is that this is
invisible in an accuracy score, and it is the one thing a connectome can demonstrate that a
16-parameter readout cannot.

### The compass, and why only half of it is real

Party positions come from the Chapel Hill Expert Survey 2024 wave, Estonia, election year
2023 — this chamber, coded by political scientists with no knowledge of this project. The map
from votes to compass is fitted on the 101 humans and **frozen before any fly is projected**,
which is stricter than SPEC §4 requires: every arm gets the same fitted map, not merely the
same procedure.

Holding out a whole party and refitting:

| axis | held-out error | range of party positions |
|---|---:|---:|
| GAL-TAN (liberal–conservative) | **0.80** | 7.4 |
| economic left–right | **1.74** | 4.1 |

The chamber's dominant voting dimension carries 61% of the variance and correlates r = +0.92
with GAL-TAN, -0.41 with the economic axis. **Roll-call votes in the XV Riigikogu carry
cultural position sharply and economic position barely.** The picture has a sharp vertical and
a soft horizontal; the page draws the held-out error on the plot rather than hiding it in a
note, because that cross is nearly half the frame wide.

This is a finding about the parliament, not only about the method: in this term the
government/opposition split runs almost parallel to the liberal–conservative axis, so a
member's position on it is largely a restatement of how often they backed the coalition.

### Reliability: a single vote is barely reproducible

150 bills, three input phases, initiator bit on, readout centred on each run's own median —
which is what turns it into a vote:

| | |
|---|---:|
| phase 0 vs 1 | r = +0.135 |
| phase 0 vs 2 | r = +0.271 |
| phase 1 vs 2 | r = +0.278 |
| all three on the same side | 34.7% (a coin gives 25%) |
| signal-to-noise of the disposition | 1.11 |

Content-only, run first, was worse still (r = -0.08, -0.02, -0.09) but also had AUC 0.509 —
no signal at all — so that test was uninformative rather than negative.

**This does not settle the question.** A compass placement aggregates 461 votes, and a weak
but consistent per-bill component compounds across a record the way it does for any noisy
repeated measure. What it does settle is that the within-brain control must be run at full
corpus length in compass space rather than inferred from these correlations.

### The test, run and passed

Twenty degree-preserving shuffles at full corpus length, against the same connectome run five
times, all projected through the same frozen map.

| | compass units |
|---|---:|
| two runs of the **same** wiring (5 runs, 10 pairs) | **0.82** |
| two **different** wirings (20 shuffles, 190 pairs) | **3.12** |
| ratio | **3.8×** |
| permutation p (20,000 relabellings) | **0.008** |
| two Estonian parties, for scale | 4.80 |

Pre-registered threshold was 2×. It passes.

**The ratio fell as reruns arrived and that is not the result eroding.** It read 16.5 at two
real runs, 7.4 at three, 4.3 at four, 3.8 at five — mean pairwise distance underestimates
spread at small n, in both the numerator and the denominator, and the denominator had the
fewest points. 3.8 is the settled figure. Any number quoted from fewer than five runs was
premature.

The twenty shuffles land nearest EKRE ×11, REF ×5, KESK ×2, Isamaa ×1 and E200 ×1 — five of
the six parties in the chamber — spanning y = 2.00 to 9.11 against the chamber's own range of
1.84 to 9.26. One connectome, rewired, covers almost the whole liberal–conservative axis of the
Riigikogu.

### What almost became a false headline

The first shuffle re-run under fresh input noise scattered 2.47 compass units against the real
connectome's 0.82. Read straight, that says the measured wiring has a reproducible political
disposition and a degree-matched random one does not — *structure buys stability*, which would
have been the best claim in this project.

It was a confound. That shuffle was chosen arbitrarily and is the third-quietest of the twenty:
turn SD 0.057 against the connectome's 0.074. A quiet readout is noise-dominated whatever
produced it. Re-running three more shuffles chosen to span the readout-strength range:

| brain | kind | turn SD | within-brain spread | runs |
|---|---|---:|---:|---:|
| rewired11 | shuffle | 0.292 | 0.18 | 3 |
| rewired16 | shuffle | 0.080 | 0.65 | 3 |
| karbes | real connectome | 0.074 | 0.82 | 5 |
| rewired0 | shuffle | 0.057 | 2.47 | 3 |
| rewired5 | shuffle | 0.046 | 2.28 | 3 |

Monotone in readout strength, and **the real connectome sits mid-pack on both columns**. A
shuffle matched to it for readout strength (seed 16, SD 0.080) reproduces to 0.65 against its
0.82. Reproducibility is bought by loudness, not by being the wiring that was measured.

Recorded here because it is the kind of result that gets published: a striking effect from one
arbitrarily-chosen control arm, with the covariate that explains it one query away.

### Three more things the twenty shuffles showed

**Why the connectome predicts badly, rather than an apology for it.** AUC as reported is
direction-free by construction, so it rewards tracking the government/opposition axis either
way. Across the rewirings, distance from the chamber's midline predicts AUC at **r = 0.60** —
being a good predictor of this parliament means having picked a side in it. Kärbes lands 0.43
from the midline. It has not picked one.

**The accuracy number is the unstable one.** Five runs of the identical connectome give AUCs of
0.633, 0.712, 0.584, 0.801 and 0.688 — a range of 0.22 — while their seats move 0.82 compass
units in total. The statistic the whole accuracy framing rests on wanders more under input
noise than the position does.

**The connectome is unremarkable among its own shuffles.** It sits 1.97 compass units from the
centre of their cloud, which averages 2.49 — the 30th percentile. What a connectome buys is a
particular individual, reproducibly. It does not buy a privileged one.

### The brain on screen

The page's hero is 126,072 real `somaLocation` coordinates from MaleCNS v1.0, projected
dorsally and rendered as a two-channel fluorescence plate — depth-attenuated, depth-of-field,
tone-mapped, bloomed — with the 32 DNa descending neurons the vote is read from picked out as
a driver line. The imaging metaphor is the honest one rather than a stylisation: a nuclear
counterstain of a *Drosophila* CNS shows precisely this, cell bodies in a rind around the
neuropil. Nothing is registered to anyone else's image and no structure is invented; the
caption says it is a rendering of measured coordinates, not a photograph of a specimen.

---

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
