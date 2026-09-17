# Fly brain, or particle soup?

*Stage 2b, the one-bill replay slice. Measured on uv-mac-mini, 2026-09-17, against MaleCNS
v1.0 (166,700 neurons / 25,582,938 edges / 124,177,616 synaptic contacts — reproducing the
published figures to within one synapse) and the XV Riigikogu corpus.*

## The short answer

**The picture is a fly brain. The vote is not a vote.**

The animation works: real soma coordinates, real spikes, activity propagating antennal lobe
→ central brain → nerve cord in the correct anatomical order, and the central brain visibly
carrying the response while the optic lobes stay dark. That is the question the slice was
built to answer, and the answer is yes.

Building it, however, put a measurement in reach that had not been made: **does the bill
change what the fly does?** It does not. Driving every channel to +1 versus every channel to
−1 — the largest stimulus contrast this encoding can produce — moves the descending readout
by **−0.09 ± 0.38 Hz (t = −0.24)**. SPEC's Stage 2 verification says of the stimulus sweep:
*"a flat line is failure."* Measured properly, the line is flat.

The cause is identified below and it is not the readout, the encoder, or the scoring. It is
that **the network has two states — silent and saturated — and no graded regime in between.**

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

`nature`, the channel that looked like a 4.12 Hz effect, is **+0.37 ± 0.43 Hz** over 24 phases
per pole.

### 2.2 Nor will a longer simulation help

Worth recording so it is not tried. Within a single run the readout has a correlation time of
~13 ms, so the 350 ms scoring window already holds ~26 effectively independent samples, and
the implied standard error of one run's mean is 0.60 Hz. The spread actually observed *across*
phases is 1.61 Hz — **2.7× larger**.

So the variance is a per-phase *run-level offset*, not within-run drift. Doubling the
simulated duration would take the noise from 1.61 Hz to about 1.55 Hz. Only averaging across
seeds reduces it, as 1/√n.

### 2.3 The stimulus does not move anything

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

**Nothing responds.** Not the readout, not a different readout, not the region the input
lands in. Changing the decoder would not have helped.

### 2.4 Why: the network is bistable, not graded

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

This explains every other symptom at once: the flat sweep, the phantom SNR, the fly's
"wavering", and the earlier observation that `weight_scale` 0.02 leaves the descending neurons
silent while 0.05 brings them to life. Those two scales are not a range containing a working
point — **they are the two sides of a bifurcation.**

### 2.5 So the wavering is not deliberation

Same bill, same scores, same wiring, eight input phases: **6 declined, 1 Poolt, 1 Vastu**,
Δ ranging −1.93 to +1.70 Hz. It is on the page, labelled.

SPEC frames this as content — *a brain visibly making up its mind* — and it reads that way on
screen. But given 2.3, the honest description is narrower: **the input phase is the only thing
the readout responds to.** The fly is not making up its mind about the bill; it is not
responding to the bill at all. The page should not, and now does not, claim otherwise.

---

## What this does and does not invalidate

**Still standing.** The connectome pipeline (compiles to the published figures), the kernel
(1.8–3.5 s per bill, event-driven as required), the Jev scoring, the atlas, the bundle format,
the page, and the propagation result in Part 1. The measurement harness is what found this.

**Not standing.** `SNR ≈ 0.5`, `SNR = 0.88`, and any per-channel sensitivity ranking. The true
full-scale effect is consistent with zero, bounded by roughly ±0.8 Hz at 95%.

**Stage 3 as designed would produce a voting record of noise.** 784 bills × 5 seeds against a
stimulus effect indistinguishable from zero yields a record whose correlation with any faction
is chance. The rewired-graph control — the actual experiment — would then compare one
stimulus-blind random voter against twenty others and find, correctly, no difference. That is
not a negative result about connectomes; it is a null instrument.

## What would have to change first

Not for me to decide, and deliberately not attempted here — `weight_scale` was left at the
calibrated 0.05e-3 throughout, per the handoff.

1. **Get the network below self-excitation and drive it harder.** The reason 0.02 looked dead
   is probably correct behaviour: a non-self-sustaining network only fires where the input
   drives it, and sixteen ORN populations are too small an input to reach the descending
   neurons through the feedforward path. Widening the input — more glomeruli, or projecting
   scores onto antennal-lobe projection neurons rather than receptor neurons — is the lever,
   not a higher weight scale.
2. **Add what keeps a real brain off this cliff.** The kernel has no spike-frequency
   adaptation, no synaptic depression and no global inhibitory normalisation. A recurrent
   network of 25.6M excitatory-dominated synapses without any of them has no stable
   intermediate state, which is exactly what the sweep shows.
3. **Make the sweep a gate.** It is cheap (16 × n sims) and it is the difference between a
   study and a decorated random number generator. It should run, and pass, before Stage 3 is
   launched — and `karbes calibrate` now reports which channels are separable from the noise
   at all, which on the current model is none of them.

## Incidental

- **The raster is 6.7× the size budget.** SPEC assumes ~45 KB per bill at ~5 Hz. At 22 Hz the
  raster is 303 KB (151,271 events), the bundle JSON 58 KB, the finished page 630 KB. One bill
  is fine; thirty would be ~9.1 MB against a 16 MB limit. Levers: halve the frames to 50, halve
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

## Reproducing

```sh
uv run karbes calibrate          # dead band, sweep with standard errors  (~12 min)
uv run karbes replay             # bundle + page for one bill             (~1 min)
uv run pytest
```

Raw measurements behind every number above: `runs/calibration.json`, `runs/power_test.json`,
`runs/readout_test.json`, `runs/ignition.json`. All read from cache and the compiled CSR;
none re-fetch anything.
