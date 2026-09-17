# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Kärbes** ("fly") is a MaleCNS v1.0 *Drosophila* connectome simulation cast as a notional 102nd member
of the Estonian Riigikogu (which has 101 real seats). Real bills go in, an LLM scores them on topic
axes, those scores drive olfactory neuron populations in a spiking simulation of a real fly brain, and
descending-neuron activity is decoded into for/against/decline. Its voting record is then compared to
the 101 humans to ask which faction it would join — and, crucially, whether a **randomly rewired** fly
would land somewhere different.

**`SPEC.md` is the source of truth.** Read it before any non-trivial work. It carries live
measurements of the Riigikogu corpus taken 2026-09-16 that are expensive to re-derive under the API
rate limit, and every design decision descends from them. Do not delete those numbers; date-stamp
revisions.

The rewired-graph control is not validation, it is the experiment. Treat it as a first-class deliverable.

## Commands

```sh
uv sync --extra dev --extra score   # set up (project pins Python >=3.11; system python3 is 3.9)
uv run karbes --help
uv run pytest                       # all tests
uv run pytest tests/test_corpus.py::test_voter_count   # single test
uv run ruff check . && uv run ruff format .
```

## Architecture

Pipeline, each arrow a package boundary:

```
riigikogu/  fetch + cache votes and bills
   → score/     bill text → topic score vector (OpenRouter)
   → encode.py  scores → currents into named ORN populations
   → sim/       spiking LIF over the MaleCNS graph from graph/
   → decode.py  descending-neuron rate difference → vote
   → analysis/  place Kärbes among the 101; nulls.py supplies the controls
```

- `riigikogu/` — rate-limited resumable fetcher, cache-first. `corpus.py` applies the
  substantive-vote and discriminative-vote filters that define the evaluation set.
- `analysis/` — `pretests.py` (T1–T5, the Stage 0 gate), `votematrix.py`, `agreement.py`,
  `idealpoint.py`. Runs entirely offline against the cache.
- `graph/` — loads the MaleCNS feather files into sparse matrices, assigns excitatory/inhibitory sign
  from neurotransmitter predictions, resolves named cell populations, and implements rewiring.
- `sim/` — `lif.py` is the kernel; `response.py` computes the 17-sim per-channel response matrix and
  the superposition check that makes the null ladder affordable.

Stages are gated (see SPEC.md §Stages). Stage 0 costs nothing and decides whether the headline question
is answerable at all. `graph/` and `sim/` are not written until Stage 2, so a failed gate is cheap.

## Conventions that are easy to violate

- **Cache-first, never refetch.** Riigikogu allows 1 req/s per IP and 12/min per endpoint path, and has
  no `ETag` support. Cache by UUID; a second run of anything must make zero API calls. Incremental sync
  keys off a date watermark, not conditional GETs.
- **The LIF kernel is event-driven with lazy membrane decay.** Non-negotiable: a clock-driven kernel
  that touches all 25.6M edges every one of the 5,000 steps makes Stage 3 take 139 hours instead of 2.
  The dominant cost is membrane integration, not spike propagation — decay lazily on event arrival.
  Benchmark one bill under 5s before launching a full run.
- **Body IDs are integers** everywhere. Never let them become floats or strings.
- **Never default an unscored bill to a zero vector.** A rubric failure that silently scores zeros
  produces a confident, plausible, meaningless voting record. Record it unscored and exclude it.
- **Cache writes are atomic** (`.tmp` + `os.replace`). A truncated JSON from an interrupted run parses
  as valid-but-incomplete and corrupts the evidence base silently.
- **Stage gates are machine-enforced** via `runs/gate_<stage>.json`; a stage refuses to run without its
  predecessor's passing verdict, `--force` is recorded in the manifest.
- **SHA-256 the MaleCNS source feathers and the compiled arrays**, and verify on load.
- **Every OpenRouter call sets `provider: {require_parameters: true}`** alongside the
  `json_schema` response format — schema support is per provider *endpoint*, not per model, so without
  it a request can silently route somewhere that ignores the schema. Don't hardcode model slugs or
  prices; resolve them from `/api/v1/models` and record them in the run manifest.
- **Vote states:** the fly emits POOLT / VASTU / **EI_HAALETANUD**. Not `ERAPOOLETU` — real MPs
  essentially never use it (0.1% of slots).
- **Rejection motions (`Tagasi lükkamine`) have inverted polarity**: supporting a bill means voting
  VASTU on a motion to kill it. The flip lives in the decoder and must be applied identically to every
  control arm.
- **Never tune a threshold to maximise agreement with a faction.** The primary statistic is
  threshold-free (AUC on the continuous readout). See SPEC.md §4 — this is the difference between a
  result and a rigged one.
- **Any control arm gets the identical fitting procedure as the real fly.** No exceptions.
- Every run writes an audit log with the selected cell IDs, the decoded stimulus, and real spend.
- Estonian source text is cached verbatim; written deliverables are in English.

## Disk

`data/` is gitignored and unbacked. If you need to reclaim space, the order is
`data/raw/llm/` (superseded, nothing reads it) → the 1 GB
`connectome-weights-*.feather` → the small feathers → `csr-malecns-v1.0.npz`.

**Never delete `data/raw/voting/` or `data/raw/draft/`** — that is an 80-minute
rate-limited re-harvest, and it is the expensive thing in the directory even though it is
not the big thing.

Deleting the weights feather promotes `csr-malecns-v1.0.npz` from disposable to precious:
the CSR is what the kernel reads, and without the feather it can no longer be rebuilt.
Delete one or the other, never both. Full table in SPEC.md.

## Tone

Deadpan-scientific. Label outputs *simulated, wiring-constrained, engineered I/O mapping*. The I/O
mapping is engineered, not discovered — there are no "aye" neurons in a fly. Make no claims about what
the fly experiences. A negative result ("the connectome adds nothing over a 16-parameter linear
readout") is a valid and pre-committed outcome — report it plainly rather than fishing for a win.

MPs' voting records are public data and fair to analyse, but the subject is the fly. No
"which MP votes most like an insect" leaderboards.

## Data

MaleCNS v1.0 is CC-BY 4.0 — cite the *Cell* paper and the dataset. Riigikogu data is CC BY-SA 3.0.
Reference repos vary: `philshiu/Drosophila_brain_model` is MIT but FlyWire-era (use as a spec, not a
dependency); `YijieYin/connectome_data_prep` has **no licence file** — do not copy code from it.

GitHub remotes must be **HTTPS, never SSH**.
