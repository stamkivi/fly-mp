"""The plenary hall, from the Riigikogu's own seating plan, and which side each member is on.

`/api/hallplan` gives every member a seat *number* and a faction. The numbering is the geometry:
the published plan (riigikogu.ee, "Seating plan") shows six pairs of columns, ten rows deep,
the Board of the Riigikogu at the top, and the numbers run down the columns — seats 1–10 are
the left column of the first pair from front to back, 11–20 its right column, 21–40 the second
pair, and so on to 118. Every name in the plan lands on its number under that rule.

The plan is drawn with the Board at the top, so plan-left is the Speaker's right. From the
Speaker's chair: pairs 1–3 (EKRE, Isamaa, most of Reform) are to the right of the aisle,
pairs 4–6 (the rest of Reform, Eesti 200, Centre, SDE, the non-affiliated) to the left. That
is the side a member's voice reaches the fly from; it is physical, not political.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

COALITION = {"REF", "E200", "SDE"}
OPPOSITION = {"EKRE", "I", "KESK"}


@dataclass(frozen=True)
class Seat:
    place: int
    uuid: str
    name: str
    last: str
    faction: str  # short name, or "" for non-affiliated
    colour: str  # official hex from the API
    side: str  # "L" (opposition) or "R" (coalition), from the Speaker's chair
    row: int  # 0 = front
    col: int  # 0 = nearest the aisle, within the side's block


PAIRS, ROWS_DEEP, PER_PAIR = 6, 10, 20


def geometry(place: int) -> tuple[str, int, int]:
    """(side from the Speaker's chair, row with 0 nearest the Speaker, column with 0 nearest
    the aisle) for a seat number."""
    n = place - 1
    pair, col_in_pair, row = n // PER_PAIR, (n % PER_PAIR) // ROWS_DEEP, n % ROWS_DEEP
    k = pair * 2 + col_in_pair  # 0 = plan-left = Speaker's far right, 11 = Speaker's far left
    if k < 6:
        return "R", row, 5 - k
    return "L", row, k - 6


def load(path: Path = Path("data/raw/meta/hallplan.json")) -> list[Seat]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for x in raw:
        f = x.get("faction") or {}
        side, row, col = geometry(int(x["place"]))
        out.append(
            Seat(
                place=int(x["place"]),
                uuid=x["user"]["uuid"],
                name=x["user"]["fullName"],
                last=x["user"]["lastName"],
                faction=f.get("shortName") or "",
                colour="#" + (f.get("colorHex") or "A9A49B"),
                side=side,
                row=row,
                col=col,
            )
        )
    return sorted(out, key=lambda s: s.place)


def by_last_name(seats: list[Seat]) -> dict[str, Seat]:
    return {s.last: s for s in seats}
