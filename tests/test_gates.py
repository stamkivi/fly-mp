"""Prose gates are not gates. These must actually block."""

from __future__ import annotations

import pytest

from karbes.gates import read_gate, require_gate, write_gate


def test_missing_gate_blocks(tmp_path):
    with pytest.raises(SystemExit, match="has not run"):
        require_gate("stage0", runs=tmp_path)


def test_failed_gate_blocks(tmp_path):
    write_gate("stage0", False, {"t1": "fail"}, runs=tmp_path)
    with pytest.raises(SystemExit, match="did not pass"):
        require_gate("stage0", runs=tmp_path)


def test_passing_gate_allows(tmp_path):
    write_gate("stage0", True, {"t1": "ok"}, runs=tmp_path)
    require_gate("stage0", runs=tmp_path)


def test_force_is_allowed_but_recorded(tmp_path):
    """An override is legitimate; an unrecorded one is not."""
    require_gate("stage0", force=True, runs=tmp_path)
    forced = read_gate("stage0_forced", runs=tmp_path)
    assert forced is not None
    assert "overridden with --force" in forced["measurements"]["note"]


def test_gate_records_measurements(tmp_path):
    write_gate("stage0", True, {"discriminative_votes": 568}, runs=tmp_path)
    assert read_gate("stage0", runs=tmp_path)["measurements"]["discriminative_votes"] == 568
