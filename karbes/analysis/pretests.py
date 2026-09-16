"""Stage 0 pre-tests T1-T5. No LLM, no simulator — these decide whether the headline
question is answerable at all, using only the cached vote matrix.

T1  pairwise discordance   is there resolution between factions?
T2  content-blind sweep    does a marginal alone determine the party? (rigging check)
T3  dimensionality         what is the real effective N?
T4  interpretive scale     the anchors without which no fly number is readable
T5  metadata-only ceiling  how much signal is in the bill's surface, before any LLM?
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path

import numpy as np

from karbes.analysis.votematrix import (
    OPPOSE,
    SUPPORT,
    VoteMatrix,
    build,
    discriminative_mask,
)
from karbes.gates import write_gate
from karbes.riigikogu.corpus import load_bills, load_votes

log = logging.getLogger(__name__)

#: Below this many discordant votes, two factions cannot be told apart (McNemar-style
#: power: at d=20 you need 14/20 to reject at 95%; at d=8 nothing is detectable).
MIN_DISCORDANCE = 20
MIN_SPLIT_PATTERNS = 30


def t1_discordance(vm: VoteMatrix) -> dict:
    """The number of votes on which two factions took opposing lines.

    This, not the column count, is the sample size for distinguishing A from B.
    """
    factions = vm.faction_names()
    lines = {f: vm.faction_line(f) for f in factions}
    matrix: dict[str, dict[str, int]] = {a: {} for a in factions}
    for a, b in itertools.combinations(factions, 2):
        both = ~np.isnan(lines[a]) & ~np.isnan(lines[b])
        d = int((both & (lines[a] != lines[b])).sum())
        matrix[a][b] = matrix[b][a] = d
    for f in factions:
        matrix[f][f] = 0

    pairs = {f"{a} | {b}": matrix[a][b] for a, b in itertools.combinations(factions, 2)}
    worst = min(pairs.items(), key=lambda kv: kv[1]) if pairs else ("", 0)
    return {
        "factions": factions,
        "matrix": matrix,
        "pairs": pairs,
        "min_pair": worst[0],
        "min_discordance": worst[1],
        "passes": worst[1] >= MIN_DISCORDANCE,
    }


def t2_content_blind_sweep(vm: VoteMatrix, step: float = 0.05) -> dict:
    """Sweep a fly that ignores content: supports with prob p, opposes with prob q.

    For each (p, q) record which faction it matches best. If every plausible marginal
    lands in one faction's region, a threshold-calibrated headline is pre-determined and
    AUC must be the primary statistic.
    """
    rng = np.random.default_rng(0)
    factions = vm.faction_names()
    lines = np.vstack([vm.faction_line(f) for f in factions])  # (F, V)
    n = lines.shape[1]

    winners: dict[str, int] = {}
    grid = []
    ps = np.arange(0.0, 1.0 + 1e-9, step)
    for p in ps:
        for q in np.arange(0.0, 1.0 - p + 1e-9, step):
            draw = rng.random(n)
            fly = np.where(draw < p, SUPPORT, np.where(draw < p + q, OPPOSE, 0.0))
            agree = np.nanmean((lines == fly[None, :]).astype(float), axis=1)
            best = factions[int(np.argmax(agree))]
            winners[best] = winners.get(best, 0) + 1
            grid.append((round(float(p), 3), round(float(q), 3), best))

    total = sum(winners.values())
    dominant = max(winners.items(), key=lambda kv: kv[1])
    return {
        "winners": winners,
        "cells": total,
        "dominant_faction": dominant[0],
        "dominant_share": dominant[1] / total,
        # If one faction wins nearly every cell, the marginal alone picks the party.
        "marginal_determines_party": dominant[1] / total > 0.8,
    }


def t3_dimensionality(vm: VoteMatrix) -> dict:
    """SVD of the centred stance matrix, plus the count of distinct split patterns."""
    x = np.nan_to_num(vm.stance, nan=0.0)
    x = x - x.mean(axis=1, keepdims=True)
    sv = np.linalg.svd(x, compute_uv=False)
    var = sv**2
    var = var / var.sum() if var.sum() else var

    patterns = {tuple(np.nan_to_num(vm.stance[:, j], nan=9.0)) for j in range(vm.shape[1])}
    return {
        "votes": vm.shape[1],
        "members": vm.shape[0],
        "var_dim1": float(var[0]) if len(var) else 0.0,
        "var_dim2": float(var[1]) if len(var) > 1 else 0.0,
        "distinct_split_patterns": len(patterns),
        "passes": len(patterns) >= MIN_SPLIT_PATTERNS,
    }


def t4_scale(vm: VoteMatrix) -> dict:
    """Anchors: constant flies, and the distribution of real MP-to-faction agreement."""
    factions = vm.faction_names()
    lines = {f: vm.faction_line(f) for f in factions}

    const = {}
    for label, value in (
        ("always_support", SUPPORT),
        ("always_oppose", OPPOSE),
        ("always_decline", 0.0),
    ):
        const[label] = {f: float(np.nanmean((lines[f] == value).astype(float))) for f in factions}

    own, cross = {}, {}
    latest = vm.latest_faction()
    for f in factions:
        agreements, others = [], []
        for i, mid in enumerate(vm.member_ids):
            row = vm.stance[i]
            valid = ~np.isnan(row) & ~np.isnan(lines[f])
            if valid.sum() < 10:
                continue
            a = float((row[valid] == lines[f][valid]).mean())
            (agreements if latest.get(mid) == f else others).append(a)
        own[f] = float(np.median(agreements)) if agreements else float("nan")
        cross[f] = float(np.median(others)) if others else float("nan")

    return {
        "constant_flies": const,
        "own_faction_agreement_median": own,  # the realistic ceiling
        "other_member_agreement_median": cross,
    }


def t5_metadata_ceiling(vm: VoteMatrix, bills: dict) -> dict:
    """Cross-validated logistic regression from bill *surface* features to each faction's
    line — no LLM. Tells us the LLM's headroom before we pay for anything."""
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    feats, keep = [], []
    for j, v in enumerate(vm.votes):
        bill = bills.get(v.draft_uuid)
        if bill is None:
            continue
        f = {f"desc={d}": 1.0 for d in bill.descriptors}
        f[f"committee={bill.committee}"] = 1.0
        f[f"type={bill.draft_type}"] = 1.0
        f["government"] = 1.0 if bill.government_bill else 0.0
        f[f"kind={v.kind}"] = 1.0
        feats.append(f)
        keep.append(j)

    if len(feats) < 30:
        return {"error": "too few bills with metadata", "n": len(feats)}

    x = DictVectorizer(sparse=False).fit_transform(feats)
    out = {}
    for faction in vm.faction_names():
        line = vm.faction_line(faction)[keep]
        valid = ~np.isnan(line)
        y = (line[valid] == SUPPORT).astype(int)
        if valid.sum() < 30 or len(np.unique(y)) < 2:
            continue
        majority = float(max(y.mean(), 1 - y.mean()))
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
        acc = float(cross_val_score(model, x[valid], y, cv=5).mean())
        out[faction] = {
            "n": int(valid.sum()),
            "majority_baseline": round(majority, 3),
            "metadata_accuracy": round(acc, 3),
            "headroom": round(acc - majority, 3),
        }
    return out


