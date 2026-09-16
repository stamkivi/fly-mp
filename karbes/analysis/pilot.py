"""Stage 1: the rubric pilot.

Cheap, and the real gate on everything downstream. It answers one question — does the rubric
carry political signal the connectome could conceivably use — and four questions about whether
the scores are trustworthy enough to believe the first answer.

  P1  test-retest      is a score stable across repeated calls?
  P2  inter-model      do two different models agree on what a bill is?
  P3  collinearity     are there really eight dimensions, or one?
  P4  political signal do the scores beat the majority baseline AND the T5 content ceiling?
  P5  leakage audit    can the model just call the vote outright?

P4 is the one that matters. P1-P3 decide whether P4 is measuring anything.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

import numpy as np

from karbes.analysis.votematrix import SUPPORT, build, discriminative_mask
from karbes.gates import require_gate, write_gate
from karbes.riigikogu.coalition import ERAS
from karbes.riigikogu.corpus import load_bills, load_votes
from karbes.score import rubric
from karbes.score.openrouter import Scorer, resolve_models

log = logging.getLogger(__name__)

CHEAP = "google/gemini-2.5-flash-lite"
STRONG = "openai/gpt-5-mini"

PILOT_BILLS = 40
RETEST_BILLS = 12
LEAK_BILLS = 20

#: An axis whose repeat-to-repeat SD exceeds this on a [-1,1] scale is noise, not a measurement.
MAX_RETEST_SD = 0.30
#: Axes that two models disagree about are not measuring a shared concept.
MIN_MODEL_CORR = 0.60
#: Above this, "eight dimensions" is a false description and the framing must collapse.
MAX_PC1_SHARE = 0.70
#: The fly's fair benchmark from Stage 0 T5: content-only features, no initiator.
T5_CONTENT_CEILING = 0.74
#: If a model can call the vote from bill text this often, the pipeline is contaminated.
MAX_LEAK_ACCURACY = 0.85


def stratified_sample(votes, bills, n: int, seed: int = 0) -> list:
    """Spread the pilot across eras, vote kinds, and contested vs lopsided bills."""
    rng = random.Random(seed)
    buckets: dict[tuple, list] = {}
    for v in votes:
        bill = bills.get(v.draft_uuid)
        if bill is None or not bill.has_text:
            continue
        era = next((e.key for e in ERAS if v.when and e.contains_iso(v.when[:10])), "?")
        key = (era, v.kind, bool(bill.government_bill))
        buckets.setdefault(key, []).append(bill)

    picked: dict[str, object] = {}
    keys = sorted(buckets)
    while len(picked) < n and any(buckets[k] for k in keys):
        for k in keys:
            if not buckets[k] or len(picked) >= n:
                continue
            b = buckets[k].pop(rng.randrange(len(buckets[k])))
            picked.setdefault(b.uuid, b)
    return list(picked.values())


def score_bills(scorer: Scorer, bills: list, tag: str = "") -> dict[str, dict]:
    out: dict[str, dict] = {}
    system = rubric.system_prompt()
    for i, bill in enumerate(bills, 1):
        v = scorer.complete(
            system, rubric.bill_prompt(bill), schema=rubric.SCHEMA, tag=f"{tag}{bill.uuid}"
        )
        if v is None:
            continue  # recorded as a failure; never defaulted to zeros
        try:
            out[bill.uuid] = {f: float(v[f]) for f in rubric.FIELDS}
        except (KeyError, TypeError, ValueError) as exc:
            scorer.failures[bill.uuid] = f"bad fields: {exc}"
        if i % 10 == 0:
            log.info("  scored %d/%d (%s)", i, len(bills), scorer.model)
    return out


def p1_test_retest(cache: Path, bills: list) -> dict:
    """Same bill, repeated calls, at temperature 0 and 0.7."""
    out: dict = {}
    for temp, repeats in ((0.0, 3), (0.7, 3)):
        runs = []
        for r in range(repeats):
            with Scorer(CHEAP, cache, temperature=temp) as s:
                runs.append(score_bills(s, bills, tag=f"retest-t{temp}-r{r}-"))
        common = set.intersection(*(set(r) for r in runs)) if runs else set()
        sds = {}
        for f in rubric.FIELDS:
            per_bill = [np.std([run[u][f] for run in runs]) for u in common]
            sds[f] = round(float(np.mean(per_bill)), 3) if per_bill else float("nan")
        out[f"temp_{temp}"] = {"bills": len(common), "mean_sd": sds}
    noisy = [f for f, sd in out["temp_0.0"]["mean_sd"].items() if sd > MAX_RETEST_SD]
    out["noisy_axes"] = noisy
    out["passes"] = not noisy
    return out


def p2_inter_model(a: dict[str, dict], b: dict[str, dict]) -> dict:
    common = sorted(set(a) & set(b))
    corrs = {}
    for f in rubric.FIELDS:
        x = np.array([a[u][f] for u in common])
        y = np.array([b[u][f] for u in common])
        if x.std() < 1e-9 or y.std() < 1e-9:
            corrs[f] = 0.0
        else:
            corrs[f] = round(float(np.corrcoef(x, y)[0, 1]), 3)
    weak = [f for f, c in corrs.items() if c < MIN_MODEL_CORR]
    return {
        "bills": len(common),
        "correlations": corrs,
        "weak_axes": weak,
        "passes": len(weak) <= 2,
    }


def p3_collinearity(scores: dict[str, dict]) -> dict:
    x = np.array([[s[f] for f in rubric.AXIS_NAMES] for s in scores.values()])
    if len(x) < 5:
        return {"error": "too few scored bills"}
    x = x - x.mean(axis=0)
    sv = np.linalg.svd(x, compute_uv=False)
    var = sv**2
    var = var / var.sum() if var.sum() else var
    per_axis_sd = {
        f: round(float(np.std([s[f] for s in scores.values()])), 3) for f in rubric.FIELDS
    }
    return {
        "pc1_share": round(float(var[0]), 3),
        "pc2_share": round(float(var[1]), 3) if len(var) > 1 else 0.0,
        "dims_for_90pct": int(np.searchsorted(np.cumsum(var), 0.90) + 1),
        "per_axis_sd": per_axis_sd,
        "flat_axes": [f for f, sd in per_axis_sd.items() if sd < 0.05],
        "passes": float(var[0]) <= MAX_PC1_SHARE,
    }


def p4_political_signal(vm, scores: dict[str, dict]) -> dict:
    """Can the topic scores predict each bloc's line, out of sample?

    Compared against two bars: the majority baseline, and Stage 0's content-only ceiling,
    which used the curated descriptors the model also sees. Beating the first means the
    scores carry signal; beating the second means the bill *text* added something the tags
    did not.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rows, keep = [], []
    for j, v in enumerate(vm.votes):
        s = scores.get(v.draft_uuid)
        if s is None:
            continue
        rows.append([s[f] for f in rubric.FIELDS])
        keep.append(j)
    if len(rows) < 25:
        return {"error": f"only {len(rows)} scored votes", "n": len(rows)}

    x = np.array(rows)
    out: dict = {"n_votes": len(rows), "factions": {}}
    for faction in vm.faction_names():
        line = vm.faction_line(faction)[keep]
        valid = ~np.isnan(line)
        y = (line[valid] == SUPPORT).astype(int)
        if valid.sum() < 25 or len(np.unique(y)) < 2:
            continue
        majority = float(max(y.mean(), 1 - y.mean()))
        folds = min(5, int(min(np.bincount(y))))
        if folds < 2:
            continue
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
        acc = float(cross_val_score(model, x[valid], y, cv=folds).mean())
        out["factions"][faction] = {
            "n": int(valid.sum()),
            "majority": round(majority, 3),
            "rubric": round(acc, 3),
            "over_majority": round(acc - majority, 3),
            "over_t5_content": round(acc - T5_CONTENT_CEILING, 3),
        }
    beats = [r for r in out["factions"].values() if r["over_majority"] > 0.05]
    out["beats_majority"] = len(beats)
    out["passes"] = len(beats) >= 2
    return out


