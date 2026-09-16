"""Vocabulary of the Riigikogu corpus.

Estonian field values are kept verbatim — they are the source language and the API's
actual codes. English glosses live in comments, not in the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# XV Riigikogu convened 2023-04-10.
TERM_START = date(2023, 4, 10)

# Per-member decision codes, from `voters[].decision.code`.
POOLT = "POOLT"  # for
VASTU = "VASTU"  # against
ERAPOOLETU = "ERAPOOLETU"  # abstain — functionally dead, 0.1% of slots
EI_HAALETANUD = "EI_HAALETANUD"  # present, declined to press
PUUDUB = "PUUDUB"  # absent

#: States Kärbes can emit. Not ERAPOOLETU: real MPs essentially never use it.
FLY_STATES = (POOLT, VASTU, EI_HAALETANUD)

#: A member took a position (as opposed to declining or being absent).
POSITIONS = (POOLT, VASTU, ERAPOOLETU)

# Voting `description` values that decide the substance of a bill.
LOPPHAALETUS = "Lõpphääletus"  # final vote
TAGASI_LUKKAMINE = "Tagasi lükkamine"  # motion to reject the bill
UUESTI_VASTUVOTMINE = "Muutmata kujul uuesti vastuvõtmine"  # re-adoption unamended

SUBSTANTIVE_KINDS = (LOPPHAALETUS, TAGASI_LUKKAMINE, UUESTI_VASTUVOTMINE)

#: Kinds where POOLT means "kill the bill" — supporting the bill inverts to VASTU.
INVERTED_KINDS = frozenset({TAGASI_LUKKAMINE})

#: A vote only discriminates between factions if both sides drew real support.
DISCRIMINATIVE_MIN = 5

SEATS = 101


@dataclass(frozen=True)
class Vote:
    """One substantive voting, with every member's decision and faction at that moment."""

    uuid: str
    kind: str  # one of SUBSTANTIVE_KINDS
    when: str  # ISO datetime the voting opened
    draft_uuid: str
    draft_title: str
    in_favor: int
    against: int
    neutral: int
    abstained: int  # conflates present-but-silent with absent; use `decisions`
    decisions: dict[str, str]  # member uuid -> decision code
    factions: dict[str, str]  # member uuid -> faction name at this vote
    names: dict[str, str]  # member uuid -> full name

    @property
    def discriminative(self) -> bool:
        """Did the chamber actually split? 39% of final votes are unanimous."""
        return min(self.in_favor, self.against) >= DISCRIMINATIVE_MIN

    @property
    def inverted(self) -> bool:
        """True when POOLT means rejecting the bill."""
        return self.kind in INVERTED_KINDS

    def supports_bill(self, member_uuid: str) -> bool | None:
        """Normalise a member's decision to a stance on the *bill*, not on the motion.

        Returns None when the member took no position.
        """
        decision = self.decisions.get(member_uuid)
        if decision == POOLT:
            return not self.inverted
        if decision == VASTU:
            return self.inverted
        return None


@dataclass(frozen=True)
class Bill:
    """A draft, reduced to what the rubric and the metadata-only control need."""

    uuid: str
    title: str
    mark: int | None
    introduction: str
    descriptors: tuple[str, ...]
    initiators: tuple[str, ...]
    committee: str | None
    draft_type: str | None
    initiated: str | None

    @property
    def government_bill(self) -> bool:
        return any("Vabariigi Valitsus" in i for i in self.initiators)

    @property
    def has_text(self) -> bool:
        """Bills with no introduction cannot be scored and must not default to zeros."""
        return bool(self.introduction.strip())
