"""One sitting of the Riigikogu as the fly in the Speaker's chair receives it.

The verbatim record gives every utterance a speaker, a text and a timestamp to the second,
and marks disturbances, votes and the bell inline. This turns that into a list of events
the brain can be driven with, and — separately — a list of what the *real* chair did, so
the fly can be compared to it afterwards.

**What is a stimulus and what is not.** Members and ministers are stimuli: a speech is a
shape that appears on the speaker's side of the hall, and how fast it comes at the chair
is the speech's hostility (see `tone.py`). Disturbances are stimuli: a heckle lunges. Votes
are stimuli: the whole hall lights. The chair's own words are *not* stimuli — the fly is
the chair — and are kept only as ground truth: when the real chair called for order, rang
the bell, or called time.

**Time.** The brain's memory is 20 ms, so a 300-word answer and a 30-word question are,
to it, the same thing: an onset, a plateau, an offset. Every event is therefore played to
the brain for a compressed duration that grows only with the log of its length, followed
by 150 ms of silence in which the brain goes dark. A twelve-hour sitting becomes a few
minutes of biological time, and the page plays that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from karbes import hall, tone

CHAIR_PREFIX = ("Esimees", "Aseesimees")
ORDER_RE = re.compile(
    r"palun (saalis )?vaikust|liiga suur lärm|kutsu[nb] .{0,20}korrale|palun mitte segada|mitte vahele",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"\bTeie aeg\b|\bAeg!|aeg on (läbi|täis)", re.IGNORECASE)
BELL_RE = re.compile(r"\((Juhataja )?[Hh]elistab (uuesti )?kella\.?\)")
DISTURB_RE = re.compile(r"\(([^()]*?(?:kohalt|saalist|protestib|Naer|vahele)[^()]*)\)")
SILENCE = 0.15  # seconds of dark between events, in biological time


@dataclass
class Event:
    t: float  # real seconds from the start of the sitting
    kind: str  # speech | heckle | vote | presence
    speaker: str
    role: str  # member | gov | chair | floor
    faction: str
    side: str  # L | R | "" (both / none)
    seat: int | None
    words: int
    text: str  # a short excerpt for the ticker
    key: str  # tone cache key, for speeches
    item: str  # agenda item title
    hostility: float = 0.0  # filled from the tone cache
    real_chair: str = ""  # order | time | bell, on chair utterances only
    bio: float = 0.0  # seconds of biological time this event is played for


@dataclass
class Sitting:
    date: str
    title: str
    events: list[Event] = field(default_factory=list)

    @property
    def stimuli(self) -> list[Event]:
        return [e for e in self.events if e.role != "chair"]


def _role(speaker: str) -> str:
    if speaker.startswith(CHAIR_PREFIX):
        return "chair"
    if "minister" in speaker.lower():
        return "gov"
    return "member"


def bio_duration(kind: str, words: int) -> float:
    import math

    if kind == "speech":
        return min(0.8, 0.15 + 0.25 * math.log10(1 + words))
    return {"heckle": 0.3, "vote": 0.5, "presence": 0.4}[kind]


def load(path: Path, seats: list[hall.Seat] | None = None) -> Sitting:
    seats = seats or hall.load()
    by_last = hall.by_last_name(seats)
    raw = json.loads(path.read_text(encoding="utf-8"))
    events: list[Event] = []
    t0 = None
    for sit in raw:
        for ai in sit.get("agendaItems", []):
            item = re.sub(r"<[^>]+>", "", ai.get("title") or "")[:90]
            for e in ai.get("events", []):
                when = datetime.fromisoformat(e["date"])
                t0 = t0 or when
                t = (when - t0).total_seconds()
                kind = e.get("type")
                if kind in ("VOTING_EVENT", "PRESENCE_CHECK"):
                    k = "vote" if kind == "VOTING_EVENT" else "presence"
                    events.append(Event(t, k, "", "floor", "", "", None, 0, "", "", item, bio=bio_duration(k, 0)))
                    continue
                if kind != "SPEECH" or not e.get("text"):
                    continue
                sp, text = e["speaker"], e["text"]
                role = _role(sp)
                seat = by_last.get(sp.split()[-1]) if role == "member" else None
                faction = seat.faction if seat else ("" if role != "gov" else "GOV")
                side = seat.side if seat else ("R" if role == "gov" else "")
                words = len(text.split())
                ev = Event(
                    t, "speech", sp, role, faction, side, seat.place if seat else None, words,
                    text[:140].replace("\n", " "), tone.key(text), item,
                    bio=0.0 if role == "chair" else bio_duration("speech", words),
                )
                if role == "chair":
                    if ORDER_RE.search(text):
                        ev.real_chair = "order"
                    elif BELL_RE.search(text):
                        ev.real_chair = "bell"
                    elif TIME_RE.search(text):
                        ev.real_chair = "time"
                events.append(ev)
                # Disturbances recorded inside this utterance become their own events, a
                # little after it starts. A named heckler who has a seat lunges from it.
                for m in DISTURB_RE.finditer(text):
                    note = m.group(1)
                    who = re.match(r"([A-ZÕÄÖÜ][a-zõäöü\-]+(?: [A-ZÕÄÖÜ][a-zõäöü\-]+)+)", note)
                    hs = by_last.get(who.group(1).split()[-1]) if who else None
                    frac = m.start() / max(len(text), 1)
                    events.append(Event(
                        t + frac * words / 2.0, "heckle", who.group(1) if who else "the floor", "floor",
                        hs.faction if hs else "", hs.side if hs else "", hs.place if hs else None, 0,
                        note[:140], "", item, bio=bio_duration("heckle", 0),
                    ))
                if role != "chair" and BELL_RE.search(text):
                    # The bell rang while a member was speaking. Measured across 75 days,
                    # these ring at the 92nd percentile of the speech: they are the clock,
                    # not a reaction to conduct, and are classified as such.
                    events.append(Event(t + words / 4.0, "speech", "the chair", "chair", "", "", None, 0,
                                        "(rings the bell — time)", "", item, real_chair="time"))
    events.sort(key=lambda x: x.t)
    date = t0.astimezone().strftime("%-d %B %Y") if t0 else path.stem[-10:]
    return Sitting(date=date, title=raw[0].get("title", "") if raw else "", events=events)


def attach_tone(s: Sitting, root: Path = Path("data/raw")) -> int:
    """Fill hostility from the cache. Unscored speeches stay at 0 and are counted."""
    tc = tone.ToneCache(root)
    missing = 0
    for e in s.events:
        if e.kind == "speech" and e.role != "chair":
            rec = tc.dir / f"{e.key}.json"
            if rec.exists():
                d = json.loads(rec.read_text(encoding="utf-8"))
                e.hostility = tone.hostility(d["score"], d["confidence"])
            elif e.words >= tone.MIN_WORDS:
                missing += 1
    return missing