def p5_leakage(cache: Path, bills: list, votes_by_bill: dict) -> dict:
    """Ask the model to call the vote outright. If it can, the fly is not deciding anything."""
    correct = total = 0
    answers = []
    with Scorer(CHEAP, cache, temperature=0.0) as s:
        for bill in bills:
            v = votes_by_bill.get(bill.uuid)
            if v is None:
                continue
            text = s.complete(
                "You are an expert on Estonian parliamentary politics. Answer in one sentence.",
                rubric.leak_probe_prompt(bill),
                tag=f"leak-{bill.uuid}",
                max_tokens=120,
            )
            if not text:
                continue
            said_pass = any(
                w in text.lower()
                for w in ("will pass", "likely pass", "yes", "is likely to be adopted")
            )
            actually_passed = v.in_favor > v.against
            total += 1
            correct += int(said_pass == actually_passed)
            answers.append(
                {"bill": bill.title[:60], "said_pass": said_pass, "passed": actually_passed}
            )
    acc = correct / total if total else 0.0
    return {
        "n": total,
        "accuracy": round(acc, 3),
        "contaminated": acc >= MAX_LEAK_ACCURACY,
        "passes": acc < MAX_LEAK_ACCURACY,
        "sample": answers[:5],
    }


def run_pilot(cache_root: Path, force: bool = False, verbose: bool = True) -> int:
    require_gate("stage0", force=force)

    votes = load_votes(cache_root)
    bills = load_bills(cache_root)
    vm = build(votes).subset(discriminative_mask(votes))

    sample = stratified_sample(vm.votes, bills, PILOT_BILLS)
    log.info("pilot sample: %d bills", len(sample))

    models = resolve_models([CHEAP, STRONG])
    log.info("models: %s", ", ".join(f"{m['id']} (${m['prompt_per_m']}/M)" for m in models))

    with Scorer(CHEAP, cache_root, temperature=0.0) as s_cheap:
        cheap_scores = score_bills(s_cheap, sample, tag="main-")
        cheap_usage = s_cheap.usage
        cheap_fail = dict(s_cheap.failures)

    with Scorer(STRONG, cache_root, temperature=0.0) as s_strong:
        strong_scores = score_bills(s_strong, sample, tag="main-")
        strong_usage = s_strong.usage
        strong_fail = dict(s_strong.failures)
    if not strong_scores:
        # The comparison model is a nice-to-have; losing it must not abort the gate.
        log.warning(
            "comparison model %s scored nothing: %s",
            STRONG,
            next(iter(strong_fail.values()), "unknown"),
        )

    p1 = p1_test_retest(cache_root, sample[:RETEST_BILLS])
    p2 = (
        p2_inter_model(cheap_scores, strong_scores)
        if strong_scores
        else {
            "error": f"{STRONG} produced no scores",
            "passes": False,
            "bills": 0,
            "correlations": {},
            "weak_axes": [],
        }
    )
    p3 = p3_collinearity(cheap_scores)
    p4 = p4_political_signal(vm, cheap_scores)

    votes_by_bill = {}
    for v in vm.votes:
        votes_by_bill.setdefault(v.draft_uuid, v)
    p5 = p5_leakage(cache_root, sample[:LEAK_BILLS], votes_by_bill)

    passed = all(x.get("passes", False) for x in (p1, p2, p3, p4, p5))
    spend = round(cheap_usage.cost + strong_usage.cost, 4)
    gate = write_gate(
        "stage1",
        passed,
        {
            "models": models,
            "sample_bills": len(sample),
            "scored_cheap": len(cheap_scores),
            "scored_strong": len(strong_scores),
            "failures": {"cheap": cheap_fail, "strong": strong_fail},
            "spend_usd": spend,
            "calls": cheap_usage.calls + strong_usage.calls,
            "p1_test_retest": p1,
            "p2_inter_model": p2,
            "p3_collinearity": p3,
            "p4_political_signal": p4,
            "p5_leakage": p5,
        },
    )
    if verbose:
        _report(models, sample, cheap_scores, p1, p2, p3, p4, p5, spend, passed, gate)
    return 0 if passed else 1


