"""Who was in government, when.

Coalition membership is the dominant structural variable in Riigikogu voting, and it is
*time-varying*. Analysing the XV term as one block averages over two different political
worlds: the Social Democrats voted with Reform on all but 4 of 358 contested votes while
in coalition, and on all but 68 of 205 after being expelled. Any faction-level target
built across that boundary is a blend of two incompatible behaviours.

The Riigikogu open data API does not expose government composition — it describes the
parliament, not the cabinet — so this table is encoded by hand from the sources below and
cross-checked against the voting record (see `detect_change_points`).

Sources:
  Kaja Kallas's third cabinet — https://en.wikipedia.org/wiki/Kaja_Kallas%27s_third_cabinet
  Kristen Michal's cabinet    — https://en.wikipedia.org/wiki/Kristen_Michal%27s_cabinet
  Coalition agreement 2023-27 — https://valitsus.ee/en/coalition-agreement-2023-2027
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Faction names exactly as the API spells them, so joins need no normalisation.
REF = "Eesti Reformierakonna fraktsioon"
E200 = "Eesti 200 fraktsioon"
SDE = "Sotsiaaldemokraatliku Erakonna fraktsioon"
EKRE = "Eesti Konservatiivse Rahvaerakonna fraktsioon"
ISAMAA = "Isamaa fraktsioon"
KESK = "Eesti Keskerakonna fraktsioon"
CROSSBENCH = "Fraktsiooni mittekuuluvad Riigikogu liikmed"

ALL_FACTIONS = (REF, E200, SDE, EKRE, ISAMAA, KESK)


@dataclass(frozen=True)
class Era:
    """A span over which the coalition's party composition did not change."""

    key: str
    start: date
    end: date | None  # None = still current
    parties: frozenset[str]
    cabinet: str
    note: str = ""

    def contains(self, d: date) -> bool:
        return d >= self.start and (self.end is None or d <= self.end)

    @property
    def label(self) -> str:
        end = self.end.isoformat() if self.end else "present"
        span = f"{self.start.isoformat()}..{end}"
        return f"{self.key} {span}"


#: Cabinets changed three times but *composition* changed once, so there are two eras.
#: Kallas III and Michal I had identical coalition parties; a new PM is not a new bloc.
ERAS: tuple[Era, ...] = (
    Era(
        key="A",
        start=date(2023, 4, 17),
        end=date(2025, 3, 10),
        parties=frozenset({REF, E200, SDE}),
        cabinet="Kallas III, then Michal I from 2024-07-23",
        note="majority coalition",
    ),
    Era(
        key="B",
        start=date(2025, 3, 11),
        end=None,
        parties=frozenset({REF, E200}),
        cabinet="Michal I",
        note=(
            "SDE expelled 2025-03-11; minority in practice, and the government lost its "
            "formal majority in August 2026 after MP defections"
        ),
    ),
)


def era_at(d: date) -> Era | None:
    """The coalition era containing `d`, or None for votes before the term began."""
    for era in ERAS:
        if era.contains(d):
            return era
    return None


def coalition_at(d: date) -> frozenset[str]:
    """Factions in government on `d`. Empty before the term begins."""
    era = era_at(d)
    return era.parties if era else frozenset()


def alignment_at(faction: str, d: date) -> str:
    """`government`, `opposition`, or `crossbench` for a faction on a given date.

    This is the axis the chamber actually votes on — far more of the variance than any
    left-right reading — and it is the reason a faction is not a stable analysis target.
    """
    if faction == CROSSBENCH:
        return "crossbench"
    return "government" if faction in coalition_at(d) else "opposition"


def detect_change_points(dates: list[str], discordance: list[int], window: int = 40) -> list[str]:
    """Largest jumps in a rolling discordance series, for cross-checking the table above.

    The encoded dates are external claims; this finds where the *voting record* says the
    relationship changed, so the two can be compared rather than assumed consistent.
    """
    if len(dates) < 2 * window:
        return []
    jumps = []
    for i in range(window, len(dates) - window):
        before = sum(discordance[i - window : i]) / window
        after = sum(discordance[i : i + window]) / window
        jumps.append((abs(after - before), dates[i]))
    jumps.sort(reverse=True)
    return [d for _, d in jumps[:3]]
