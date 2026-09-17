"""The soma atlas: real coordinates, deliberately non-uniform sampling."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from karbes import atlas as A
from karbes.graph.populations import ANNOTATIONS

ROOT = Path("data/malecns")
pytestmark = pytest.mark.skipif(
    not (ROOT / ANNOTATIONS).exists(), reason="MaleCNS annotations not downloaded"
)


@pytest.fixture(scope="module")
def built():
    return A.build(ROOT)


def test_it_samples_the_neurons_that_have_real_coordinates(built):
    assert sum(built.population.values()) == 139_662
    assert abs(built.k - A.DEFAULT_SAMPLE) <= len(A.GROUP_NAMES)


def test_body_ids_stay_integers(built):
    assert built.bodies.dtype == np.int64
    assert len(np.unique(built.bodies)) == built.k


def test_the_readout_pool_is_kept_whole(built):
    """The descending neurons are what the vote is read from; sampling them away would
    put roughly 150 of 1,300 on screen and hide the thing being measured."""
    kept = int((built.group == A.GROUP_NAMES.index("descending")).sum())
    assert kept == built.population["descending"]
    assert built.fractions()["descending"] == 1.0


def test_the_sample_is_stratified_not_uniform(built):
    """Optic-lobe cells are 65% of located somas. If the page were shown a uniform sample
    it would draw two enormous eyes and a nerve cord of barely 1,500 points."""
    fractions = built.fractions()
    assert fractions["cord"] > fractions["optic"] * 2
    assert fractions["central"] > fractions["optic"]


def test_quantisation_keeps_the_brain_in_proportion(built):
    """One shared scale for all three axes. Per-axis scaling would stretch the brain."""
    assert built.xyz.dtype == np.uint16
    assert built.xyz.max() == np.iinfo(np.uint16).max
    # Two axes are shorter than the longest, so neither may reach full scale.
    assert (built.xyz.max(axis=0) < np.iinfo(np.uint16).max).sum() == 2


def test_the_blob_is_the_size_the_budget_assumed(built):
    assert len(built.web_bytes()) == built.k * 7
    assert len(built.web_bytes()) < 150_000


def test_the_sample_is_deterministic(built):
    again = A.build(ROOT)
    assert np.array_equal(built.bodies, again.bodies)
    assert np.array_equal(built.xyz, again.xyz)