def _short(name: str) -> str:
    return (
        name.replace("fraktsioon", "")
        .replace("Eesti ", "")
        .replace("Sotsiaaldemokraatliku Erakonna", "SDE")
        .replace("Konservatiivse Rahvaerakonna", "EKRE")
        .replace("Reformierakonna", "REF")
        .replace("Keskerakonna", "KESK")
        .strip()
    )


def _ok(flag: bool) -> str:
    return "PASS" if flag else "FAIL"


def _report(models, sample, scores, p1, p2, p3, p4, p5, spend, passed, gate) -> None:
    print("\n" + "=" * 72)
    print("STAGE 1 PILOT — is the rubric worth scaling?")
    print("=" * 72)
    print(f"\n{len(sample)} bills, {len(scores)} scored, ${spend:.4f} spent")
    for m in models:
        print(f"  {m['id']:<34} ${m['prompt_per_m']}/M in  ${m['completion_per_m']}/M out")

    print(f"\nP1  test-retest            {_ok(p1['passes'])}")
    for k in ("temp_0.0", "temp_0.7"):
        sds = p1[k]["mean_sd"]
        worst = sorted(sds.items(), key=lambda kv: -kv[1])[:3]
        print(f"    {k}: worst axes " + ", ".join(f"{f} {sd:.2f}" for f, sd in worst))
    if p1["noisy_axes"]:
        print(f"    noisy (SD > {MAX_RETEST_SD}): {', '.join(p1['noisy_axes'])}")

    print(f"\nP2  inter-model agreement  {_ok(p2['passes'])}   n={p2['bills']}")
    for f, c in sorted(p2["correlations"].items(), key=lambda kv: kv[1]):
        mark = "  <- weak" if c < MIN_MODEL_CORR else ""
        print(f"      {f:<12} r={c:+.2f}{mark}")

    print(f"\nP3  collinearity           {_ok(p3.get('passes', False))}")
    if "error" not in p3:
        print(
            f"    PC1 {p3['pc1_share']:.0%}, PC2 {p3['pc2_share']:.0%}, "
            f"{p3['dims_for_90pct']} dims for 90% of variance"
        )
        if p3["flat_axes"]:
            print(f"    near-constant axes: {', '.join(p3['flat_axes'])}")

    print(f"\nP4  political signal       {_ok(p4.get('passes', False))}")
    if "error" in p4:
        print(f"    {p4['error']}")
    else:
        print(
            f"      {'bloc':>8} {'n':>4} {'majority':>9} {'rubric':>8} {'vs maj':>8} {'vs T5':>7}"
        )
        for f, r in sorted(p4["factions"].items(), key=lambda kv: -kv[1]["rubric"]):
            print(
                f"      {_short(f):>8} {r['n']:>4} {r['majority']:>9.3f} "
                f"{r['rubric']:>8.3f} {r['over_majority']:>+8.3f} {r['over_t5_content']:>+7.3f}"
            )
        print(f"    (T5 content-only ceiling was {T5_CONTENT_CEILING:.2f} — the fly's fair bar)")

    print(f"\nP5  leakage audit          {_ok(p5['passes'])}")
    print(
        f"    model predicted the outcome from bill text on {p5['accuracy']:.0%} "
        f"of {p5['n']} bills (contaminated at >= {MAX_LEAK_ACCURACY:.0%})"
    )

    print("\n" + "-" * 72)
    print(f"GATE stage1: {_ok(passed)}   ->  {gate}")
    print("-" * 72 + "\n")
