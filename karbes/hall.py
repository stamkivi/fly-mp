"""The plenary hall, as far as it can be reconstructed, and which side each member is on.

`/api/hallplan` gives every member a seat *number* and a faction, and the photograph from
the Speaker's desk shows two blocks of desks either side of a centre aisle, about six rows
deep. The numbered plan itself is not published anywhere I could find, so the positions
below are a **reconstruction** and the page says so.

Laterality for the fly is *political*, not photographic: the coalition is seated to the
Speaker's right and the opposition to the left, as in most parliaments; the Government's
box is on the Speaker's right too. The Riigikogu does seat by faction, so the blocs are
real; which physical side they occupy is the one assumption. It is harmless to the
physics — the escape reflex is mirror-symmetric — and it only decides which way the
drawing faces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

COALITION = {"REF", "E200", "SDE"}
OPPOSITION = {"EKRE", "I", "KESK"}
ROWS = 6


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


def _side(faction: str, place: int, blocs: list[tuple[int, str]]) -> str:
    if faction in COALITION:
        return "R"
    if faction in OPPOSITION:
        return "L"
    # Non-affiliated members sit where they sit; the nearest faction bloc by seat number
    # is the best available guess at which block that is.
    nearest = min(blocs, key=lambda b: abs(b[0] - place))[1]
    return "R" if nearest in COALITION else "L"


def load(path: Path = Path("data/raw/meta/hallplan.json")) -> list[Seat]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    blocs = [
        (int(s["place"]), (s.get("faction") or {}).get("shortName") or "")
        for s in raw
        if (s.get("faction") or {}).get("shortName")
    ]
    seats = []
    for s in raw:
        f = s.get("faction") or {}
        short = f.get("shortName") or ""
        seats.append(
            (
                int(s["place"]),
                s["user"]["uuid"],
                s["user"]["fullName"],
                s["user"]["lastName"],
                short,
                "#" + (f.get("colorHex") or "A9A49B"),
                _side(short, int(s["place"]), blocs),
            )
        )
    # Lay each side out front-to-back in seat-number order: a rectangle of ROWS rows.
    out = []
    for side in ("L", "R"):
        mine = sorted(s for s in seats if s[6] == side)
        per_row = -(-len(mine) // ROWS)
        for i, s in enumerate(mine):
            out.append(Seat(*s, row=i // per_row, col=i % per_row))
    return sorted(out, key=lambda s: s.place)


def by_last_name(seats: list[Seat]) -> dict[str, Seat]:
    return {s.last: s for s in seats}
