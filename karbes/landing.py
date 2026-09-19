"""The landing page: one card per recorded sitting, the comparison table, the credits.

Bilingual the same way the viewer is: every visible string is written into the markup in both
languages (`data-en` / `data-et`) and a few lines of script pick one.
"""

import base64
import html
import json
from pathlib import Path

from karbes.chairpage import FLY, HALL_PHOTO

TEMPLATE = Path(__file__).resolve().parent.parent / "page" / "index.html"

ROWS = [
    ("stimuli", "things happened in the hall", "sündmust saalis"),
    ("hostile", "speeches read as hostile", "vaenulikuks loetud kõnet"),
    ("heckles", "recorded heckles", "protokollitud vahelehüüet"),
    ("fly_bells", "the fly rang the bell", "kärbes helistas kella"),
    (
        "chair_conduct",
        "the real chair called for order or rang",
        "päris juhataja kutsus korrale või helistas kella",
    ),
    ("chair_time", "the real chair called time", "päris juhataja: aeg läbi"),
    ("coincide", "fly and chair within two events", "kärbes ja juhataja kahe sündmuse sees"),
]


def _bi(en: str, et: str, tag: str = "span", cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<{tag}{c} data-en="{html.escape(en)}" data-et="{html.escape(et)}">{html.escape(en)}</{tag}>'


def _card(x: dict) -> str:
    S = x["summary"]
    figs = [
        (S["stimuli"], "events", "sündmust"),
        (S["fly_bells"], "fly bells", "kärbse kellahelinat"),
        (S["chair_order"] + S["chair_bell"], "chair: order", "juhataja: korrale"),
        (S["coincide"], "coincided", "langes kokku"),
    ]
    f = "".join(f'<div class="fig"><b>{n}</b>{_bi(en, et)}</div>' for n, en, et in figs)
    return (
        f'<a class="card" href="{html.escape(x["href"])}">'
        f'<div class="when">{_bi(x["date"], x["date_et"])}</div>'
        f"<p>{_bi(x.get('blurb_en', ''), x.get('blurb_et', ''))}</p>"
        f'<div class="figs">{f}</div>'
        f'<div class="go">{_bi("Watch the sitting →", "Vaata istungit →")}</div>'
        f"</a>"
    )


def _table(sittings: list[dict]) -> str:
    head = (
        "<tr><th></th>"
        + "".join(f"<th>{_bi(x['date'], x['date_et'])}</th>" for x in sittings)
        + "</tr>"
    )
    rows = []
    for key, en, et in ROWS:
        cells = []
        for x in sittings:
            S = x["summary"]
            v = S["chair_order"] + S["chair_bell"] if key == "chair_conduct" else S[key]
            if key == "hostile":
                v = f"{v} ({100 * v / max(1, S['stimuli']):.0f}%)"
            cells.append(f"<td>{v}</td>")
        rows.append(f"<tr><td>{_bi(en, et)}</td>{''.join(cells)}</tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def build(sittings: list[dict], repo_url: str) -> str:
    t = TEMPLATE.read_text(encoding="utf-8")
    ordered = sorted(sittings, key=lambda x: not x.get("default", False))
    tokens = {
        "__CARDS__": "".join(_card(x) for x in ordered),
        "__TABLE__": _table(ordered),
        "__REPO__": html.escape(repo_url),
        "__FLY_B64__": base64.b64encode(FLY.read_bytes()).decode(),
        "__HALL_B64__": base64.b64encode(HALL_PHOTO.read_bytes()).decode()
        if HALL_PHOTO.exists()
        else "",
        "__SITTINGS_JSON__": json.dumps(
            [{k: x[k] for k in ("iso", "date", "date_et", "href")} for x in ordered],
            ensure_ascii=False,
        ),
    }
    for k, v in tokens.items():
        if k not in t:
            raise ValueError(f"landing template has no {k}")
        t = t.replace(k, v)
    return t
