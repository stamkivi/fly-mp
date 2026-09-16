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
from karbes.riigikogu.coalition import ERAS, alignment_at, era_at
from karbes.riigikogu.corpus import load_bills, load_votes, voterless_votings

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


def t1c_by_era(vm: VoteMatrix) -> dict:
    """Discordance recomputed inside each coalition era.

    Whole-term discordance is misleading whenever a party changes side mid-term. SDE is
    exactly that case, so a target built across the boundary blends two behaviours.
    """
    import datetime as _dt

    out: dict = {"eras": {}}
    dates = [v.when[:10] for v in vm.votes]
    for era in ERAS:
        mask = np.array([bool(d) and era.contains(_dt.date.fromisoformat(d)) for d in dates])
        if mask.sum() < 30:
            continue
        sub = vm.subset(mask)
        t1 = t1_discordance(sub)
        out["eras"][era.key] = {
            "label": era.label,
            "cabinet": era.cabinet,
            "coalition": sorted(era.parties),
            "votes": int(mask.sum()),
            "min_pair": t1["min_pair"],
            "min_discordance": t1["min_discordance"],
            "pairs": t1["pairs"],
            "blocs": t1b_blocs(t1),
        }

    # Did any faction change side between eras? That is the finding, not an anomaly.
    switched = []
    keys = [e.key for e in ERAS]
    for f in vm.faction_names():
        sides = {
            e.key: ("government" if f in e.parties else "opposition")
            for e in ERAS
            if e.key in out["eras"]
        }
        if len(set(sides.values())) > 1:
            switched.append({"faction": f, "sides": sides})
    out["switched_sides"] = switched
    out["era_keys"] = [k for k in keys if k in out["eras"]]
    return out


