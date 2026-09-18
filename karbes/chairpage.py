"""Bundle a recorded sitting for the page, and fill the template.

Members appear by faction and role, never by name: the record is public, but the subject
is the fly, and a page that names who heckled whom is a different page.
"""

from __future__ import annotations

import base64
import html
import json
import logging
from pathlib import Path

import numpy as np

from karbes import hall
from karbes.atlas import Atlas
from karbes.chair import BELL_GF, FPS, ONSET_BINS, Recording
from karbes.sitting import Sitting

log = logging.getLogger(__name__)

TEMPLATE = Path("page/chair.html")
BRAIN = Path("page/assets/brain.jpg")
BRAIN_FRAME = Path("page/assets/brain.json")
FLY = Path("page/assets/fly.png")
HALL_PHOTO = Path("page/assets/hall.jpg")

ROLE_LABEL = {"member": "a member", "gov": "a minister", "floor": "the floor", "chair": "the chair"}


def _who(e) -> str:
    if e.role == "gov":
        return "the Prime Minister" if e.speaker.startswith("Peaminister") else "a minister"
    if e.role == "member":
        return f"{e.faction} member" if e.faction else "a non-affiliated member"
    if e.kind == "heckle":
        return f"{e.faction} member, from the floor" if e.faction else "a voice from the floor"
    return ROLE_LABEL.get(e.role, e.role)


def bundle(s: Sitting, rec: Recording, atlas: Atlas, start_iso: str) -> dict:
    seats = hall.load()
    frame = json.loads(BRAIN_FRAME.read_text(encoding="utf-8"))
    # atlas coordinates -> voxels -> the plate's frame, in units of the plate's width.
    # plate.render uses ONE isotropic scale, set by the x-span: px = (vx-minX)*k + m*w and
    # py = (vz-minZ)*k + m*w with k = w*(1-2m)/span_x. So both axes divide by span_x.
    vox = atlas.origin[None, :] + atlas.xyz.astype(np.float64) * atlas.scale
    m = frame["margin"]
    span_x = frame["maxX"] - frame["minX"]
    sx = (vox[:, 0] - frame["minX"]) / span_x * (1 - 2 * m) + m
    sy = (vox[:, 2] - frame["minZ"]) / span_x * (1 - 2 * m) + m
    aspect = frame["height"] / frame["width"]
    inside = (sx >= 0) & (sx <= 1) & (sy >= 0) & (sy <= aspect)
    atlas_xy = np.stack([sx, sy], axis=1).astype(np.float32)
    log.info("atlas: %d of %d cells fall on the plate", int(inside.sum()), len(inside))

    reactions = {r.index: r for r in rec.reactions}
    events = []
    for i, e in enumerate(s.events):
        r = reactions.get(i)
        events.append(
            {
                "t": round(e.t, 1),
                "kind": e.kind,
                "role": e.role,
                "who": _who(e),
                "faction": e.faction,
                "side": e.side,
                "seat": e.seat,
                "words": e.words,
                "text": e.text,
                "hostility": round(e.hostility, 3),
                "real_chair": e.real_chair,
                "bio": round(e.bio, 3),
                "item": e.item,
                "gf": r.gf if r else None,
                "turn": r.turn if r else None,
                "dna_l": r.dna_l if r else None,
                "dna_r": r.dna_r if r else None,
                "spikes": r.spikes if r else None,
                "active": r.active if r else None,
            }
        )
    fly_bells = [i for i, r in reactions.items() if r.gf >= BELL_GF]
    chair_marks = [i for i, e in enumerate(s.events) if e.real_chair]
    # Conduct only: a time call is a clock, not a reaction to anyone's behaviour. A fly bell
    # "coincides" with a chair mark if the chair acted within the same or the next two
    # events — the chair reacts after the offence, not during it.
    conduct = [i for i in chair_marks if s.events[i].real_chair != "time"]
    coincide = sum(1 for i in fly_bells if any(0 <= j - i <= 2 for j in conduct))
    summary = {
        "events": len(s.events),
        "stimuli": len(rec.reactions),
        "fly_bells": len(fly_bells),
        "chair_order": sum(1 for i in chair_marks if s.events[i].real_chair == "order"),
        "chair_bell": sum(1 for i in chair_marks if s.events[i].real_chair == "bell"),
        "chair_time": sum(1 for i in chair_marks if s.events[i].real_chair == "time"),
        "coincide": coincide,
        "heckles": sum(1 for e in s.events if e.kind == "heckle"),
        "hostile": sum(1 for e in s.stimuli if e.hostility > 0.3),
        "ritual": sum(
            1
            for e in s.stimuli
            if e.kind == "speech" and e.text.startswith(("Aitäh", "Suur tänu", "Tänan"))
        ),
        "bio_seconds": round(len(rec.raster) / FPS, 1),
        "by_kind": _by_kind(s, rec),
    }

    # The page draws at most this many cells per frame; a 27-hour sitting would otherwise ship
    # 8 MB. Trimmed here, at build time, with a fixed seed, so no recording is redone.
    RASTER_CAP, ONSET_CAP = 150, 110
    rng = np.random.default_rng(0)

    def trim(frames: list[list[int]], cap: int) -> list[list[int]]:
        return [sorted(rng.choice(fr, cap, replace=False).tolist()) if len(fr) > cap else fr for fr in frames]

    def pack(frames: list[list[int]]) -> tuple[str, list[int]]:
        off = [0]
        for fr in frames:
            off.append(off[-1] + len(fr))
        flat = np.fromiter((x for fr in frames for x in fr), dtype="<u2", count=off[-1])
        return base64.b64encode(flat.tobytes()).decode(), off

    raster_b64, raster_off = pack(trim(rec.raster, RASTER_CAP))
    onset_b64, onset_off = pack(trim(rec.onset, ONSET_CAP))
    return {
        "schema": "karbes-chair/2",
        "date": s.date,
        "title": s.title,
        "start": start_iso,
        "fps": FPS,
        "bell_gf": BELL_GF,
        "seats": [
            {
                "place": x.place,
                "faction": x.faction,
                "colour": x.colour,
                "side": x.side,
                "row": x.row,
                "col": x.col,
            }
            for x in seats
        ],
        "events": events,
        "group_hz": rec.group_hz,
        "frame_event": rec.frame_event,
        "raster_b64": raster_b64,
        "raster_off": raster_off,
        "onset_b64": onset_b64,
        "onset_off": onset_off,
        "onset_bins": ONSET_BINS,
        "onset_event": [r.index for r in rec.reactions],
        "atlas": {
            "k": atlas.k,
            "xy_b64": base64.b64encode(atlas_xy.tobytes()).decode(),
            "group_b64": base64.b64encode(atlas.group.astype(np.uint8).tobytes()).decode(),
            "inside_b64": base64.b64encode(np.packbits(inside).tobytes()).decode(),
            "groups": list(atlas.group_names()),
        },
        "brain": frame,
        "summary": summary,
    }


