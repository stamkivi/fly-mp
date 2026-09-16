"""Machine-enforced stage gates.

Prose gates are not gates. Each stage writes its measured values and a verdict; the next
stage refuses to start without its predecessor's pass, overridable only by an explicit
--force that is recorded.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

RUNS = Path("runs")


def gate_path(stage: str, runs: Path = RUNS) -> Path:
    return runs / f"gate_{stage}.json"


def write_gate(stage: str, passed: bool, measurements: dict, runs: Path = RUNS) -> Path:
    runs.mkdir(parents=True, exist_ok=True)
    path = gate_path(stage, runs)
    path.write_text(
        json.dumps(
            {
                "stage": stage,
                "passed": passed,
                "at": datetime.now(tz=UTC).isoformat(),
                "measurements": measurements,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def read_gate(stage: str, runs: Path = RUNS) -> dict | None:
    path = gate_path(stage, runs)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def require_gate(stage: str, force: bool = False, runs: Path = RUNS) -> None:
    """Raise unless `stage` has a recorded pass. `force` is allowed but recorded."""
    gate = read_gate(stage, runs)
    if gate and gate.get("passed"):
        return
    reason = "has not run" if gate is None else "did not pass"
    if force:
        write_gate(
            f"{stage}_forced",
            True,
            {"note": f"gate '{stage}' {reason}; overridden with --force"},
            runs,
        )
        return
    raise SystemExit(
        f"gate '{stage}' {reason}. Run it first, or pass --force to override "
        f"(the override is recorded in runs/)."
    )
