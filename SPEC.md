# Kärbes — the 102nd member of the Riigikogu

## Context

The Riigikogu has 101 seats. **Kärbes** ("fly") takes a notional 102nd seat: a simulated
*Drosophila* brain (MaleCNS v1.0, released 3 Sep 2026) that is given the same bills the real chamber
votes on, decides on its own, and is then placed among the 101 humans to ask **which faction it would
join**.

The point is not to claim a fly has politics. It is to run the community's standard
`data → sensory encoding → connectome sim → motor readout → action` recipe on a civic dataset where —
unusually — there are 101 calibrated human controls voting on the identical stimulus. That makes it a
better testbed than Doom. The honest question is:

> Does fly *anatomy* contribute anything, or would any randomly rewired graph with the same degree
> distribution land in the same seat?

So the rewired control is not an afterthought — it is the experiment. Everything else is apparatus.

This document is the project's spec and the source of truth; it supersedes the planning copy it was
promoted from. Source briefing:
<https://pluralplatform.dsp.so/2CcZ0GXk-fly-connectome-briefing-malecns-v1-0>.

Measurements below were taken live on 2026-09-16 and are the evidence base for the design decisions
that follow. They are expensive to re-derive under the API rate limit — do not delete them, and
date-stamp any revision.

---

## What was verified live during planning

Probed the Riigikogu API and the MaleCNS bucket. These numbers drive the design; none are assumed.

**The API is friendlier than expected — two facts delete a lot of planned work:**

- `GET /api/votings?startDate=&endDate=` returns sittings with votings nested, each already carrying
  `relatedDraft {uuid, title, mark}` inline. No lookup needed to know what was voted on.
- `GET /api/votings/{uuid}` returns **all 101 MPs in one request**, each with `decision {code}` *and*
  `faction {uuid, name}` **as recorded at that vote** — no membership endpoint, no date-range joins
  against faction history. (It is the *formal* affiliation, which is not the same as the voting bloc —
  see below.)

`GET /api/volumes/drafts/{uuid}` returns a plain-text **`introduction`** (~4,200 chars of Estonian prose
summarising the bill), ~12 controlled-vocabulary `descriptors`, `initiators` (`Vabariigi Valitsus` vs
named MPs), `leadingCommittee`, `draftTypeCode`. **No PDF/asice parsing needed** — full bill texts are
`.asice` containers and we ignore them.

### Corpus

Measured for one parliamentary year and for the whole term. Data is current: the latest sitting
returned is 2026-09-16, i.e. today.

| Slice | One year (2025-09→2026-06) | **Full XV term (2023-04→today)** |
|---|---|---|
| Sittings / votings | 150 / 611 | 504 / 2,240 |
| Substantive votes with a bill | 258 (231 bills) | 910 (784 bills) |
| **…that actually split the chamber** (`min(for,against) ≥ 5`) | 142 (122 bills) | **568 (474 bills)** |
| └ of which rejection motions / final votes | 69 / 72 | **372 / 193** |

**Take the full term.** 4× the evaluation set for ~80 min of unattended, cached, one-time fetching and
well under $1 of LLM. N=142 cannot support a 6-faction comparison; N=568 might.

Checked for the obstruction artefact this term is known for: the 372 discriminative rejection motions
are **one per bill, 372 distinct bills**. No en-masse duplicate motions inflating N.

**Caveat found during the harvest:** those counts come from the *aggregate* fields on the votings list,
which are present even when the per-member voter list is not. A known API gap leaves some early-term
votings with tallies but **zero voters** (~6% of the first tranche fetched). Those cannot be used and
are dropped, so the usable N is below 568. `karbes pretest` reports the dropped count; take the number
it prints, not the one in the table above.

### Three findings that reshape the design

**1. Most parliamentary business carries no factional signal.** 98% of final votes pass; the median
final vote is 57–1–36; **39% of final votes have zero votes against**. A fly that always votes POOLT
agrees with the *outcome* ~98% of the time. Hence the discriminative filter above — the evaluation set
is 568 votes, not 2,240. Note this means **rejection motions carry most of the signal** (372 vs 193):
motions to kill a bill cleave the chamber along coalition/opposition lines far more cleanly than final
passage does. Any design that analyses only `Lõpphääletus` throws away two thirds of the information.

**2. `ERAPOOLETU` is functionally dead.** Across the 568 discriminative votes there are 57,368 MP-vote
slots: 40.5% POOLT / 22.2% VASTU / **0.1% ERAPOOLETU (73 instances)** / 37.2% silent-or-absent.
Estonian MPs do not abstain — they decline by sitting still, or by not turning up. So the fly's third
action is **`EI_HAALETANUD`** (present, declines), the real behavioural analogue. Mapping the deadband
to `ERAPOOLETU` would have given Kärbes a behaviour no human in the building uses.

**3. Rejection motions have inverted polarity.** On a `Tagasi lükkamine`, POOLT means *kill the bill*.
The connectome's job is only "does this bill smell good?"; the flip is bookkeeping in the decoder, not
something the fly should learn. `supports_bill → POOLT on a final vote, VASTU on a rejection motion`,
applied identically to every control arm and documented as part of the engineered interface. This also
buys a free validation test (§6).

**Factions** (June 2026): Reformierakond 37 · non-affiliated 18 · Eesti 200 13 · SDE 9 · EKRE 9 ·
Isamaa 8 · Keskerakond 7. Note Reform+E200 = 50 of 101 — short of a majority, so the "coalition line"
is not well defined without resolving the crossbench. Handled in §5.

**The embedded `faction` is *formal registration*, not voting bloc.** Defectors stay registered as
non-affiliated while voting with their new party — which is most of what that 18-member crossbench
*is*. So the formal label is unreliable exactly where the term is most interesting. This is another
reason the primary artifact is an ideal-point scaling (§5), which ignores labels entirely and recovers
blocs from behaviour; formal factions are then an overlay on that space, not the unit of analysis.

### API caveats that shape the fetcher