def _by_kind(s: Sitting, rec: Recording) -> dict:
    """Mean reaction per kind of event — the thing the brain cannot keep and the page can."""
    R = {r.index: r for r in rec.reactions}
    rows: dict[str, list] = {}
    for i, r in R.items():
        e = s.events[i]
        kind = (
            e.kind
            if e.kind != "speech"
            else ("hostile speech" if e.hostility >= 0.5 else "civil speech")
        )
        rows.setdefault(kind, []).append(r)
    return {
        k: {
            "n": len(v),
            "gf": round(float(np.mean([r.gf for r in v])), 1),
            "turn": round(float(np.mean([abs(r.turn) for r in v])), 3),
            "active": int(np.mean([r.active for r in v])),
            "spikes": int(np.mean([r.spikes for r in v])),
            "bells": sum(1 for r in v if r.gf >= BELL_GF),
        }
        for k, v in rows.items()
    }


def build(b: dict, others: dict[str, dict] | None = None) -> str:
    """`others` maps a sitting's date label to {"url": ..., "summary": ...}: the top-bar
    links, and the one-line comparison the end card makes with the other sitting."""
    t = TEMPLATE.read_text(encoding="utf-8")
    others = others or {}
    links = "".join(f'<a href="{o["url"]}">{html.escape(d)}</a>' for d, o in others.items())
    compare = [
        {"date": d, "url": o["url"], "stimuli": o["summary"]["stimuli"], "fly_bells": o["summary"]["fly_bells"],
         "chair_order": o["summary"]["chair_order"] + o["summary"]["chair_bell"], "heckles": o["summary"]["heckles"],
         "hostile": o["summary"]["hostile"], "coincide": o["summary"]["coincide"]}
        for d, o in others.items() if o.get("summary")
    ]
    b = dict(b, others=compare)
    tokens = {
        "__DATE__": html.escape(b["date"]),
        "__OTHERS__": ("other sitting:" + links) if links else "",
        "__BUNDLE_JSON__": json.dumps(b, ensure_ascii=False).replace("</", "<\\/"),
        "__BRAIN_B64__": base64.b64encode(BRAIN.read_bytes()).decode(),
        "__FLY_B64__": base64.b64encode(FLY.read_bytes()).decode(),
        "__HALL_B64__": base64.b64encode(HALL_PHOTO.read_bytes()).decode()
        if HALL_PHOTO.exists()
        else "",
    }
    for k, v in tokens.items():
        if k not in t:
            raise ValueError(f"chair template has no {k}")
        t = t.replace(k, v)
    return t