def run_pretests(cache_root: Path, verbose: bool = True) -> int:
    votes = load_votes(cache_root)
    if not votes:
        raise SystemExit("no cached votes — run `karbes harvest` first")

    vm_all = build(votes)
    vm = vm_all.subset(discriminative_mask(votes))
    bills = load_bills(cache_root)

    t1 = t1_discordance(vm)
    t2 = t2_content_blind_sweep(vm)
    t3 = t3_dimensionality(vm)
    t4 = t4_scale(vm)
    t5 = t5_metadata_ceiling(vm, bills)

    passed = t1["passes"] and t3["passes"]
    gate = write_gate(
        "stage0",
        passed,
        {
            "corpus": {
                "substantive_votes": len(votes),
                "discriminative_votes": vm.shape[1],
                "unique_bills": len({v.draft_uuid for v in votes}),
                "bills_cached": len(bills),
                "bills_without_text": sum(1 for b in bills.values() if not b.has_text),
                "members": vm.shape[0],
            },
            "t1_discordance": t1,
            "t2_content_blind": t2,
            "t3_dimensionality": t3,
            "t4_scale": t4,
            "t5_metadata_ceiling": t5,
        },
    )

    if verbose:
        _report(votes, vm, bills, t1, t2, t3, t4, t5, passed, gate)
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


