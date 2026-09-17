# Fly brain, or particle soup?

> ## ⚠ RETRACTION — 2026-09-17, later the same day
>
> **Everything in Part 2 below is measured on a kernel that implements the synapse wrongly,
> and most of it is already answered in published code I should have read first.** It is kept
> for the record, struck through in intent, but no number in Part 2 should be used or cited.
>
> **The implementation error.** Shiu et al.'s model — which `SPEC.md` names as the source of
> our parameters — integrates a synaptic variable, it does not step the membrane directly:
>
> ```
> dv/dt = (v_0 - v + g) / t_mbr     # g enters divided by the membrane time constant
> dg/dt = -g / tau                  # tau = 5 ms
> on_pre: g += w                    # w = contact count x 0.275 mV
> ```
>
> `karbes/sim/lif.py` instead does `v += contacts * weight_scale` — an instantaneous voltage
> step, no synaptic filtering, no membrane low-pass. A single event therefore delivers its
> whole amplitude at one instant to all ~153 targets simultaneously, instead of a ~9 ms
> rise smeared across them. `TheMrRaGe/flybrain` documents this exact failure mode in its own
> findings: *"instantaneous voltage jumps produce ~4x excess conductance, forcing a bogus gain
> fudge. The delay is not optional."* Our `weight_scale = 0.05e-3`, which the handoff describes
> as calibrated, **is that bogus gain fudge** — a factor of 5.5 pulled out of 0.275 to stop a
> network that was exploding for an unrelated reason.
>
> **So the headline diagnosis is void.** "The network is bistable", "0.02 and 0.05 are two
> sides of a bifurcation", "SNR is zero", "the sweep is flat", "22 cells carry a sparse code" —
> all of it is a description of the broken kernel, not of the connectome. The published model
> rests at **0 Hz basal firing** by design and responds sparsely: 455 of 127,400 neurons to a
> sugar stimulus. `Kisame76/drosophila-brain-mlx` runs the same model on **this same MaleCNS
> v1.0 connectome**, validated against Brian2 to SHA-256-identical spike counts. The 22 Hz
> self-ignition is ours alone.
>
> **The readout was also already solved, and we chose the one option the literature rules out.**
> `TheMrRaGe/flybrain` measures three steering readouts on MaleCNS:
>
> | readout | d' |
> |---|---:|
> | DNa02 alone | 1.11 |
> | **DNa family** | **4.21** |
> | all 1,310 descending neurons | **-1.70 — significant with the wrong sign** |
>
> Its verdict on the whole-population readout: *"it tracks residual asymmetry, not steering."*
> `HANDOFF.md` insists on reading all ~1,304 DNs and cites the -4.577 -> +0.011 Hz asymmetry
> as justification. That fixed the symptom and destroyed the signal. The steering literature
> (Rayshubskiy et al., *Cell* 2024) is specific: rotational velocity tracks the **left-right
> firing difference of DNa01/DNa02**, near-linearly across the dynamic range.
>
> Two more things it gets right that we did not:
> * the statistic is a normalised `turn_index = (R-L)/(R+L)`, not a raw rate difference;
> * the **baseline left/right bias under symmetric stimuli must be subtracted** — theirs
>   reaches -1.3 against a directional signal of ~0.08.
>
> **And the encoder and decoder were never compatible.** `karbes/graph/populations.py` drives
> ORNs *bilaterally and symmetrically* on the stated grounds that "a bill does not arrive from
> the left or the right", while `karbes/decode.py` reads a left-minus-right difference. A
> symmetric stimulus cannot systematically move an antisymmetric readout. flybrain reports the
> same: get sensory laterality wrong and *"measured turn response to stimulus left vs right was
> 0.0000, identical to four decimals."* That is a design contradiction, and no amount of
> simulation was going to resolve it.
>
> **What survives** is Part 1 (the render and playback work, though its firing rates will move
> once the kernel is fixed) and the incidental defects: the additive-render density bug, the
> raster dedup undercount, the overlapping probe groups, the Jev confidence default, and the
> ORN/rubric key drift. Those are real and are ours.
>
> Sources: [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model)
> · [Shiu et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10187186/)
> · [TheMrRaGe/flybrain](https://github.com/TheMrRaGe/flybrain)
> · [Kisame76/drosophila-brain-mlx](https://github.com/Kisame76/drosophila-brain-mlx)
> · [Rayshubskiy et al., *Cell* 2024](https://www.cell.com/cell/fulltext/S0092-8674(24)00962-0)

*Stage 2b, the one-bill replay slice. Measured on uv-mac-mini, 2026-09-17, against MaleCNS
v1.0 (166,700 neurons / 25,582,938 edges / 124,177,616 synaptic contacts — reproducing the
published figures to within one synapse) and the XV Riigikogu corpus.*

## The short answer

**The picture is a fly brain. The vote is not yet a vote — because of the decoder, not the
connectome.**

The animation works: real soma coordinates, real spikes, activity propagating antennal lobe
→ central brain → nerve cord in the correct anatomical order, and the central brain visibly
carrying the response while the optic lobes stay dark. That is the question the slice was
built to answer, and the answer is yes.

Building it put a measurement in reach that had not been made: **does the bill change what
the fly does?** Through the current readout, no. Driving every channel to +1 against every
channel at −1 — the largest contrast this encoding can produce — moves the descending readout
by **−0.09 ± 0.38 Hz (t = −0.24)**. SPEC's Stage 2 verification says of the stimulus sweep:
*"a flat line is failure."* Measured properly, the line is flat, and so is every other scalar
summary of the network tried alongside it.

But the signal is there. Against a label-permutation null, **22 of the 1,304 descending
neurons respond to the stimulus** where 3.4 would be expected by chance (p = 0.018; the most
sensitive single cell reaches |t| = 5.59, p = 0.007). SPEC's readout is the mean rate of one
side minus the mean rate of the other, so those twenty are averaged in with 1,284 that do
nothing. **The connectome transmits; the decoder discards.**

Two things cause this and they stack. The network is **bistable** — silent with no input,
~22 Hz with half a hertz of it, and only 24 Hz with two hundred times that — so its
population rate carries nothing. And the readout takes a population mean, which is precisely
the statistic that bistability pins. The fix most likely to work is a cross-validated sparse
readout, fitted against the stimulus sweep and never against a vote.

---

## Part 1 — the animation, which works

### 1.1 The soup was in the renderer, not in the brain

The first render made the optic lobes the brightest thing on screen, which looked exactly
like structureless particle soup. The data says the opposite:

| group | somas drawn | mean rate over 500 ms |
|---|---:|---:|
| optic | 6,918 | **2.1 Hz** |
| central brain | 4,118 | **100.9 Hz** |
| cord | 2,672 | 13.5 Hz |
| ascending | 979 | 21.2 Hz |
| descending | 1,312 | 30.1 Hz |

*(Rates are true spike counts. The spike raster shipped to the page is deduplicated per
frame — it only records whether a cell lit up — and at 5 ms frames a cell firing at 100 Hz
often spikes twice inside one, so counting raster entries understates the rate, worst where
the rate is highest: it reports the central brain at 53 Hz. The bundle therefore carries
separately probed per-group counts, and the on-screen meters read those.)*

The optic lobes receive no input in this simulation — there is no visual stimulus — and they
duly sit near silence, a **49×** difference against the central brain. They looked brightest
because the renderer summed every soma's colour
additively, and optic somas are packed far denser in projection than anywhere else.
**Density was being rendered as activity**, inverting the single most important fact in the
picture.

The fix is structural: the resting cloud is blended with `max` so anatomy sets the *shape*,
and only spikes are summed so activity sets the *light*. Carry this forward — **any additive
point-cloud render of a connectome will lie in this direction**, because neuron density and
neuron activity are uncorrelated and density wins.

### 1.2 The propagation is real and correctly ordered

| group | first frame with a spike | ms to half its peak |
|---|---:|---:|
| central brain | 0 | 10 |
| descending | 1 | 10 |
| ascending | 1 | 15 |
| cord | 1 | 15 |
| optic | 2 | 65 |

The ORN drive lands in the antennal lobe, which sits in the central brain; the central brain
fires first, the descending neurons follow, the cord follows them. That ordering falls out of
the wiring rather than being staged. 9.5% of drawn somas fire in a given 5 ms frame and 21.7%
fire at all during the 500 ms — sparse and structured, not a seizure.

**Caveat that matters given Part 2:** this wave is what the connectome does when it is
ignited. It looks the same regardless of which bill ignited it.

### 1.3 The wave is over in 15 ms of 500

After roughly frame 3 the network is in steady state for the remaining 485 ms. At a constant
frame rate the propagation finishes in about four tenths of a second of wall clock and the
viewer watches nineteen seconds of plateau.

Playback is therefore eased — first ten frames held at 380 ms, the rest at 118 ms. The canvas
clock always shows true neural time and is labelled `slowed` while slowed, so only the rate of
presentation is adjusted, never the data.

---

## Part 2 — the vote, which does not work

### 2.1 A single-seed sweep is not a measurement

The first calibration ran one simulation per sweep point and reported:

> nature 4.12 Hz · place 2.94 · security 1.32 · who_decides 1.15 · pay 1.11 · spend 0.46 ·
> burden 0.16 · power_over 0.06 — mean 1.41 Hz, against a 1.61 Hz noise floor, **SNR 0.88**.

**All of that is noise.** Run-to-run spread on this readout is ~1.6 Hz, so a span built from
two single runs carries ~2.3 Hz of error — larger than seven of the eight spans it reported.
The apparent ranking was a ranking of random numbers.

Seed pairing cannot rescue it: the same seed under two different stimuli gives **r = −0.11**,
because changing a channel's rate reshuffles every subsequent spike time. The seed is not a
shared noise term that cancels in a difference. Averaging is the only lever, and `sweep` now
runs every pole over `--sweep-seeds` phases and reports span, standard error and t.

Re-measured at 12 phases per pole (`runs/calibration.json`, 2026-09-17):

| channel | span (Hz) | se | t | | channel | span (Hz) | se | t |
|---|---:|---:|---:|---|---|---:|---:|---:|
| pay | −0.514 | 0.462 | −1.11 | | power_over | −0.757 | 0.543 | −1.39 |
| spend | +0.248 | 0.643 | +0.39 | | who_decides | −0.025 | 0.532 | −0.05 |
| burden | +0.810 | 0.607 | +1.33 | | nature | −0.328 | 0.470 | −0.70 |
| place | −0.659 | 0.662 | −1.00 | | security | +0.177 | 0.434 | +0.41 |

**Not one channel reaches |t| = 1.4.** `nature`, which looked like a 4.12 Hz effect on one
seed, is −0.33 ± 0.47 — and has changed sign. Mean |span| is 0.44 Hz against a 1.65 Hz noise
floor, so the SNR that `karbes calibrate` now prints is **0.27**; treat even that as an upper
bound, because |span| is biased upward when the true span is near zero and the measurement is
noisy.

### 2.2 Nor will a longer simulation help

Worth recording so it is not tried. Within a single run the readout has a correlation time of
~13 ms, so the 350 ms scoring window already holds ~26 effectively independent samples, and
the implied standard error of one run's mean is 0.60 Hz. The spread actually observed *across*
phases is 1.61 Hz — **2.7× larger**.

So the variance is a per-phase *run-level offset*, not within-run drift. Doubling the
simulated duration would take the noise from 1.61 Hz to about 1.55 Hz. Only averaging across
seeds reduces it, as 1/√n.

### 2.3 No scalar readout moves

24 phases per condition, full-scale contrast:

| contrast | effect | t |
|---|---:|---:|
| every channel +1 vs every channel −1 | −0.090 ± 0.377 Hz | −0.24 |
| every channel +1 vs a blank bill | −0.211 ± 0.421 Hz | −0.50 |
| nature +1 vs nature −1 | +0.368 ± 0.427 Hz | +0.86 |

And it is not merely the left/right readout that is blind. The same contrast, measured against
quantities that are not differences (12 phases each):

| measure | blank | all +1 | all −1 | +1 vs −1 | t |
|---|---:|---:|---:|---:|---:|
| descending pool, total rate | 28.03 | 28.00 | 29.08 | −1.08 ± 0.74 | −1.46 |
| descending pool, left/right Δ | 0.59 | 0.25 | 0.68 | −0.43 ± 0.42 | −1.04 |
| central brain (32,164 cells) | 99.05 | 99.86 | 99.87 | −0.01 ± 0.19 | −0.05 |
| whole network | 22.44 | 22.72 | 22.72 | +0.01 ± 0.09 | +0.07 |

No *scalar* responds. Not the readout, not the obvious alternatives, not the region the
input lands in.

### 2.3b But individual descending neurons do respond — the average is what destroys it

Every scalar above is a **mean over 1,304 cells**, which is only blind if the signal is
spread across them. It is not. Taking the full 1,304-dimensional descending rate vector
under the same full-scale contrast, 12 phases per condition, against a **label-permutation
null** (400 permutations — the right null here, because descending neurons are strongly
correlated and the independent-tests expectation is badly wrong):

| statistic | observed | permuted null | p |
|---|---:|---:|---:|
| descending cells with \|t\| > 3 | **22** | 3.4 ± 6.1 | **0.018** |
| most stimulus-sensitive single cell, \|t\| | **5.59** | 3.54 ± 0.70 | **0.007** |
| leave-one-out nearest-centroid accuracy | 0.625 | 0.493 ± 0.112 | 0.198 |

**The connectome does carry the stimulus to the descending neurons.** It reaches a small
number of them — on the order of twenty out of 1,304 — and SPEC's readout, the mean rate of
one side minus the mean rate of the other, averages those twenty into 1,284 that do not
respond. That is why every scalar is flat.

The obvious inference from §2.3 — that the network transmits nothing — is therefore wrong,
and it is worth naming because it is the inference a reader will otherwise draw. This is a
readout-design failure.

Held deliberately short of a claim: **which** cells is not established. They were selected
on the same runs that tested them, so their identity is not validated — the permutation null
tests whether *more signal than chance exists*, which it does, not whether these particular
cells are the carriers. A cross-validated decoder on held-out phases is the experiment that
would settle it, and it has not been run.

One boundary worth marking now, because it is the difference between a result and a rigged
one: a readout fitted to **maximise stimulus sensitivity** is outcome-blind and legitimate —
it is fitted against the sweep, and never sees a vote. A readout fitted to maximise agreement
with a faction is the thing SPEC §4 forbids. These are not the same operation and the
distinction must survive into whatever replaces the decoder.

### 2.4 Why the scalars are flat: the network is bistable, not graded

The diagnosis. Flat drive on all sixteen ORN populations, swept over input rate, 3 phases each:

| ORN input | network rate | descending pool |
|---:|---:|---:|
| **0.0 Hz** | **0.00 Hz** | **0.00 Hz** |
| 0.5 Hz | 21.42 | 25.74 |
| 1.0 Hz | 21.69 | 25.80 |
| 2.0 Hz | 22.17 | 27.22 |
| 5.0 Hz | 22.44 | 27.70 |
| 10.0 Hz | 22.67 | 28.19 |
| 25.0 Hz | 23.01 | 28.91 |
| 50.0 Hz | 23.17 | 28.83 |
| **100.0 Hz** | **23.64** | 29.21 |

Zero input leaves the network perfectly silent. **Half a hertz** on roughly a thousand cells
takes it to 21.4 Hz. Then a **200-fold** further increase in input, to 100 Hz, moves it by
10%, to 23.6 Hz.

There are two states, silent and saturated, and no input regime in which the response follows
the input. Once ignited the activity is self-sustained by recurrence, and the ~1,000 driven
ORNs are a rounding error on 166,700 neurons feeding each other. **The bill is not competing
with noise; it is competing with the network's own self-excitation, and losing by two orders
of magnitude.**

This explains every population-level symptom at once: the flat sweep, the phantom SNR, the
fly's "wavering", and the earlier observation that `weight_scale` 0.02 leaves the descending
neurons silent while 0.05 brings them to life. Those two scales are not a range containing a
working point — **they are the two sides of a bifurcation.**

Read together with 2.3b: the *population rate* is pinned by self-excitation, but the
*pattern* is not entirely. A small stimulus-dependent signal rides on top of a saturated
network, and any readout that takes a mean throws it away.

### 2.5 So the wavering is not deliberation

Same bill, same scores, same wiring, eight input phases. On the bill the shipped replay
uses — the highest-salience discriminative bill in the corpus, picked by the pre-registered
rule — the fly declines **8 times out of 8**, with Δ ranging −0.81 to +0.78 Hz against a
1.65 Hz dead band. On an earlier candidate the same procedure gave **6 declined, 1 Poolt,
1 Vastu**, Δ from −1.93 to +1.70. Both are on the page, labelled.

SPEC frames this as content — *a brain visibly making up its mind* — and it reads that way on
screen. Given 2.3 and 2.3b the honest description is narrower: **the input phase is the only
thing this readout responds to.** The brain is not silent to the bill, but the number the
verdict is taken from is, so what looks like deliberation is a coin landing. The page should
not claim otherwise, and now does not.

---

## What this does and does not invalidate

**Still standing.** The connectome pipeline (compiles to the published figures), the kernel
(1.8–3.5 s per bill, event-driven as required), the Jev scoring, the atlas, the bundle format,
the page, and the propagation result in Part 1. The measurement harness is what found this.

**Not standing.** `SNR ≈ 0.5`, `SNR = 0.88`, and any per-channel sensitivity ranking. On the
mean-rate readout the full-scale effect is consistent with zero, bounded by roughly ±0.8 Hz
at 95%.

**Also not standing: the decoder.** `decode.race` averages 1,304 cells per side. Per 2.3b
that is where the signal dies, and it is the one component of the pipeline that these
measurements condemn outright.

**Stage 3 as designed would produce a voting record of noise** — not because the connectome
is silent, but because the current readout cannot hear it. 784 bills × 5 seeds through a
mean-rate difference yields a record whose correlation with any faction is chance, and the
rewired-graph control would then compare one stimulus-blind random voter against twenty
others and find, correctly, no difference. Running it before the readout is fixed would burn
two hours to measure the decoder rather than the fly.

## What would have to change first

Not for me to decide, and deliberately not attempted here — `weight_scale` was left at the
calibrated 0.05e-3 throughout, per the handoff. In rough order of expected value:

1. **Replace the mean-rate readout with a cross-validated sparse one.** This is the cheapest
   and, on 2.3b, the most likely to work: fit a decoder on the DN population against the
   *stimulus sweep*, validate on held-out input phases, and only then use it on bills. Fitted
   against the sweep it never sees a vote, so it stays outcome-blind. If held-out accuracy is
   real, most of what looks broken here is fixed without touching the model at all.
2. **Get the network below self-excitation and drive it harder.** The reason 0.02 looked dead
   is probably correct behaviour: a non-self-sustaining network only fires where the input
   drives it, and sixteen ORN populations are too small an input to reach the descending
   neurons through the feedforward path. Widening the input — more glomeruli, or projecting
   scores onto antennal-lobe projection neurons rather than receptor neurons — is the lever,
   not a higher weight scale.
3. **Add what keeps a real brain off this cliff.** The kernel has no spike-frequency
   adaptation, no synaptic depression and no global inhibitory normalisation. A recurrent
   network of 25.6M excitatory-dominated synapses without any of them has no stable
   intermediate state, which is exactly what the ignition curve shows.
4. **Make the sweep a gate.** It is cheap (16 × n sims) and it is the difference between a
   study and a decorated random number generator. It should run, and pass, before Stage 3 is
   launched — and `karbes calibrate` now reports which channels are separable from the noise
   at all, which on the current readout is none of them.

## Incidental

- **The raster is 6.6× the size budget.** SPEC assumes ~45 KB per bill at ~5 Hz. At 22 Hz the
  raster is 299 KB (153,063 events), the bundle JSON 64 KB, the finished page 630 KB. One bill
  is fine; thirty would be ~10.6 MB against a 16 MB limit. Levers: halve the frames to 50, halve
  the atlas to 8k, or record at full resolution only up to steady state.
- **A zero-input baseline measures nothing**, because the network is exactly silent without
  input. The dead band must be measured against background drive; `karbes calibrate` does.
- **Jev returns a real 0.0 confidence** when it cannot read a channel — on the selected bill,
  `place` and `power_over` both do. That is an honest answer and the confidence weighting
  correctly drives those channels at background. `jev.py` previously defaulted a *missing*
  confidence to the same 0.0, which would have been indistinguishable; it now raises.
- **The ORN table had drifted from the rubric**, still keyed on the old abstract axes
  (`fiscal`, `market`, …) after the rubric was rewritten as concrete questions. A test now
  fails if they separate again.
- **The readout was 3 descending types; it is now all 1,304** with a lateralised soma, which is
  what the −4.577 → +0.011 Hz asymmetry fix actually requires.

## The page

Published **private** on Display, 2026-09-17:
<https://pluralplatform.dsp.so/HcPL3HY7-k-rbes-one-bill-replay-stage-2b>

It is one self-contained HTML file with the bundle, the spike raster and the soma atlas
baked in — no LLM call, no simulation and no network fetch at view time. `runs/page/index.html`
is the same file and opens from disk.

## Reproducing

```sh
uv run karbes calibrate          # dead band, sweep with standard errors  (~12 min)
uv run karbes replay             # bundle + page for one bill             (~1 min)
uv run pytest
```

Raw measurements behind every number above: `runs/calibration.json`, `runs/power_test.json`,
`runs/readout_test.json`, `runs/ignition.json`, `runs/population_test.json`,
`runs/perm_test.json`. All read from cache and the compiled CSR;
none re-fetch anything.
