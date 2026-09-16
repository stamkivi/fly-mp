"""Harvest the Riigikogu corpus into the cache, and rebuild it from cache alone."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from itertools import zip_longest
from pathlib import Path
from zoneinfo import ZoneInfo

from karbes.riigikogu.fetch import Cache, Client
from karbes.riigikogu.model import (
    SEATS,
    SUBSTANTIVE_KINDS,
    TERM_START,
    Bill,
    Vote,
)

log = logging.getLogger(__name__)

#: The chamber's own clock: sitting dates are Tallinn local dates.
TALLINN = ZoneInfo("Europe/Tallinn")


def today() -> date:
    return datetime.now(tz=TALLINN).date()


def _year_ranges(start: date, end: date) -> list[tuple[str, str]]:
    """Calendar-year chunks, so the cache is resumable and incremental sync is natural."""
    ranges = []
    cursor = start
    while cursor <= end:
        year_end = min(date(cursor.year, 12, 31), end)
        ranges.append((cursor.isoformat(), year_end.isoformat()))
        cursor = year_end + timedelta(days=1)
    return ranges


def _substantive_votings(sittings: list[dict]) -> list[dict]:
    """Votings that decide a bill: a related draft, real tallies, a substantive description."""
    out = []
    for sitting in sittings:
        for voting in sitting.get("votings", []):
            if voting.get("description") not in SUBSTANTIVE_KINDS:
                continue
            if not voting.get("relatedDraft") or "inFavor" not in voting:
                continue
            out.append(voting)
    return out


def harvest(
    cache_root: Path,
    start: date = TERM_START,
    end: date | None = None,
    refresh_last_range: bool = False,
) -> dict:
    """Populate the cache. Resumable: anything already cached costs no request."""
    end = end or today()
    ranges = _year_ranges(start, end)
    cache = Cache(cache_root)

    with Client(cache) as client:
        if refresh_last_range and ranges:
            # The current year is still accruing sittings; its cached range is stale.
            stale = cache_root / "votings_range" / f"{ranges[-1][0]}_{ranges[-1][1]}.json"
            stale.unlink(missing_ok=True)

        sittings: list[dict] = []
        for lo, hi in ranges:
            log.info("votings %s..%s", lo, hi)
            sittings.extend(client.votings_in_range(lo, hi))

        votings = _substantive_votings(sittings)
        draft_uuids = {v["relatedDraft"]["uuid"] for v in votings}
        log.info(
            "%d sittings -> %d substantive votings on %d bills",
            len(sittings),
            len(votings),
            len(draft_uuids),
        )

        client.hallplan()

        # Votings and drafts live on different endpoint paths, so they have independent
        # 12/min budgets. Alternating between them saturates both and halves wall-clock
        # (24 req/min instead of 12); the limiter blocks per-path, so no threads needed.
        todo_votings = [v["uuid"] for v in votings]
        todo_drafts = sorted(draft_uuids)
        done_v = done_d = 0
        for v_uuid, d_uuid in zip_longest(todo_votings, todo_drafts):
            if v_uuid is not None:
                client.voting(v_uuid)
                done_v += 1
            if d_uuid is not None:
                client.draft(d_uuid)
                done_d += 1
            if (done_v + done_d) % 50 == 0:
                log.info(
                    "  votings %d/%d | drafts %d/%d | %d requests, %d cached",
                    done_v,
                    len(todo_votings),
                    done_d,
                    len(todo_drafts),
                    client.requests_made,
                    cache.hits,
                )

        stats = {
            "sittings": len(sittings),
            "substantive_votings": len(votings),
            "unique_bills": len(draft_uuids),
            "requests_made": client.requests_made,
            "cache_hits": cache.hits,
            "cache_misses": cache.misses,
            "gaps": client.gaps,
            "range": [start.isoformat(), end.isoformat()],
        }

    if client.gaps:
        (cache_root / "gaps.json").write_text(json.dumps(client.gaps, indent=2), encoding="utf-8")
    return stats


def load_votes(cache_root: Path) -> list[Vote]:
    """Rebuild the vote corpus from cache alone. Makes no network calls."""
    cache = Cache(cache_root)
    sittings: list[dict] = []
    for path in sorted((cache_root / "votings_range").glob("*.json")):
        sittings.extend(json.loads(path.read_text(encoding="utf-8")))

    votes: list[Vote] = []
    for voting in _substantive_votings(sittings):
        detail = cache.get("voting", voting["uuid"])
        if detail is None:
            continue  # a recorded gap; counts are re-derived without it
        voters = detail.get("voters") or []
        if len(voters) != SEATS:
            log.warning("voting %s has %d voters, expected %d", voting["uuid"], len(voters), SEATS)
        decisions, factions, names = {}, {}, {}
        for voter in voters:
            uid = voter["uuid"]
            decisions[uid] = (voter.get("decision") or {}).get("code", "")
            factions[uid] = (voter.get("faction") or {}).get("name", "")
            names[uid] = voter.get("fullName", "")
        draft = voting["relatedDraft"]
        votes.append(
            Vote(
                uuid=voting["uuid"],
                kind=voting["description"],
                when=voting.get("startDateTime", ""),
                draft_uuid=draft["uuid"],
                draft_title=draft.get("title", ""),
                in_favor=voting["inFavor"],
                against=voting["against"],
                neutral=voting.get("neutral", 0),
                abstained=voting.get("abstained", 0),
                decisions=decisions,
                factions=factions,
                names=names,
            )
        )
    votes.sort(key=lambda v: v.when)
    return votes


def load_bills(cache_root: Path, uuids: set[str] | None = None) -> dict[str, Bill]:
    """Rebuild bills from cache alone. Bills with no introduction are kept but flagged."""
    cache = Cache(cache_root)
    draft_dir = cache_root / "draft"
    keys = uuids if uuids is not None else {p.stem for p in draft_dir.glob("*.json")}

    bills: dict[str, Bill] = {}
    for key in keys:
        raw = cache.get("draft", key)
        if raw is None:
            continue
        committee = (raw.get("leadingCommittee") or {}).get("name")
        bills[key] = Bill(
            uuid=key,
            title=raw.get("title", ""),
            mark=raw.get("mark"),
            introduction=raw.get("introduction") or "",
            descriptors=tuple(d["text"] for d in raw.get("descriptors", []) if "text" in d),
            initiators=tuple(i.get("name", "") for i in raw.get("initiators", [])),
            committee=committee,
            draft_type=raw.get("draftTypeCode"),
            initiated=raw.get("initiated"),
        )
    return bills