def _report(votes, vm, bills, t1, t2, t3, t4, t5, passed, gate) -> None:
    print("\n" + "=" * 72)
    print("STAGE 0 PRE-TESTS — is the question answerable?")
    print("=" * 72)
    print(
        f"\ncorpus: {len(votes)} substantive votes, {vm.shape[1]} discriminative, "
        f"{len({v.draft_uuid for v in votes})} bills ({len(bills)} cached)"
    )
    no_text = sum(1 for b in bills.values() if not b.has_text)
    print(f"        {no_text} bills have no introduction text (cannot be scored)")

    print(f"\nT1  pairwise discordance   {'PASS' if t1['passes'] else 'FAIL'}")
    print(
        f"    weakest pair: {_short(t1['min_pair'].split(' | ')[0])} vs "
        f"{_short(t1['min_pair'].split(' | ')[1])} = {t1['min_discordance']} "
        f"(need >= {MIN_DISCORDANCE})"
    )
    for pair, d in sorted(t1["pairs"].items(), key=lambda kv: kv[1])[:5]:
        a, b = pair.split(" | ")
        print(f"      {_short(a):>8} vs {_short(b):<8} {d:>4}")

    print("\nT2  content-blind sweep")
    print(
        f"    a fly that ignores every bill best-matches {_short(t2['dominant_faction'])} "
        f"in {t2['dominant_share']:.0%} of the marginal grid"
    )
    print(
        f"    marginal alone determines the party: {t2['marginal_determines_party']}"
        f"  -> AUC must be primary"
        if t2["marginal_determines_party"]
        else ""
    )

    print(f"\nT3  dimensionality         {'PASS' if t3['passes'] else 'FAIL'}")
    print(f"    dim 1 explains {t3['var_dim1']:.1%}, dim 2 {t3['var_dim2']:.1%}")
    print(
        f"    {t3['distinct_split_patterns']} distinct split patterns "
        f"(need >= {MIN_SPLIT_PATTERNS}) <- the real effective N"
    )

    print("\nT4  interpretive scale — always-support fly vs each faction's line")
    for f, a in sorted(t4["constant_flies"]["always_support"].items(), key=lambda kv: -kv[1]):
        own = t4["own_faction_agreement_median"].get(f, float("nan"))
        print(f"      {_short(f):>8}  always-support {a:.0%}   own-faction ceiling {own:.0%}")

    print("\nT5  metadata-only ceiling (no LLM)")
    if "error" in t5:
        print(f"    {t5['error']}")
    else:
        print(f"      {'faction':>8}  {'n':>4}  {'majority':>8}  {'metadata':>8}  {'gain':>6}")
        for f, r in sorted(t5.items(), key=lambda kv: -kv[1]["headroom"]):
            print(
                f"      {_short(f):>8}  {r['n']:>4}  {r['majority_baseline']:>8.3f}  "
                f"{r['metadata_accuracy']:>8.3f}  {r['headroom']:>+6.3f}"
            )

    print("\n" + "-" * 72)
    print(f"GATE stage0: {'PASS' if passed else 'FAIL'}   ->  {gate}")
    print("-" * 72 + "\n")
