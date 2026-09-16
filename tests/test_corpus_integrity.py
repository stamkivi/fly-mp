"""Integrity checks against whatever is actually cached.

These are in SPEC.md's test plan: they guard against silent corpus corruption, which is
the failure mode that would invalidate every downstream number without any visible error.
Skipped when the cache is empty so the suite still runs on a fresh clone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from karbes.riigikogu.fetch import Cache
from karbes.riigikogu.model import SEATS

CACHE = Path("data/raw")
VOTING_DIR = CACHE / "voting"


def cached_votings(limit: int | None = None) -> list[dict]:
    if not VOTING_DIR.exists():
        return []
    cache = Cache(CACHE)
    keys = sorted(p.stem for p in VOTING_DIR.glob("*.json"))
    if limit:
        keys = keys[:limit]
    return [d for d in (cache.get("voting", k) for k in keys) if d]


@pytest.fixture(scope="module")
def votings() -> list[dict]:
    data = cached_votings()
    if not data:
        pytest.skip("no cached votings — run `karbes harvest` first")
    return data


def test_votings_without_voter_lists_are_a_bounded_minority(votings):
    """If this is a large share of the corpus, the usable N is materially below the 568
    figure in SPEC.md, which was derived from aggregate fields."""
    empty = [v for v in votings if not v.get("voters")]
    assert len(empty) / len(votings) < 0.25, (
        f"{len(empty)}/{len(votings)} votings have no per-member data"
    )


def test_tallies_sum_to_the_chamber(votings):
    """inFavor + against + neutral + abstained == 101 on every voting."""
    for v in votings:
        total = v["inFavor"] + v["against"] + v.get("neutral", 0) + v.get("abstained", 0)
        assert total == SEATS, f"voting {v['uuid']} tallies to {total}, not {SEATS}"


def test_voter_lists_are_either_whole_or_absent(votings):
    """Some early-term votings carry tallies but no per-member list at all. That is a
    known API gap and they are dropped. A *partial* list would be far worse — it would
    look usable while silently missing members."""
    for v in votings:
        n = len(v.get("voters", []))
        assert n in (0, SEATS), f"voting {v['uuid']} has a partial voter list of {n}"


def test_every_voter_has_a_decision_and_faction(votings):
    for v in votings:
        for voter in v.get("voters", []):
            assert (voter.get("decision") or {}).get("code"), (
                f"voter {voter.get('fullName')} has no decision in {v['uuid']}"
            )
            assert voter.get("faction"), (
                f"voter {voter.get('fullName')} has no faction in {v['uuid']}"
            )


def test_decision_codes_are_known(votings):
    from karbes.riigikogu.model import (
        EI_HAALETANUD,
        ERAPOOLETU,
        POOLT,
        PUUDUB,
        VASTU,
    )

    known = {POOLT, VASTU, ERAPOOLETU, EI_HAALETANUD, PUUDUB}
    seen = {vo["decision"]["code"] for v in votings for vo in v.get("voters", [])}
    assert seen <= known, f"unknown decision codes: {seen - known}"


def test_aggregate_counts_match_the_per_voter_records(votings):
    """The aggregate fields and the voter list must tell the same story, or one of them
    is being misread."""
    from karbes.riigikogu.model import POOLT, VASTU

    for v in votings:
        if not v.get("voters"):
            continue  # tallies only; dropped from the corpus
        codes = [vo["decision"]["code"] for vo in v["voters"]]
        assert codes.count(POOLT) == v["inFavor"], f"inFavor mismatch in {v['uuid']}"
        assert codes.count(VASTU) == v["against"], f"against mismatch in {v['uuid']}"
