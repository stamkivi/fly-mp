# Fly brain, or particle soup?

*Stage 2b, the one-bill replay slice. Measured on uv-mac-mini, 2026-09-17, against MaleCNS
v1.0 (166,700 neurons / 25,582,938 edges / 124,177,616 synaptic contacts) and the XV
Riigikogu corpus.*

## The answer

**A fly brain.** Not marginally, and not only in silhouette — the activity is anatomically
ordered and the ordering is visible on screen.

But the first version of the page looked exactly like particle soup, and *why* it did turned
out to be the most useful result of the day. Both halves are below, because the failure is
more instructive than the success.

---

## 1. The soup was in the renderer, not in the brain

The first render made the optic lobes the brightest thing on screen by a wide margin. That
looked like a network firing everywhere at once with no structure.

It is the opposite of what the data says:

| group | somas drawn | mean rate over 500 ms |
|---|---:|---:|
| optic | 6,918 | **1.9 Hz** |
| central brain | 4,118 | **53.7 Hz** |
| cord | 2,672 | 10.6 Hz |
| ascending | 979 | 14.7 Hz |
| descending | 1,312 | 19.7 Hz |

The optic lobes receive **no input at all** in this simulation — there is no visual stimulus —
and they duly sit near silence. They looked brightest because the renderer accumulated every
soma's colour additively, and optic somas are packed far more densely in the projection than
anywhere else. **Density was being rendered as activity**, which inverted the single most
important fact in the picture.

The fix is structural, not cosmetic: the resting cloud is now blended with `max` so anatomy
sets the *shape*, and only spikes are summed so activity sets the *light*. Optic base colours
were darkened to match their real rate. After that the central brain visibly dominates, which
is both what the numbers say and what a fly smelling something should look like.

Worth carrying forward: **any additive point-cloud render of a connectome will lie in this
direction**, because neuron density and neuron activity are uncorrelated and density wins.

## 2. There is real propagation, in the right order

Per group, from the raster of the selected bill:

| group | first frame with a spike | ms to half its peak |
|---|---:|---:|
| central brain | 0 | 10 |
| descending | 1 | 10 |
| ascending | 1 | 15 |
| cord | 1 | 15 |
| optic | 2 | 65 |

The ORN drive lands in the antennal lobe, which sits in the central brain; the central brain
fires first, the descending neurons follow, and the cord follows them. **Antennal lobe →
central brain → nerve cord is not staged — it falls out of the wiring.** That is the claim the
animation was supposed to support, and it holds.

Only 9.5% of drawn somas fire in any given 5 ms frame, and 21.7% fire at all during the 500 ms.
This is a sparse, structured response, not a seizure.

## 3. The wave is over in 15 ms of 500

After roughly frame 3 the network is in steady state and stays there for the remaining 485 ms.
At a constant frame rate the entire propagation — the thing worth watching — is finished in
about four tenths of a second of wall clock, and what the viewer actually sees is 19 seconds of
flat plateau.

Playback is therefore **eased**: the first ten frames are held at 380 ms each and the rest run
at 118 ms. The canvas clock always shows true neural time and is labelled `slowed` while it is
slowed, so the data is not misstated — only the rate at which it is shown. Without this the
animation is technically correct and completely unwatchable.

## 4. Signal-to-noise, measured here: 0.88

`runs/calibration.json`, 20 blank-bill phases plus a 16-run stimulus sweep.

| | |
|---|---:|
| signal — mean readout span over a channel swept −1 → +1 | **1.41 Hz** |
| noise — SD of the readout on a bill that says nothing | **1.61 Hz** |
| **SNR** | **0.88** |
| dead band (1 SD, the decline threshold) | 1.61 Hz |
| network rate at background drive | 22.4 Hz |

SPEC records 0.5. This is not a contradiction and **not a re-tuning of `weight_scale`**, which
stays at the calibrated 0.05e-3: the encoder is new (a background-plus-stimulus pole pair with
confidence weighting), and it happens to buy a little more signal. The conclusion is unchanged
and unchallenged — **the noise is still larger than the signal.**

## 5. Two of the eight channels do essentially nothing

Readout span when a channel is swept from −1 to +1, everything else at zero:

| channel | span (Hz) | | channel | span (Hz) |
|---|---:|---|---|---:|
| nature | **4.12** | | who_decides | 1.15 |
| place | **2.94** | | pay | 1.11 |
| security | 1.32 | | spend | 0.46 |
| | | | burden | **0.16** |
| | | | power_over | **0.06** |

The sweep is emphatically not flat, so the connectome does convert the stimulus into
something. But the spread across channels is 69×.

This says nothing about which policy questions matter. The channel-to-glomerulus pairing is
**arbitrary and fixed** — no glomerulus in a fly means "taxes" — so this is a fact about which
glomeruli happen to reach the descending left/right asymmetry through the real wiring, and
which do not. A bill whose content lands mostly on `power_over` is, in this instrument, a bill
the fly effectively cannot smell. That belongs in any writeup of the voting record.

## 6. The fly genuinely changes its mind

The same bill, the same scores, the same wiring, eight input phases:

| | |
|---|---|
| Ei hääletanud | **6** |
| Poolt | 1 |
| Vastu | 1 |
| Δ range | **−1.93 to +1.70 Hz** |

That range is wider than *any single channel* moves the readout, and wider than six of the
eight channels can move it even from one extreme to the other. Per SPEC this is treated as
content rather than as a defect, and it is now on the page as a labelled panel rather than
buried: the reader sees eight chips, six of which say the fly declined.

The honest consequence, stated plainly: **at a dead band of one SD this fly declines on most
bills.** Whether that leaves enough decided votes to place it among the 101 is a Stage 3
question and is not answered here.

## 7. The raster is 6.7× the size budget

SPEC budgets ~45 KB per bill, assuming roughly 5 Hz. The network runs at 22.4 Hz, so:

| | |
|---|---:|
| spike events recorded (16k somas, 100 frames) | 151,271 |
| raster blob | **303 KB** |
| bundle JSON | 58 KB |
| finished page, everything embedded | 630 KB |

One bill is comfortable. **Thirty bills would be ~9.1 MB against the 16 MB limit** — feasible
but not roomy, and season mode would not fit beside it. Cheapest levers, in order: halve the
frame count to 50, drop the atlas sample to 8k, or record only the frames up to steady state at
full resolution. None of these needs deciding yet.

## 8. A zero-input baseline measures nothing

Recorded so it is not re-derived: the dead band was first defined as the spread of the readout
with **no input at all**. That returns exactly `0.0` on all ten seeds, because without drive
this network is perfectly silent at every weight scale tested.

The baseline has to be the fly smelling its own background — all sixteen ORN populations at
5 Hz, every channel scored zero. That is what `karbes calibrate` measures and what the dead
band comes from. It never looks at the chamber, so it cannot be tuned to make the voting record
agree with anybody.

---

## What is not answered here

- **Whether a rewired fly lands somewhere else.** That is the experiment, and this slice does
  not touch it.
- **Whether the fly has a seat.** One bill does not identify a position on the chamber's first
  dimension, and when the fly declines it places nothing at all. The page says so rather than
  drawing a marker.
- **Whether the connectome beats a 16-parameter linear readout.** Unchanged from SPEC, still
  open, still pre-committed as a valid negative outcome.

## Reproducing this

```sh
uv run karbes calibrate          # -> runs/calibration.json   (~3 min, 36 sims)
uv run karbes replay             # -> runs/replay/, runs/page/index.html
uv run pytest
```

Both read from cache and the compiled CSR; neither re-fetches anything.