- **No `ETag` / `If-None-Match` support** (tracker issue #35, open). There is no cheap conditional poll,
  so the "keep sitting" mode must fetch only date ranges after the last cached sitting.
- Pagination on list endpoints is `page`/`size` (default 20), not `limit`/`offset` — but the date-range
  votings call is not paginated (504 sittings came back in one response), so this only bites if we add
  `/api/volumes/drafts` search later.
- Intermittent 500s on `/api/documents` and 403s on some `/api/files/…/download` (issue #13, closed
  won't-fix). We touch neither — one more reason to stay on `introduction` — but the fetcher still needs
  retry-with-backoff and must treat a persistent failure as a recorded gap, not a crash.
- `lang` accepts `ET`/`RU`/`EN`. Cache Estonian; English fields are not reliably populated.

### MaleCNS data

All three files live, public, CC-BY 4.0; sizes confirmed by HTTP HEAD against
`https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/`:
`body-annotations-…-minconf-0.5.feather` 13.8 MB · `body-neurotransmitters-….feather` 41.3 MB ·
`connectome-weights-…-minconf-0.5.feather` 1002.5 MB.

**Licence note:** `philshiu/Drosophila_brain_model` is MIT but FlyWire-era (last push Sep 2024) — use
as a *spec*, not a dependency. `YijieYin/connectome_data_prep` has **no licence file**; do not copy
code from it. LIF parameters come from Stonkfly's documented table (MIT), reimplemented.

---

## On cost — the real risk is not the LLM bill

784 bills × ~2,000 input tokens ≈ **1.6M input tokens, under $1** at cheap-model rates. The prototype
gate is the right instinct but it should gate on **whether there is signal to find**, not on spend: a
rubric that returns ~0.0 for every bill costs the same as a good one and wastes everything downstream.

The genuine budgets are **API wall-clock** and **simulator engineering**. At 1 req/s and 12/min per
endpoint path: 910 voting details (~76 min) + 784 drafts (~65 min), different path templates so they
interleave → **~80 minutes, unattended, once**, then cached forever. Assume 12/min is per path
*template*, not per distinct URL — the docs are ambiguous and the conservative reading costs an hour we
spend in the background anyway.

**The decisive tests cost nothing.** Stage 0 below settles whether the headline question is answerable
at all, using only the cached vote matrix — no LLM, no simulator.

---

## Method — the pipeline

```
bill (title + introduction + descriptors + initiator)
  → LLM rubric → signed topic scores + salience
  → ORN populations (one per pole) + salience → global gain
  → MaleCNS LIF, fixed neural clock
  → DN readout Δ = rate(right pool) − rate(left pool)          ← primary statistic is Δ itself
  → θ deadband → supports / opposes / declines
  → POOLT | VASTU | EI_HAALETANUD  (polarity flipped on rejection motions)
  → ideal-point scaling: Kärbes inserted as row 102 → nearest faction
  → repeat over the null ladder → does anatomy matter?
```

### 1. Topic rubric

Estonian-politics-relevant, not imported US culture war. Each in `[-1,+1]`: `fiscal` · `market` ·
`defence` · `eu` · `social` · `green` · `regional` · `state_power`. Plus `salience` in `[0,1]` — how
ideologically loaded the bill is at all, so ratifications and technical amendments score near 0 and
drive the fly toward declining, which is correct behaviour.

**Eight axes is a hypothesis, not a commitment.** Stage 1 tests whether the LLM can actually produce
eight *independent* dimensions; if PC1 explains >70% of variance the framing is false and we collapse
to the 2–3 dimensions that are real, and say so.

Metadata (`initiators`, `leadingCommittee`, `descriptors`) is kept as separate structured features so
the metadata-only control (Stage 0, T5) can use it without the LLM having laundered it into the scores.

**OpenRouter mechanics** (verified against current docs; total spend for the project is $1–4, so
optimise for JSON reliability, not price):

- Base `https://openrouter.ai/api/v1`, `Authorization: Bearer`, OpenAI Python SDK works unchanged.
- `response_format: {type: "json_schema", json_schema: {strict: true, …}}`, **plus
  `provider: {require_parameters: true}`** — schema support is per *provider endpoint*, not per model,
  so without this flag a request can silently route to a provider that ignores the schema. Validate and
  repair JSON defensively anyway.
- **Do not hardcode model slugs or prices.** The catalogue churns — a slug that was standard a year ago
  (`google/gemini-2.0-flash-001`) now 404s. At Stage 1, query
  `GET /api/v1/models?supported_parameters=structured_outputs`, pick one cheap model and one stronger
  one (needed for the inter-model check anyway), and record the resolved slugs and their live
  `pricing.prompt`/`pricing.completion` into the run manifest.
- `usage` comes back with a `cost` field by default — log real spend per run rather than estimating.
- Paid models have no OpenRouter-side request cap; keep concurrency modest (5–20) with backoff on 429.
- Prompt caching (a fixed rubric prefix with `cache_control`) is supported but worth only a few dollars
  at this volume — wire it only if the corpus grows.

### 2. Encoding — the fly smells the bill

One axis → two ORN types (positive pole, negative pole), since rates cannot be negative; injected as
fixed-rate Poisson current into named populations — the briefing's recommended pattern and the
Shiu-model "activation" idiom. `salience` scales overall drive.

Exact MaleCNS ORN type strings **must be read out of `body-annotations` first** — not hardcoded from
memory. Choose types with comparable population sizes and normalise current per neuron so no axis gets
weight purely from having more cells. Scale drive to land in measured ORN firing ranges (~5–200 Hz),
pre-registered rather than tuned.

Two caveats to test rather than assume, both in Stage 2: a pole-pair encoding read out as a
right-minus-left difference **hard-codes an opponent architecture**, and a *static* 500 ms input is
probably decoration — a network under constant drive settles in ~50–100 ms, after which recurrence does
no work. If Stage 2 confirms both, present the axes **sequentially within the 500 ms** so history and
recurrent dynamics actually enter the map. This is the single change most likely to make the connectome
matter rather than act as a fixed linear projection.

### 3. Simulation — spiking LIF, from the start

Per your call: no rate-model intermediate. Spiking LIF on the full retained graph throughout, per
Stonkfly's documented table — 0.1 ms step, τ_m 20 / τ_s 5 ms, threshold −45 mV, rest −52 mV, delay
1.8 ms, refractory 2.2 ms, weight = contact count × 0.275, ACh excitatory / GABA+glutamate+histamine
inhibitory with an explicit unknown-transmitter fallback. Retention: assigned neuronal superclasses,
drop glia/unresolved (~166.7k nodes, ~25.6M edges). Deterministic given a seed; 5 seeds per bill, modal
vote wins, vote entropy logged. A fly that flips on rerun is not a member of parliament and we should
learn that on day one.

Apple Silicon: `seohyunjun/mps-malecns-model` is a MaleCNS-specific MPS simulator and is the closest
existing starting point — evaluate it before writing a kernel, but check its licence first.

**The superposition shortcut is now load-bearing, not an optimisation.** Going straight to LIF means
the null ladder can no longer be run cheaply on a toy model, so it has to be run cheaply on the real
one. If the input channels combine approximately linearly, each connectome is fully characterised by a
~16-dimensional response matrix — **17 sims** (one per channel at unit drive, plus baseline) instead of
784. Validate on the real connectome first (Stage 2). If R² > 0.95:

- ORN-label permutation and DN-pool permutation need **no re-simulation at all** — they are
  permutations of an already-computed response matrix, so those nulls become free and can run 1,000×.
- Degree-preserving rewiring costs 17 sims per instance, so 20 rewirings ≈ 340 sims.

The real fly's headline record still runs the honest way — all 784 bills × 5 seeds ≈ 3,920 sims, so
the published voting record is genuine spiking output, not extrapolation. That is ~0.5–2 h **only with
an event-driven, lazy-decay kernel**; a naive clock-driven one makes it 139 h. See §Engineering
constraints before writing a line of the simulator.

**If superposition holds, that is itself a headline finding**, not a mere speedup: it means the fly is
an anatomy-derived linear readout and we report it plainly rather than burying it. If it fails, the
nulls get expensive and N gets cut — budget for that branch.

### 4. Readout — and why θ is not the statistic

`Δ = mean rate(right DN pool) − mean rate(left DN pool)`. An engineered interface, labelled as such —
there are no "aye" neurons in a fly.

**The primary statistic is threshold-free.** Fitting θ to match a target marginal is *not* outcome-blind:
in a chamber whose votes are near one-dimensional, a content-blind voter's best-matching faction is
approximately whichever faction's base rate is closest to its own — so calibrating the marginal very
nearly picks the party. Instead:

- **Primary:** held-out **AUC** of the continuous Δ against "did faction X's majority vote to advance
  this bill", on discriminative votes, with cluster-bootstrap CIs. Exact null at 0.5, immune to θ.
- **Secondary (the fair thresholded version):** for each faction F, fit θ on the calibration split so
  the fly's marginal matches *F's own* marginal, then measure held-out agreement with F. Every faction
  is then scored under a fly with that faction's base rates, so the winner is determined purely by
  pattern, not by marginals.
- θ survives only to produce the theatrical POOLT/VASTU/EI_HAALETANUD output. Publish the party
  assignment as a **function of θ** across a grid, disclosing the sensitivity rather than hiding it.

Chronological split as primary (robust to faction composition drifting as MPs defect); cross-fitting
over sitting-day folds as a power-preserving secondary. Report both. Identical procedure on every
control arm — otherwise the comparison is rigged in the real fly's favour.

### 5. Placing Kärbes among the 101

**The primary artifact is not a party name — it is an ideal-point scaling.** Run IRT / optimal
classification on the 101 × 568 vote matrix in 1–2 dimensions and **insert the fly as row 102**, with a
bootstrap credible region around its position. This handles the 18 crossbenchers naturally, gives a
continuous position instead of a forced categorical, makes "which party" a nearest-neighbour question
in a space the reader can *see*, and — crucially — visibly shows when the fly's uncertainty region
spans three parties. It is minutes of compute on a matrix this size, and it is the literal
interpretation of "the 102nd member".

Around it:

- **Anchors, without which no number is readable:** always-POOLT / always-VASTU / always-decline flies;
  marginal-matched random flies (1,000 draws → the null band for *any* content-blind model); the
  distribution of real MP-to-faction agreements; each MP's own-faction agreement (the realistic
  ceiling). Report the fly's **nearest human neighbour** among the 101 — a better and more robust story
  than a party name.
- **Metric:** per-MP agreement aggregated to faction as primary (faction-majority-line as secondary,
  since that is what "would join party X" colloquially means). Publish the full **3×5 confusion matrix**
  (fly state × MP state) plus per-faction state-rate tables, so that e.g. EKRE's reliance on *not
  voting* is visible rather than silently deleted. Two analyses: revealed-preference (POOLT/VASTU only,
  absence as missing) and behavioural (all declining collapsed to "no position"). Report the
  Hix–Noury–Roland Agreement Index rather than Rice, as it handles three categories properly.
- **Statistics:** two-way cluster bootstrap over **MPs and bills**. 90 bills carry both a contested
  rejection motion and a contested final vote; the fly scores both from one topic vector, so those
  votes are mechanically linked. **Max-statistic permutation correction** for the 7-way argmax — on
  each null draw record max-over-factions of (agreement − matched baseline) and compare the real fly's
  max to that distribution. Handles the selection exactly, costs nothing.
- The 18 non-affiliated MPs are never treated as a faction and never excluded: scored individually,
  clustered by vote correlation to see whether a pro-government subgroup exists.

### 6. The null ladder

The user's question — *would a randomly rewired fly pick a different party?* — is the headline. But
degree-preserving rewiring erases ORN identity so thoroughly that the rewired fly may become
near-constant across bills, at which point it is indistinguishable from a content-blind fly we can
compute in seconds. So build a ladder, cheap rungs first, and keep rewiring as the headline arm:

1. **Content shuffle** — permute topic vectors across bills (1,000×). Does output depend on input at all?
2. **ORN-label permutation** — permute which axis drives which ORN type, connectome and dynamics
   untouched. Best-powered null in the set: isolates the specific olfactory→DN mapping, cannot go
   degenerate, preserves dynamic range.
3. **DN-pool permutation** — random size-matched pools / random L-R splits.
4. **Degree-preserving rewiring** — *the headline control.* Directed double-edge swap, Q ≈ 10–20 swaps
   per edge; weights carried with edges; **neurotransmitter sign assigned per presynaptic neuron**, so
   Dale's law survives any rewiring; ORN and DN node labels unchanged. N ≥ 20 instances, or 1,000 if
   the superposition shortcut validates.
5. **Weight shuffle only**, topology fixed — separates weights from topology.

**Degeneracy must be measured, not assumed away.** Pre-specify a validity filter applied *before*
θ-fitting (across-bill IQR of Δ above a floor; no vote class above 95%). Report the fraction of rewired
instances that fail — "83% of rewired brains are politically catatonic" is itself a finding. Report the
null both with and without exclusions.

**Free validation from the polarity flip:** calibrate on final votes only, then check the 372 rejection
motions. If the fly is doing anything, its inverted stance there should match the *same* faction. No
extra fitting, pre-specifiable, hard to get right by accident.

**Optional and worth more than many rewirings:** run the identical pipeline on a *different real brain*
(FlyWire/FAFB, female). Same party → the strongest structural evidence in the project. Different party
→ a devastating, honest and genuinely funny robustness result.

### 7. What counts as success

Do not compete with the direct-input logistic regression on accuracy; it is fit to the outcome and the
fly is not. Published attempts report exactly this control winning. Compete on claims it cannot make,
in decreasing strength: **zero-fit ordering** (a zero-parameter map from bill content to a scalar with
held-out AUC above its ORN-permutation null); the **rejection-motion sign-flip** prediction; **error
structure** ("the fly defects from Reform precisely on environmental bills" beats 3pp of accuracy);
**dose–response** in salience; **consistency** on near-duplicate bills versus human bodies.

Pre-commit to the negative result as publishable: *"a 166,000-neuron connectome adds nothing over a
16-parameter linear readout of the same inputs; the politics is entirely in the LLM and the threshold."*
That is more interesting than a manufactured win, and given the priors it is the likely outcome.

The framing that survives all of the above is a **specification curve**: ~3 DN pools × 2 encodings ×
3 θ targets × 2 LLMs ≈ 36 defensible pipelines. Plot the party assignment across all of them. Stable →
a strong result. Coin flip → the multiverse plot *is* the result. This turns the project from "which
party does the fly join", which is underpowered and rig-prone, into "how robustly can a fly brain be
made to join a party", which is answerable.

**Its scope is decided by a measurement, not by a judgement call.** Run natively, 36 pipelines is
36 × Stage 3 ≈ 18–70 h — tolerable once, painful every time the rubric is revised. Stage 2's
superposition check (17 sims, about a minute) picks the branch automatically:

| Stage 2 result | Specification curve |
|---|---|
| R² > 0.95 | All 36 pipelines evaluated on the precomputed response matrix — minutes, and exact within the validated drive range |
| R² ≤ 0.95 | Trim to ~6 pre-registered pipelines run natively (~3 h); disclose the remaining degrees of freedom in prose |

Either way the honesty claim survives; only the resolution changes. Do not commit compute to this
before Stage 2 reports.

---

## Stages and gates

Each stage has a kill criterion. Do not start the next before its gate passes.

**Stage 0 — harvest + offline pre-tests. No LLM, no simulator, no cost.** This is where the project is
actually decided. Rate-limited resumable fetcher, on-disk cache keyed by UUID, never refetch; run over
the full term in the background (~80 min). Then, entirely offline against the cached 101 × 568 matrix:

- **T1 — pairwise discordance.** The 7×7 matrix of `d_AB` = votes where factions A and B took opposing
  lines. This, not 568, is the sample size for distinguishing A from B. *Kill: if d(Reform, E200) < 20,
  drop the 7-way party claim and reframe as coalition/opposition plus a continuous position.*
- **T2 — content-blind marginal sweep.** Sweep a content-ignoring fly's (p_POOLT, p_VASTU) over the
  simplex, record argmax faction for each. Produces a map marginal → party. *Kill: if plausible target
  marginals all land in one party's region, the thresholded headline is pre-determined and AUC must be
  primary.* (This is why §4 already puts AUC first — T2 confirms or relaxes it.)
- **T3 — dimensionality and effective N.** SVD of the centred vote matrix; count distinct split
  patterns. *Kill: fewer than 30 patterns → state the real N up front, claim no more than 2–3 blocs.*
- **T4 — the interpretive scale.** All anchors from §5, so that any later fly number is readable.
- **T5 — metadata-only ceiling, no LLM.** Cross-validated logistic regression predicting each faction's
  line from initiator, committee, one-hot descriptors, voting type, date. *If descriptors + initiator
  already hit the ceiling, the LLM's headroom is a few points and the fly's is smaller — know this
  before paying for anything.* Doubles as a free direct-input control for debugging.

*Gate:* 101 voters on every voting, faction strings stable, the 568-vote set reproduced from cache
alone, and T1/T3 leave enough resolution to state a defensible question.

**Stage 1 — LLM rubric pilot (~30–40 bills, stratified; a few cents).**
- **Test–retest:** 3 runs at temperature 0, 3 at 0.7. Any axis with SD > 0.3 on a [−1,1] scale is noise
  — drop it.
- **Inter-model:** cheap vs one strong model; drop axes correlating < 0.6.
- **Collinearity:** if PC1 of the 8 axes explains > 70%, the 8-dimensional framing is false — collapse
  and say so.
- **Political signal:** logistic regression from scores must beat each faction's majority baseline
  out-of-sample, *and* beat T5's metadata-only ceiling. If scores can't separate Isamaa from Reform,
  the fly has nothing to work with and no simulator rescues it.
- **Leakage audit:** score 20 bills with and without initiator/committee visible; then ask the model
  directly "will this pass, and who votes against?". *Kill: if it is ~85% accurate, the pipeline is
  contaminated and "the fly decided" is not a true sentence.*
- Hand-check 5 Estonian scorings.

**Stage 2 — LIF kernel + smoke tests, before any politics.** Build (or adopt) the spiking kernel and
characterise it on non-political input first:
- **Zero-input Δ** — quantify the bilateral asymmetry floor. With symmetric injection Δ should be ~0
  plus noise, but hemisphere proofreading completeness is *not* equal in MaleCNS, so a nonzero floor
  would mean the sign of Kärbes's votes is partly a segmentation artefact. Measure it before trusting
  any vote.
- Unit-drive response per channel (the 17 sims) → the response matrix; **superposition R²**.
- Drive sweep for the unsaturated range; time-to-steady-state (if ~50 ms, the 500 ms clock is
  decoration → switch to the sequential encoding in §2); 20 repeats of one bill for within- vs
  between-bill variance.

*Gate:* stimulus reliably changes the readout, the readout is not degenerate, and Δ's between-bill
variance exceeds its within-bill variance. A flat stimulus-sweep here kills the project honestly.

**Stage 3 — the full run.** All 784 bills × 5 seeds on the real connectome, plus the full LLM pass.
Produces Kärbes's actual voting record. *Do not start until a single bill simulates in under 5 s* —
that check is the difference between a 2-hour job and a 139-hour one.

**Stage 4 — the null ladder and the analysis.** §6 in full, §5 statistics, specification curve.
*This is the product*, not a validation afterthought.

**Stage 5 — the four deliverables.** All requested, in dependency order:
1. **Repo + written findings** — reproducible, `python -m karbes run` offline from cache, with the
   headline plot and every baseline.
2. **Watchable visualisation** — export `fly-connectome-template` replay JSON (`source.kind:
   "predicted"`, never `"measured"`; real body IDs from the bundled `ids.bin`; 2–10,000 frames, ≤10 MB;
   the template's licence requires linked credit in both the UI and the README).
3. **Published shareable page** — the story of the 102nd member, written for someone who doesn't know
   what a connectome is, with the charts and the viewer embedded or linked. Editorial line: MPs' voting
   records are public data and fair to analyse, but the piece is about the fly, not about ridiculing
   named individuals — report factions and the nearest-neighbour result without building a
   "which MP votes most like an insect" leaderboard.
4. **Live / re-runnable** — `karbes sync` fetches only sittings after the last cached one (no ETag
   support, so the date-range watermark *is* the cache key), scores new bills, votes, and appends to the
   record. Kärbes keeps sitting. Re-running the full analysis stays a separate explicit command so the
   published numbers don't silently drift.

---

## Layout

Briefing Appendix C skeleton, adapted. Stages 0–1 create only `riigikogu/`, `score/`, `analysis/` —
`graph/` and `sim/` are not written until Stage 2, so a failed gate costs nothing.

```
fly-mp/
  data/raw/         # cached API JSON keyed by uuid (gitignored)
  data/malecns/     # pinned feather files + SHA-256 lock (gitignored)
  karbes/
    riigikogu/      # fetch.py (rate-limited, resumable, watermarked), model.py, corpus.py
    analysis/       # votematrix.py, pretests.py (T1-T5), agreement.py, idealpoint.py
    score/          # rubric.py, openrouter.py (cached client)
    graph/          # load.py, sign.py, populations.py, rewire.py
    sim/            # lif.py, response.py (the 17-sim response matrix + superposition check)
    encode.py decode.py nulls.py viz.py cli.py
  runs/             # audit logs, per-bill scores, per-vote decisions, spend
  tests/
```

Conventions from the briefing's hard-won lessons: body IDs stay **integers** throughout; SHA-256 the
source feather files *and* the compiled arrays; every run writes an audit log with selected cell IDs
and the decoded stimulus; every output is labelled *simulated, wiring-constrained, engineered I/O
mapping*. Estonian source text is cached verbatim; deliverables in English. Python project (no bun).
Nothing touches Pulse or Seik. Keep the tone deadpan-scientific — engineered reinforcement signals,
no claims about what the fly experiences.

---

## Engineering constraints

Measured or derived during review. These are the things that silently wreck the project if missed.

### The kernel must be event-driven. This is not a preference.

| Implementation | Per sim | Stage 3 (3,920 sims) |
|---|---|---|
| Clock-driven, full sparse matvec every step | ~128 s | **139 h** |
| Event-driven propagation + lazy membrane decay | ~0.4–1.8 s | **0.5–2 h** |

5,000 steps × 25.58M edges = 128 G edge-ops per simulation if every edge is touched every step. The
"overnight job" figure in §Stages is only true for the second row — a naive kernel is ~40× too slow and
Stage 3 never finishes.

Note the dominant cost is **not** spike propagation. At a plausible 5 Hz mean rate, propagation is
~64M edge-ops but naive membrane integration is 5,000 × 166.7k ≈ **834M** neuron-updates. So lazy
(exponential) decay — updating a neuron's potential only when it receives an event, using the elapsed
interval — matters more than event-driven propagation alone. Build both.

*Verification:* assert wall-clock per sim is under 5 s on a single bill before launching Stage 3.

### Those hour figures are arithmetic, not measurements

Every compute estimate above is machine-agnostic: raw op counts divided by an assumed 0.5–2 G ops/sec,
a rough stand-in for one modern CPU core doing numpy-ish work. **No hardware was benchmarked.** Treat
them as order-of-magnitude. The derived quantities are the op counts, which are solid:

- ~900M ops per event-driven simulation → 0.4–1.8 s → 0.5–2 h for Stage 3's 3,920 sims
- 256–512M edge swaps per rewiring; 5–10 G across 20 instances
- 205 MB per connectome in CSR; 4.1 GB if 20 were held at once

**Where to run it.** The laptop (Apple Silicon) is the default and adequate for all of it; the
MaleCNS-specific MPS simulator flagged in §3 targets exactly this hardware and, if it works, likely
lands at the fast end. 16 GB is the Stonkfly minimum and needs headroom for the 1 GB weights file plus
the CSR. The mac mini (`uv-mac-mini`) is the better host for Stage 3 and the null ladder purely because
it is persistent — these are unattended overnight batch jobs with no interactivity, and nobody closes
its lid. Its per-core speed relative to the laptop is unknown.

**Cloud is not worth it here, and not on cost grounds.** A mid-size instance would run Stage 3 for
under $5 and even the pessimistic 70-hour curve for $15–35 (prices from memory, unverified) — trivially
affordable. But you would pay to move a 1 GB dataset and rebuild an environment for a job that finishes
overnight locally, and the fly's voting record is needed once, not fast. The **one** case where cloud
earns its keep: superposition fails at Stage 2 *and* the full 36-pipeline curve is wanted natively.
That is 18–70 h and parallelises perfectly across 36 independent runs.

**The Stage 2 benchmark — one bill, under 5 s — is the first real measurement of any of this.** Until
it runs, every hour figure in this document is arithmetic. Catching the 40× kernel error before
committing to a long run is the entire purpose of that gate.

### Graph loading and memory

- CSR with `int32` indices + `float32` weights is ~205 MB per connectome. Never hold 20 rewired
  instances at once (4.1 GB) — generate, simulate, discard, keep only the 16-d response matrix.
- Do not `pandas.read_feather` the 1 GB weights file into a DataFrame and then convert. Read column-wise
  via `pyarrow` and build CSR incrementally; the intermediate DataFrame is the memory spike, not the
  final matrix.
- Compiled arrays are cached to `data/malecns/` with a SHA-256 lock covering **both** the source feather
  and the compiled output, so a changed source invalidates the cache instead of silently reusing it.

### Rewiring cost

Q = 10–20 swaps per edge means **256–512M double-edge swaps per instance**, 5–10 G across 20 instances.
Pure-Python swapping is days. Vectorize in numpy (batch candidate swaps, reject invalid ones, repeat) and
benchmark one instance before committing to 20. If a vectorized instance exceeds ~10 min, reduce Q and
report the achieved mixing rather than the intended one.

### Fetcher

- **Two independent limits.** 1 req/s per IP *and* 12/min per endpoint path. A naive `sleep(1)` satisfies
  the first and violates the second by 5×. Implement a per-path token bucket (12/min) plus a global 1/s
  gate; the per-path limit is the binding one, and interleaving two paths is what yields ~24 req/min
  overall. The §Cost timings assume exactly this.
- **Atomic cache writes.** Write to `<uuid>.json.tmp` then `os.replace()`. A process killed mid-write
  otherwise leaves a truncated file that parses as valid-but-incomplete on the next run — the single
  most likely way this project silently corrupts its own evidence base.
- Retry with backoff on 5xx (the tracker reports intermittent 500s); after N failures record the UUID in
  a `gaps.json` and continue. A gap is data, not a crash — but the corpus counts must be re-derived with
  gaps excluded and the count reported.

### Determinism

"Deterministic given a seed" holds for a single-threaded CPU kernel. On MPS or any parallel reduction,
floating-point summation order can vary between runs. Either pin to a reproducible reduction, or drop
the determinism claim and report measured run-to-run variance instead. Do not assert determinism
without a test that runs the same bill twice and compares spike trains bit-for-bit.

### Gates must be machine-enforced

Prose gates are not gates. Each stage writes `runs/gate_<stage>.json` containing the measured values and
a boolean verdict; the next stage's entry point refuses to run without its predecessor's passing gate,
overridable only by an explicit `--force` that is recorded in the run manifest. This is ~20 lines and it
is the difference between staged discipline and a stage ordering that exists only in this document.

### Test plan — correctness of the science first

The tests that matter here are not parser unit tests. They are the ones that prevent an accidentally
rigged result:

| Test | Guards against |
|---|---|
| Polarity flip applied identically to every control arm | The fly getting a correction its nulls don't |
| θ fitting never observes the test split | Leakage into the headline number |
| Control arms run the identical fitting procedure | The comparison being rigged in the fly's favour |
| Second harvest run makes zero API calls | Cache correctness, and being a good citizen |
| `inFavor + against + neutral + abstained == 101` on every voting | Silent corpus corruption |
| Corpus counts reproduce the §Corpus table from cache alone | Regression in the filters that define the evaluation set |
| Same bill, same seed, twice → identical vote | The determinism claim |

### Failure modes registry

| Codepath | Failure | Handled? |
|---|---|---|
| Fetcher killed mid-write | Truncated cache entry reads as valid | Atomic rename (above) |
| Fetcher hits 429/500 | Missing votes skew the corpus | Backoff, then `gaps.json`, counts re-derived |
| LLM returns malformed JSON | Bill silently scored as zeros | Schema validation + repair; a bill that fails twice is recorded unscored, never defaulted |
| Rewired graph degenerates | Null looks artificially hard to beat | Pre-specified validity filter; failure rate reported |
| Superposition assumed, not measured | Nulls computed on an invalid approximation | Stage 2 gate; R² recorded in the manifest |
| MPS non-determinism | Vote entropy misattributed to the model | Determinism test above |

**Critical gap if unaddressed:** the LLM-returns-zeros case. A rubric failure that defaults to a
zero vector produces a confident, plausible, entirely meaningless voting record. Never default a score.

---

## Scoring: TypeSafe Jev replaces the LLM rubric

Measured head-to-head on the real corpus, September 2026.

| | LLM rubric (Gemini + GPT-5) | **Jev** |
|---|---|---|
| Bills scored | 725 / 751 | **751 / 751** |
| Cost | $0.90 | **$0.042** |
| Wall clock | ~20 min | **27 s** |
| Self-consistency (mean abs diff) | n/a across models; r 0.66 | **0.039** |
| Per-channel confidence | none | **calibrated** |
| Signal vs content ceiling | −0.016 | **+0.005** |

**The confidence is the reason, not the price.** Stage 1's failure mode was that two models
disagreed on abstract channels and nothing in the output said so — the disagreement was only
visible by running a second model and correlating. Jev states its own uncertainty per question.
On a nuclear-safety bill it returned `place` at 0.99 confidence (correctly: not a geographic
bill) and `who_decides` at 0.26 (honestly unsure). That lets ORN drive be **weighted by
confidence**, so a channel the model cannot read drives the fly weakly instead of driving it
with noise dressed as signal.

It is also the right instrument for the replay: a channel can be drawn with intensity from the
score and sharpness from the confidence. The fly smells some things clearly and others faintly,
which is both true and legible.

Spot checks were semantically correct where it matters: a VAT cut scores `pay` −0.76, the
Weapons Act scores `security` +0.90 with every other channel near zero, and the Family Law
amendment scores `power_over` −0.34 (it removes a restriction).

**What did not change, and was never going to.** Prediction of faction lines still sits at
roughly the content ceiling — mean +0.005 against the descriptor baseline. Bill content does not
predict Estonian parliamentary votes better than ~.74 no matter what reads it, because the votes
are driven by who tabled the bill. Jev buys a better *instrument* and a better *picture*, not a
better *prediction*. Recorded so nobody re-runs this hoping for a different answer.

Credentials live in `~/.config/typesafe/.env` and are loaded at runtime only — never copied into
this repo, `.env.example`, or settings.

---

## The deliverable is a replay, not a report

**Direction change, recorded deliberately.** The page was becoming a set of asserted
conclusions with a decorative animation attached. The original ask was something with a wow
effect that shows the fly *in action* — watchable for thirty seconds to a few minutes, in the
spirit of the community's Doom and Mario builds. A precomputed claim is not that.

### The noise is the show

Stage 2 measured a signal-to-noise ratio of **0.5** on the descending-neuron readout: moving an
axis from −1 to +1 shifts it about 1.1 Hz, while re-running the same stimulus with a different
input phase shifts it about 2.3 Hz. An hour went into trying to engineer that away.

That was the wrong instinct. **A deterministic instant verdict is boring; a brain visibly making
up its mind is the entire appeal**, and the wavering is real rather than staged. The left and
right descending pools genuinely race for 500 ms and the outcome is genuinely uncertain until
late. Keep it, show it, and report the SNR honestly beside it.

### Precompute, then play back

No LLM call and no simulation at view time — the page must survive being public. Everything is
generated offline into a **replay bundle** and shipped as data.

Per bill: the real title and summary · its nine topic scores (already computed for 725 bills) ·
the sixteen ORN channel activations · a **spike raster** downsampled to ~100 frames · the
left/right DN race as a time series · the vote · the fly's updated position on the political line.

*Assets already verified to exist:* **139,662 neurons carry real 3-D soma coordinates** in the
annotations, so the brain on screen is the actual fly brain rather than a schematic. A 16,000-soma
atlas is 94 KB as uint16; the full set is under 1 MB.

*Size budget* against the 16 MB artifact limit: shared soma atlas ~94 KB · spikes stored sparse at
3 bytes each, ~45 KB per bill · **30 bills ≈ 1.4 MB**. Comfortable.

### One bill, about twenty seconds

1. **The bill arrives** — real Estonian title, committee, date.
2. **It becomes a smell** — sixteen channel bars light from the actual topic scores.
3. **The brain fires** — real soma positions, activity spreading antennal lobe → central brain →
   nerve cord. The money shot.
4. **The race** — two curves, left DN against right DN, close on contested bills and decisive on
   obvious ones.
5. **The verdict** — a cell flips on the tabulaator; the fly's dot slides along the political line.

Then a **season mode**: two hundred votes in sixty seconds, the position converging out of nothing,
with the rewired flies running the same bills alongside and landing somewhere else. That is the
experiment, made watchable instead of described.

### What this changes

The project becomes an experience with a study underneath, rather than a study with a page
attached. Every finding in this document stays true and stays on the page; they stop being the
opening argument. **The fly's seat has to emerge on screen rather than be asserted in a sentence.**

Open: whether to incorporate a 3-D fly body model — the community reuses one (flybody / FlyGym) —
so the fly can be seen considering a bill and pressing one of the three voting buttons. Pending a
check on browser-loadable formats and licences.

---

## Design — the page and its visuals

Verified live: `GET /api/hallplan` returns all 101 occupied seats with `place`, the MP, and the faction
including `shortName` and **`colorHex`**. Place numbers run 1–118, so **seventeen numbers are
unassigned**: 6, 7, 10, 14, 16, 17, 18, 20, 65, 77, 90, 100, 106–110. Composition today (Sept 2026) has
already drifted from the June sample — REF 34, non-affiliated 22 — confirming the crossbench keeps
growing.

*Caveat:* the API gives no coordinates, so whether an unassigned number is a vacant desk, an aisle or a
reserved position is **unverified**. Do not assert "empty seats" in the published page without checking
a floor plan; "unassigned place number" is what the data actually supports.

**Kärbes does not get an invented 102nd seat. It gets one of the unassigned numbers** — 65, which sits
mid-hall. This is the whole visual identity and it costs nothing to be literal.

Seat *geometry* must be reconstructed: the API has only place numbers. Any rendered hall is therefore a
plausible fan arrangement, not a survey of the room, and should be labelled as a schematic.

### Official faction palette (from the API, not invented)

| | short | hex | | short | hex |
|---|---|---|---|---|---|
| Reformierakond | REF | `#FFC000` | EKRE | EKRE | `#2A3DA0` |
| Non-affiliated | — | `#C0C0C0` | Isamaa | I | `#6FABD4` |
| Eesti 200 | E200 | `#eb268e` | Keskerakond | KESK | `#3BAC7B` |
| SDE | SDE | `#E35558` | **Kärbes** | **KÄR** | near-black `#1A1A1A` |

Kärbes is never given a party colour of its own — it is *always* rendered in the colour of whatever it
currently matches, or in the neutral near-black when unmatched. The reader should never be able to
mistake the fly for a party.

### The page: one visual, three times

The spine is the real hall plan, rendered from real geometry, recurring at increasing sophistication.
The argument is carried by the same picture changing, not by three unrelated charts.

1. **The hook.** The hall, 101 seats in faction colours, one empty seat slowly pulsing.
   *"There are twelve empty seats in the Riigikogu. We put a fly in one."*
2. **The record.** Same hall, Kärbes's seat now filled with its best-matching faction's colour. Beside
   it, three or four real bills with the fly's vote next to the chamber's.
3. **The catch.** Same hall — but now the seat flickers between colours, one frame per rewired fly.
   If twenty rewired brains land in six different parties, the reader sees the result before reading
   a word of statistics.

**Emotional arc:** curiosity → comprehension → delight → doubt → respect. The page is built so the
reader arrives at the scepticism themselves. No lecturing; the third hall plan does the work.

### Charts

- **Rewired null — not a histogram.** A strip of small hall-plan glyphs, one per rewired fly, each with
  its seat coloured by the faction it joined. Legible in one second: *here are twenty rewired brains and
  where each one sat.* A bar chart of the same data says far less.
- **Ideal-point scaling** is the analytically primary artifact but the *secondary* chart on the page —
  a 102-point scatter with a credible region is hard on a phone. Desktop gets the scatter; mobile gets
  a one-dimensional strip of the first axis with Kärbes marked.
- **Specification curve** keeps the standard two-panel idiom (estimates above, active choices below).
  It is a known form and reads as honest; do not prettify it.
- Faction colour alone must never carry meaning — EKRE `#2A3DA0` and Isamaa `#6FABD4` are both blue.
  Seats carry `shortName` labels at desktop width, and every fill gets a dark stroke for contrast on
  both themes.

### Typography

Display **Fraunces**, body and UI **IBM Plex Sans**, data and figures **IBM Plex Mono**. Plex has full
Latin Extended coverage, so `õ ä ö ü š ž` render correctly rather than falling back mid-word — worth
checking on the first build, since bill titles are full of them. Deliberately not Inter or Roboto.

### States

| State | Specification |
|---|---|
| Viewer loading | A rendered poster frame of the brain mid-vote shows **instantly**; the Three.js scene loads behind it and swaps in. Never a spinner on a blank canvas. |
| No WebGL / reduced motion | Poster frame stays; the vote is narrated as text. `prefers-reduced-motion` disables the seat flicker and the pulse. |
| Viewer idle | "Watch one vote" — an explicit action, never autoplay. |
| Recess | "Kärbes has not voted since *date* — the Riigikogu is in recess." A real state: the chamber breaks mid-June to September. |
| Live mode, new vote | The seat animates once on arrival. Nothing else moves. |

### Editorial decisions

**Bilingual, English primary.** The page ships in English with an Estonian version behind a language
toggle. Consequences to plan for rather than discover: every chart label, axis and caption is a
translated string, so **no text is baked into chart images** — labels are rendered from a single
`strings.{en,et}.json` and figures are generated per locale. Estonian is the source language for bill
titles, faction names and vote codes; those stay verbatim in both versions and are glossed in English on
first use, never translated (`Lõpphääletus`, `Tagasi lükkamine`, `poolt`/`vastu`). The two versions
*will* drift as findings get revised — so the findings text lives in one place and the translation is a
final step before each publish, not a parallel document.

**Individual MPs are named, stated neutrally.** The nearest-neighbour result is the most robust and most
human output the analysis produces, and it is public data. It is reported as a flat statement of fact —
*"Kärbes's voting record is closest to that of [MP] ([faction])"* — once, in the findings, with the
agreement figure and its confidence interval beside it. What does not happen: no ranked list of MPs by
similarity to an insect, no MP's name in a headline or social preview, no naming anyone as *least*
fly-like. If the credible interval around the nearest neighbour overlaps several MPs, say so and name
them all rather than picking the point estimate for effect.

### Accessibility and responsive

Keyboard-reachable viewer controls; the hall plan is an image with a text alternative that states
Kärbes's seat and match in words. Minimum 44px touch targets on the seat glyphs at mobile width, which
means seats become tappable only above a breakpoint — below it the hall is a static figure. Contrast
checked against both themes; `#FFC000` and `#C0C0C0` fail as text colours and are used only as fills.

---

## Stage 0 results (measured 2026-09-16, full XV term)

Harvest complete: 504 sittings, 910 substantive votings, 784 bills, **zero gaps**. A rerun makes
**0 requests / 1,699 cache hits in 0.67 s**.

**Usable corpus: 898 substantive votes, 563 discriminative, 772 bills.** 12 votings dropped for having
tallies but no per-member list; 33 bills have no `introduction` and cannot be scored.

### T1 fails because coalition membership is the variable, and it moves

**Reform and Eesti 200 took opposing majority lines on 2 of 563 votes.** The first reading of
that — "as voting objects they are one party" — was wrong. They are *coalition partners*, and
coalition membership is a time-varying fact this spec originally failed to model at all.

The XV term is not one political world. The API describes the parliament, not the cabinet, so the
timeline is encoded by hand in `karbes/riigikogu/coalition.py` from published sources and
cross-checked against the voting record:

| Era | Span | Cabinet | Government |
|---|---|---|---|
| A | 2023-04-17 → 2025-03-10 | Kallas III, then Michal I from 2024-07-23 | REF + E200 + **SDE** |
| B | 2025-03-11 → present | Michal I | REF + E200 |

SDE was expelled on 2025-03-11. The government lost its formal majority in August 2026 after MP
defections, which is where the 22-member crossbench comes from, but the coalition's *composition*
did not change, so there are two eras rather than three.

**The voting record reproduces that boundary with no external information:**

| pair | Era A (SDE in govt), n=357 | Era B (SDE out), n=205 |
|---|---|---|
| REF vs SDE | **4** | **68** |
| E200 vs SDE | 2 | 67 |
| REF vs E200 | 1 | 1 |

Blocs are therefore era-specific: **A = {REF+E200+SDE}, KESK, EKRE, Isamaa**; **B = {REF+E200},
KESK, EKRE, Isamaa, SDE**. A whole-term "SDE" target blends two incompatible behaviours and is
meaningless; the earlier whole-term merge, which kept SDE separate, was exactly that mistake.

### T1d: the axis is government vs opposition, and it is almost everything

- Government bloc cohesion: **100%**
- Opposition cohesion: 89%
- The two sides took **opposite lines on 91% of 551 contested votes**

So "which party would Kärbes join" is not the real question and cannot be rescued — at party level
Reform and Eesti 200 are separated by one vote in three and a half years. **The answerable question
is which side it takes**, with party resolution reported only where a bloc is genuinely separable.

**A natural experiment falls out of this, and it is the best validation the project has.** Kärbes is
coalition-blind by construction: it reads bill content and never learns who is in government. So at
the 2025-03-11 boundary its agreement with the *government bloc* should hold steady while its
agreement with *SDE* shifts — SDE moved, the fly did not. That prediction is pre-specifiable, needs
no extra fitting, and is hard to satisfy by accident. It replaces the rejection-motion sign-flip as
the primary internal-consistency test.

### T5: one bit explains Estonian politics, and the fly never sees it

| feature set | E200 | REF | EKRE | Isamaa | SDE | KESK |
|---|---|---|---|---|---|---|
| procedural (vote kind) | .777 | .777 | .760 | .637 | .708 | .601 |
| **content** (descriptors + committee + type) | **.754** | **.735** | **.739** | **.658** | **.611** | **.600** |
| content + initiator | .891 | .902 | .886 | .743 | .734 | .640 |
| all | .918 | .918 | .909 | .743 | .736 | .696 |
| majority baseline | .522 | .519 | .515 | .542 | .522 | .539 |

Adding **whether the government or an MP tabled the bill** — one bit — moves the big blocs from ~.74 to
~.90. The coalition backs government bills and kills opposition ones; that is procedural signalling,
not content.

Two consequences, both binding:

1. **The fly's fair benchmark is the `content` row (~.74), not .92.** It reads bill text and never sees
   the initiator, so .92 is not its target and failing to reach it is not a finding.
2. **The Stage 1 rubric must be initiator-blind.** If the prompt sees the initiator, the topic scores
   launder that single bit and the fly's apparent performance is leakage, not comprehension. §1 already
   passed metadata "as context" — that is now forbidden for `initiators`; it stays a separate feature
   for the control only.

### T2, T3, T4

- **T2:** a content-blind fly best-matches Eesti 200 across 50% of the marginal grid — concentrated but
  below the 80% threshold, so the marginal does not fully determine the answer. AUC stays primary.
- **T3 passes:** 560 distinct split patterns out of 563, dimension 1 explains 56.1% and dimension 2
  only 7.5%. Strongly one-dimensional, as expected.
- **T4:** an always-support fly scores 52% against REF/E200 and 33–46% elsewhere — **much weaker than
  feared**, because the discriminative filter and the rejection-motion inversion balance the set. The
  always-POOLT confound in §5 is real but far smaller than assumed. Realistic ceilings (own-faction
  agreement): REF .89, E200 .85, SDE/EKRE .71, KESK .67, Isamaa .60.

---

## Stage 1 results (full corpus, 725 bills, $0.90)

Gate **FAIL**. Decisive this time, not underpowered: n is 370–533 votes per bloc and the 95% CI
half-width is ±0.04.

| | result |
|---|---|
| **P1 test-retest** | **PASS** — SD ≤0.02 at temperature 0, ≤0.10 at 0.7 |
| **P2 inter-model** | **FAIL** — `regional` .52, `state_power` .55, `social` .57 below the 0.60 bar |
| **P3 collinearity** | **PASS** — PC1 37%, PC2 20%, six dimensions for 90% of variance |
| **P4 political signal** | see below — the headline result |
| **P5 leakage** | **PASS** — the model calls outcomes at 61%, near chance |

### The finding: bill text adds nothing over subject tags

The rubric sees a bill's descriptors, committee, type **and its full explanatory summary**. The
Stage 0 `content` baseline sees everything except the summary. So the comparison isolates exactly
what reading the text is worth.

| bloc | n | tags only | LLM rubric | gap | significant? |
|---|---|---|---|---|---|
| SDE | 470 | .611 | .657 | **+0.046** | yes, better |
| EKRE | 492 | .739 | .724 | −0.015 | no |
| REF | 533 | .735 | .720 | −0.015 | no |
| KESK | 388 | .600 | .575 | −0.025 | no |
| E200 | 533 | .754 | .719 | −0.035 | no |
| Isamaa | 370 | .658 | .584 | **−0.074** | yes, worse |

One bloc better, one worse, four indistinguishable. **Reading the explanatory text of an Estonian
bill carries no predictive signal beyond its curated subject tags.** That is a finding about
parliament, not a defect in the rubric, and it compounds the Stage 0 result: content is worth ~.74,
the initiator bit is worth ~.90, and the prose behind the tags is worth nothing at all.

Dropping the three disputed axes (P4b) makes it worse, not better — every bloc falls except KESK
and Isamaa by ~0.01. The reliable axes are the topical ones, and topic is what the tags already encode.

### What this means for the fly

The rubric's job was never to beat the descriptors. It is to give the connectome a **small,
continuous, interpretable** stimulus — nine named channels a bill can arrive on. It does that,
reproducibly (P1), multi-dimensionally (P3), without leakage (P5). Parity with the tags is
information about the chamber, not a reason to discard it.

Recorded honestly for the write-up: Kärbes's input signal is no better than free metadata, so its
ceiling is ~.72 against ~.90 for anything that knows who tabled the bill. The remaining question —
whether the *connectome* does anything with the signal it gets — is untouched by this and is what
the rewired control answers.

**Carried forward as a known limitation:** `regional` (.52), `state_power` (.55) and `social` (.57)
are not reproducible across models. `regional` fires on few bills; the other two are genuine scope
disputes that survived an explicit scope rule. They stay in the rubric, flagged, rather than being
dropped after the fact on a threshold I chose.

---

## Status

| Step | State |
|---|---|
| Repo initialised, skeleton + `.gitignore` | done |
| `SPEC.md` promoted from plan | done (this file) |
| `CLAUDE.md` via `/init` | done |
| Stage 0 — harvest + offline pre-tests (T1–T5, era-aware) | **done, gate PASS** (see above) |
| Stage 1 — LLM rubric, full corpus | **done, gate FAIL on P2; finding recorded** |
| **Stage 2 — LIF kernel + smoke tests** | **next** |

Stage 0 is the decision point: it runs with no LLM and no simulator, and its T1/T3 kill criteria
determine whether the 7-faction question is answerable at all or must be reframed as
coalition/opposition plus a continuous position. Nothing downstream should be built until it passes.

---

## Verification

- **Stage 0:** re-derive the corpus table above from cache alone; assert `inFavor + against + neutral +
  abstained == 101` on every voting; assert 100% cache hit rate on a second run (zero duplicate API
  calls); T1–T5 emit a one-page "is this question answerable?" report.
- **Stage 1:** test–retest SD table, inter-model correlation table, PCA scree, held-out AUC per faction
  vs both the majority baseline and the T5 metadata ceiling, leakage-audit delta.
- **Stage 2:** stimulus-sweep plot (Δ vs each axis swept −1→+1, others at 0 — a flat line is failure);
  zero-input Δ distribution vs the bilateral asymmetry floor; superposition R²; time-to-steady-state.
- **Stage 3:** per-bill vote entropy across 5 seeds; assert the fly's marginal is not >90% one class;
  logged OpenRouter spend matches the estimate.
- **Stage 4:** the headline plot — the ideal-point space with the 101 MPs, Kärbes's position and its
  credible region, and the rewired flies' positions overlaid; plus the specification curve.
- **Stage 5:** replay JSON validates against the template's rules (real body IDs, visible brain groups,
  frame count and size limits, strictly increasing time); `karbes sync` on an already-current cache
  makes **zero** API calls.
- End-to-end: `python -m karbes run` reproduces everything in `runs/` from cache with **no network**.