def t1d_government_axis(vm: VoteMatrix) -> dict:
    """How much of the chamber is explained by government-vs-opposition alone.

    If this is most of it, then "which party would the fly join" is really "which side",
    and the party-level claim needs the caveat.
    """
    import datetime as _dt

    agree_gov, agree_opp, n = 0, 0, 0
    for j, v in enumerate(vm.votes):
        if not v.when:
            continue
        d = _dt.date.fromisoformat(v.when[:10])
        if era_at(d) is None:
            continue
        gov, opp = [], []
        for i, _mid in enumerate(vm.member_ids):
            f = vm.faction[i, j]
            st = vm.stance[i, j]
            if not f or np.isnan(st) or st == 0.0:
                continue
            side = alignment_at(f, d)
            if side == "government":
                gov.append(st)
            elif side == "opposition":
                opp.append(st)
        if len(gov) < 5 or len(opp) < 5:
            continue
        n += 1
        gov_line = SUPPORT if np.mean(gov) > 0 else OPPOSE
        opp_line = SUPPORT if np.mean(opp) > 0 else OPPOSE
        agree_gov += float(np.mean(np.array(gov) == gov_line))
        agree_opp += float(np.mean(np.array(opp) == opp_line))
        if gov_line != opp_line:
            pass
    opposed = 0
    for j, v in enumerate(vm.votes):
        if not v.when:
            continue
        d = _dt.date.fromisoformat(v.when[:10])
        if era_at(d) is None:
            continue
        gov, opp = [], []
        for i, _mid in enumerate(vm.member_ids):
            f = vm.faction[i, j]
            st = vm.stance[i, j]
            if not f or np.isnan(st) or st == 0.0:
                continue
            side = alignment_at(f, d)
            (gov if side == "government" else opp if side == "opposition" else []).append(st)
        if len(gov) < 5 or len(opp) < 5:
            continue
        if (np.mean(gov) > 0) != (np.mean(opp) > 0):
            opposed += 1
    return {
        "votes_scored": n,
        "government_cohesion": round(agree_gov / n, 3) if n else None,
        "opposition_cohesion": round(agree_opp / n, 3) if n else None,
        "sides_opposed_share": round(opposed / n, 3) if n else None,
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
    line — no LLM — ablated by feature set.

    The ablation is the point. `initiator` (government vs MP) is one bit that Kärbes never
    sees, and it is worth roughly 18 points on its own: the coalition backs government
    bills and kills opposition ones. That is procedural signalling, not content. So the
    fair benchmark for a content-reading fly is the `content` row, not `content+initiator`.

    It also constrains Stage 1: the rubric must be initiator-blind, or the topic scores
    launder this one bit and the fly's apparent performance is leakage.
    """
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def content(bill, vote):
        f = {f"desc={d}": 1.0 for d in bill.descriptors}
        f[f"committee={bill.committee}"] = 1.0
        f[f"type={bill.draft_type}"] = 1.0
        return f

    def procedural(bill, vote):
        return {f"kind={vote.kind}": 1.0}

    def initiator(bill, vote):
        return {"government": 1.0 if bill.government_bill else 0.0}

    feature_sets = {
        "content": [content],
        "procedural": [procedural],
        "content+initiator": [content, initiator],
        "all": [content, procedural, initiator],
    }

    out: dict = {"sets": {}, "fair_benchmark_for_fly": "content"}
    for label, parts in feature_sets.items():
        feats, keep = [], []
        for j, v in enumerate(vm.votes):
            bill = bills.get(v.draft_uuid)
            if bill is None:
                continue
            merged: dict = {}
            for fn in parts:
                merged.update(fn(bill, v))
            feats.append(merged)
            keep.append(j)
        if len(feats) < 30:
            return {"error": "too few bills with metadata", "n": len(feats)}

        x = DictVectorizer(sparse=False).fit_transform(feats)
        per_faction = {}
        for faction in vm.faction_names():
            line = vm.faction_line(faction)[keep]
            valid = ~np.isnan(line)
            y = (line[valid] == SUPPORT).astype(int)
            if valid.sum() < 30 or len(np.unique(y)) < 2:
                continue
            majority = float(max(y.mean(), 1 - y.mean()))
            model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
            acc = float(cross_val_score(model, x[valid], y, cv=5).mean())
            per_faction[faction] = {
                "n": int(valid.sum()),
                "majority_baseline": round(majority, 3),
                "accuracy": round(acc, 3),
                "gain": round(acc - majority, 3),
            }
        out["sets"][label] = per_faction
    return out


def t1b_blocs(t1: dict) -> dict:
    """Merge factions that are not distinguishable, and report what *is* answerable.

    T1 failing is not the end of the study — it says the unit of analysis is wrong.
    Single-link agglomeration over the discordance matrix collapses factions that vote
    together into blocs, and the blocs are the targets a fly could actually be matched to.
    """
    factions = t1["factions"]
    matrix = t1["matrix"]
    blocs = [[f] for f in factions]

    def between(a: list[str], b: list[str]) -> int:
        return min(matrix[x][y] for x in a for y in b)

    merged = True
    while merged and len(blocs) > 1:
        merged = False
        for i in range(len(blocs)):
            for j in range(i + 1, len(blocs)):
                if between(blocs[i], blocs[j]) < MIN_DISCORDANCE:
                    blocs[i] = blocs[i] + blocs.pop(j)
                    merged = True
                    break
            if merged:
                break

    separations = {}
    for i in range(len(blocs)):
        for j in range(i + 1, len(blocs)):
            key = f"{_short(blocs[i][0])}+ | {_short(blocs[j][0])}+"
            separations[key] = between(blocs[i], blocs[j])

    return {
        "blocs": blocs,
        "n_blocs": len(blocs),
        "min_separation": min(separations.values()) if separations else 0,
        # Merged groups are the honest unit of analysis when T1 fails.
        "collapsed": [b for b in blocs if len(b) > 1],
    }


def run_pretests(cache_root: Path, verbose: bool = True) -> int:
    votes = load_votes(cache_root)
    voterless = voterless_votings(cache_root)
    if not votes:
        raise SystemExit("no cached votes — run `karbes harvest` first")

    vm_all = build(votes)
    vm = vm_all.subset(discriminative_mask(votes))
    bills = load_bills(cache_root)

    t1 = t1_discordance(vm)
    t1b = t1b_blocs(t1)
    t1c = t1c_by_era(vm)
    t1d = t1d_government_axis(vm)
    t2 = t2_content_blind_sweep(vm)
    t3 = t3_dimensionality(vm)
    t4 = t4_scale(vm)
    t5 = t5_metadata_ceiling(vm, bills)

    # T1 failing means the unit of analysis is wrong, not that the study is dead — so
    # the gate asks whether *some* separable set of targets exists, at bloc level.
    resolvable = t1["passes"] or (t1b["n_blocs"] >= 2 and t1b["min_separation"] >= MIN_DISCORDANCE)
    passed = resolvable and t3["passes"]
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
                # SPEC.md's 568 came from aggregate fields, which exist even when the
                # per-member list does not. Usable N is net of these.
                "voterless_dropped": len(voterless),
            },
            "t1_discordance": t1,
            "t1b_blocs": t1b,
            "t1c_by_era": t1c,
            "t1d_government_axis": t1d,
            "t2_content_blind": t2,
            "t3_dimensionality": t3,
            "t4_scale": t4,
            "t5_metadata_ceiling": t5,
        },
    )

    if verbose:
        _report(votes, vm, bills, t1, t1b, t1c, t1d, t2, t3, t4, t5, passed, gate, voterless)
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


def _report(votes, vm, bills, t1, t1b, t1c, t1d, t2, t3, t4, t5, passed, gate, voterless) -> None:
    print("\n" + "=" * 72)
    print("STAGE 0 PRE-TESTS — is the question answerable?")
    print("=" * 72)
    print(
        f"\ncorpus: {len(votes)} substantive votes, {vm.shape[1]} discriminative, "
        f"{len({v.draft_uuid for v in votes})} bills ({len(bills)} cached)"
    )
    no_text = sum(1 for b in bills.values() if not b.has_text)
    print(f"        {no_text} bill(s) have no introduction text (cannot be scored)")
    if voterless:
        print(f"        {len(voterless)} votings dropped: tallies but no per-member list")

    print(f"\nT1  pairwise discordance   {'PASS' if t1['passes'] else 'FAIL'}")
    print(
        f"    weakest pair: {_short(t1['min_pair'].split(' | ')[0])} vs "
        f"{_short(t1['min_pair'].split(' | ')[1])} = {t1['min_discordance']} "
        f"(need >= {MIN_DISCORDANCE})"
    )
    for pair, d in sorted(t1["pairs"].items(), key=lambda kv: kv[1])[:5]:
        a, b = pair.split(" | ")
        print(f"      {_short(a):>8} vs {_short(b):<8} {d:>4}")

    print(f"\nT1b blocs after merging   {t1b['n_blocs']} separable targets")
    for b in t1b["blocs"]:
        tag = " + ".join(_short(x) for x in b)
        note = "  <- indistinguishable, merged" if len(b) > 1 else ""
        print(f"      {tag}{note}")
    print(f"    weakest separation between blocs: {t1b['min_separation']}")

    print("\nT1c discordance within coalition eras")
    for key in t1c["era_keys"]:
        e = t1c["eras"][key]
        gov = ", ".join(_short(p) for p in e["coalition"])
        print(f"    era {e['label']}  n={e['votes']}  government: {gov}")
        blocs = " | ".join(" + ".join(_short(x) for x in b) for b in e["blocs"]["blocs"])
        print(f"       blocs: {blocs}")
    for sw in t1c["switched_sides"]:
        sides = " -> ".join(f"{k}:{v}" for k, v in sw["sides"].items())
        print(f"    {_short(sw['faction'])} changed side mid-term ({sides})")

    print("\nT1d government-vs-opposition axis")
    print(
        f"    government bloc cohesion {t1d['government_cohesion']:.0%}, "
        f"opposition {t1d['opposition_cohesion']:.0%}"
    )
    print(
        f"    the two sides took opposite lines on "
        f"{t1d['sides_opposed_share']:.0%} of {t1d['votes_scored']} votes"
    )

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

    print("\nT5  metadata-only ceiling (no LLM), by feature set")
    if "error" in t5:
        print(f"    {t5['error']}")
    else:
        facs = sorted(t5["sets"]["all"], key=lambda f: -t5["sets"]["all"][f]["accuracy"])
        print(f"      {'feature set':<19}" + "".join(f"{_short(f):>8}" for f in facs))
        for label in ("procedural", "content", "content+initiator", "all"):
            row = t5["sets"].get(label, {})
            cells = "".join(
                f"{row[f]['accuracy']:>8.3f}" if f in row else f"{'--':>8}" for f in facs
            )
            print(f"      {label:<19}{cells}")
        majs = "".join(f"{t5['sets']['all'][f]['majority_baseline']:>8.3f}" for f in facs)
        print(f"      {'majority baseline':<19}{majs}")
        print()
        print("    'initiator' is one bit the fly never sees, and it is worth most of the")
        print("    gap. The fly's fair benchmark is the 'content' row.")

    print("\n" + "-" * 72)
    print(f"GATE stage0: {'PASS' if passed else 'FAIL'}   ->  {gate}")
    print("-" * 72 + "\n")
