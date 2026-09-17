# Handoff: the one-bill replay slice

You are picking this up on **uv-mac-mini**. Read `SPEC.md` first — especially
*"The deliverable is a replay, not a report"*, *"Current task"*, and *"Engineering constraints"*.
`CLAUDE.md` has the conventions that are easy to violate.

## The one question this task answers

**Does the brain animation read as a fly brain, or as particle soup?**

Everything downstream — 30 bills, season mode, the 3-D fly body — depends on that answer. So build
*one* bill end to end and look at it. Do not build thirty.

## Before you start

`./bootstrap.sh` is running (or has finished). It harvests the Riigikogu corpus (~80 min, rate
limited), downloads the 1.06 GB connectome, compiles the CSR, and scores bills with Jev. Check
`bootstrap.log`. Everything it does is cached and resumable, so a re-run is cheap and safe.

**You can start step 1 immediately** — the bundle format needs no data. Steps 2–3 need the
bootstrap finished.

Disk is tight: **~4 GB free**, and the pipeline wants ~2 GB. If you run short, the 1 GB weights
feather is only needed to *recompile* the CSR; `data/malecns/csr-malecns-v1.0.npz` is what the
kernel reads. Delete the feather and keep its hash in `sha256.lock.json` rather than deleting the
compiled graph.

## Build this

### 1. `karbes/replay.py` — the bundle generator

One bundle per bill, JSON plus a small binary blob:

- bill title, summary, committee, date, and the real chamber tally
- the nine Jev channels: **score and confidence** (confidence is the point — see below)
- ORN drive per channel, **weighted by confidence**, so a channel Jev could not read drives weakly
- spike raster downsampled to ~100 frames, stored sparse as `(neuron_index uint16, frame uint8)`
- the left/right DN race as a per-frame series
- the verdict, and the fly's resulting position on the ideal-point line

Budget: ~45 KB per bill sparse, against a 16 MB page limit.

### 2. `karbes/atlas.py` — the soma atlas

Sample ~16,000 of the **139,662 neurons that carry real 3-D `somaLocation` coordinates**, quantised
to uint16 (~94 KB). Keep `superclass` so optic lobes, central brain and nerve cord are separable
and can be labelled on screen. This is shared across all bills, written once.

### 3. The page

Replace the illustrative canvas in the published artifact with playback of the real bundle.
Sequence per bill, about twenty seconds:

1. the bill arrives — real Estonian title
2. it becomes a smell — channels light, **intensity from score, sharpness from confidence**
3. the brain fires — real soma positions, activity spreading antennal lobe → central brain → cord
4. the race — left DN against right DN
5. the verdict — a cell flips on the tabulaator; the fly's dot slides along the political line

**The viewer votes first** (poolt / vastu / decline) before the fly decides. That is what makes
anyone watch a second bill.

## Things that will bite you

- **SNR is ~0.5 and that is deliberate.** The fly genuinely wavers; re-running the same bill with
  a different input phase moves the readout more than changing a channel does. Do **not** average
  it away to make the fly look decisive — a brain visibly making up its mind is the entire point.
  Show it, and say so on the page.
- **`weight_scale = 0.05e-3`**, not the published 0.275. At 0.275 the network runs at ~50 Hz. At
  0.02 it is physiological but the descending neurons never fire. 0.05 is the lowest scale where
  the readout is alive at all. This is calibrated, not inherited — say so in any writeup.
- **Read all ~1,304 descending neurons**, not a hand-picked few. With 51 the zero-input left/right
  asymmetry was −4.577 Hz, larger than any stimulus effect; with all of them it is +0.011 Hz.
- **Never fabricate a score.** A bill Jev cannot read is excluded and counted, never defaulted to
  zeros — that produces a confident, plausible, meaningless voting record with nothing to flag it.
- **Body IDs stay integers.** Floats silently break every join.
- Do not commit `.env` or anything under `data/`. Both are gitignored; keep it that way.

## Definition of done

- `uv run pytest` passes, `uv run ruff check karbes/ tests/` clean
- one bundle generated from a real bill and committed as a fixture under `tests/`
- the page plays it back, published, URL reported
- **an honest written answer to "fly brain or particle soup?"** — including "particle soup", if
  that is what it looks like. A negative answer here is worth more than a polished one that hides it.
- push to `origin master` so it can be reviewed remotely

## Do not

- build thirty bills, season mode, or the 3-D fly body yet
- re-tune `weight_scale` hoping SNR improves — that was tried at length; it is a network property
- re-run the LLM rubric hoping to beat the content ceiling — measured, it does not, and `SPEC.md`
  records why
