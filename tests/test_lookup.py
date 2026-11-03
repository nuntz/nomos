"""Seam 1: the boundary index, built from a Dataset release's files, and its lookup operation."""

import pytest

from conftest import FIXTURE_DATASET
from nomos.boundary_index import BoundaryIndex
from nomos.location import LookupStatus


@pytest.fixture(scope="module")
def index() -> BoundaryIndex:
    return BoundaryIndex.build(
        adm0=FIXTURE_DATASET / "fixtureCGAZ_ADM0.geojson",
        adm1=FIXTURE_DATASET / "fixtureCGAZ_ADM1.geojson",
    )


def test_point_inside_a_region_is_matched_with_its_location(index):
    result = index.lookup(55.0, -125.0)

    assert result.status is LookupStatus.MATCHED
    assert result.location.region == "British Columbia"
    assert result.location.region_id == "fixture-CAN-BC"
    assert result.location.country == "Canada"
    assert result.location.country_code == "CA"


def test_point_inside_a_hole_resolves_to_the_enclosed_unit_not_the_surrounding_one(index):
    result = index.lookup(-25.0, 25.0)

    assert result.status is LookupStatus.MATCHED
    assert result.location.region == "Maseru District"
    assert result.location.country == "Lesotho"
    assert result.location.country_code == "LS"


def test_point_around_a_hole_resolves_to_the_surrounding_unit(index):
    result = index.lookup(-22.0, 22.0)

    assert result.status is LookupStatus.MATCHED
    assert result.location.region == "Free State"
    assert result.location.country == "South Africa"
    assert result.location.country_code == "ZA"
