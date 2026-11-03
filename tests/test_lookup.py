"""Seam 1: the boundary index, built from a Dataset release's files, and its lookup operation."""

import json

import pytest

from conftest import FIXTURE_DATASET
from nomos.boundary_index import BoundaryDataError, BoundaryIndex
from nomos.location import Location, LookupStatus

BRITISH_COLUMBIA = Location("Canada", "CA", "British Columbia", "fixture-CAN-BC")
ALBERTA = Location("Canada", "CA", "Alberta", "fixture-CAN-AB")


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


@pytest.mark.parametrize(
    "lat, lon",
    [(-17.0, 179.5), (-17.0, 180.0), (-17.0, -180.0), (-17.0, -179.5)],
    ids=["east of 180", "exactly 180", "exactly -180", "west of -180"],
)
def test_points_on_both_sides_of_the_antimeridian_and_exactly_on_it_are_matched(index, lat, lon):
    result = index.lookup(lat, lon)

    assert result.status is LookupStatus.MATCHED
    assert result.location.region == "Northern"
    assert result.location.country == "Fiji"
    assert result.location.country_code == "FJ"


def test_point_on_an_edge_shared_by_two_regions_is_ambiguous_and_lists_both(index):
    result = index.lookup(55.0, -120.0)

    assert result.status is LookupStatus.AMBIGUOUS
    assert result.location is None
    assert set(result.candidates) == {BRITISH_COLUMBIA, ALBERTA}


def test_region_whose_country_disagrees_with_the_containing_country_is_ambiguous_and_lists_both(index):
    # Kordofan (Sudan) reaches into ADM0 South Sudan between lat 9.5 and 10.
    result = index.lookup(9.75, 32.0)

    assert result.status is LookupStatus.AMBIGUOUS
    assert result.location is None
    assert set(result.candidates) == {
        Location("Sudan", "SD", "Kordofan", "fixture-SDN-KOR"),
        Location("South Sudan", "SS"),
    }


def test_region_on_a_border_between_countries_is_matched_when_one_of_them_is_its_country(index):
    # Lat 50 is the Canada / United States border in ADM0; only British Columbia reaches it in ADM1.
    result = index.lookup(50.0, -125.0)

    assert result.status is LookupStatus.MATCHED
    assert result.location == BRITISH_COLUMBIA


def test_point_outside_every_region_and_every_country_is_no_match(index):
    # Open sea, 10 degrees west of British Columbia and far beyond any Nearby match tolerance.
    result = index.lookup(55.0, -140.0)

    assert result.status is LookupStatus.NO_MATCH
    assert result.location is None
    assert result.candidates == ()


def test_point_just_outside_the_coast_within_5_km_is_a_nearby_match_with_its_distance(index):
    # In the sea west of British Columbia, outside every Region and Country: 4,902 m from the
    # coast at lon -130, measured geodesically (pyproj.Geod) when the test was written.
    result = index.lookup(55.0, -130.0766)

    assert result.status is LookupStatus.NEARBY
    assert result.location == BRITISH_COLUMBIA
    assert result.distance_m == pytest.approx(4902, abs=1)


def test_point_off_the_coast_beyond_5_km_is_no_match(index):
    # 5,107 m from the coast at lon -130.
    result = index.lookup(55.0, -130.0798)

    assert result.status is LookupStatus.NO_MATCH
    assert result.location is None
    assert result.distance_m is None


def test_nearby_search_reaches_across_the_antimeridian(index):
    # In the sea just east of 180; Chukotka lies only west of -180, 854 m away.
    result = index.lookup(67.5, 179.98)

    assert result.status is LookupStatus.NEARBY
    assert result.location == Location("Russia", "RU", "Chukotka", "fixture-RUS-CHU")
    assert result.distance_m == pytest.approx(854, abs=1)


def test_nearby_match_inside_a_country_is_a_region_of_that_country_not_a_nearer_foreign_one(index):
    # In ADM0 Kenya, in its strip with no Region: Eastern (Uganda) is 2,226 m away and
    # Rift Valley (Kenya) 4,453 m.
    result = index.lookup(0.0, 36.02)

    assert result.status is LookupStatus.NEARBY
    assert result.location == Location("Kenya", "KE", "Rift Valley", "fixture-KEN-RV")
    assert result.distance_m == pytest.approx(4453, abs=1)


def test_point_inside_a_country_is_country_only_when_only_a_foreign_region_is_within_5_km(index):
    # In ADM0 Kenya: Eastern (Uganda) is 1,113 m away, Rift Valley (Kenya) 5,566 m.
    result = index.lookup(0.0, 36.01)

    assert result.status is LookupStatus.COUNTRY_ONLY
    assert result.location == Location("Kenya", "KE")
    assert result.distance_m is None


@pytest.mark.parametrize(
    "lat, lon, location",
    [
        (41.5, 13.02, Location("Vatican City", "VA")),  # 1.7 km east of the whole-country feature
        (-51.5, -57.98, Location("Falkland Islands (UK)", None)),  # 1.4 km east of the Disputed area
    ],
    ids=["whole-country feature", "Disputed area"],
)
def test_point_near_a_feature_that_stands_for_a_whole_country_is_country_only_not_nearby(
    index, lat, lon, location
):
    result = index.lookup(lat, lon)

    assert result.status is LookupStatus.COUNTRY_ONLY
    assert result.location == location
    assert result.distance_m is None


def rewrite_coordinates(source, dest, transform):
    """Copy a GeoJSON file, passing every (lon, lat) pair through transform."""
    data = json.loads(source.read_text(encoding="utf-8"))

    def walk(coords):
        if isinstance(coords[0], (int, float)):
            return list(transform(*coords))
        return [walk(c) for c in coords]

    for feature in data["features"]:
        feature["geometry"]["coordinates"] = walk(feature["geometry"]["coordinates"])
    dest.write_text(json.dumps(data), encoding="utf-8")
    return dest


def test_building_refuses_boundary_data_whose_coordinates_are_not_longitude_and_latitude(tmp_path):
    # A projected dataset, in metres rather than degrees.
    adm1 = rewrite_coordinates(
        FIXTURE_DATASET / "fixtureCGAZ_ADM1.geojson", tmp_path / "adm1.geojson",
        lambda lon, lat: (lon * 111_000, lat * 111_000),
    )

    with pytest.raises(BoundaryDataError, match="ADM1.*longitude"):
        BoundaryIndex.build(adm0=FIXTURE_DATASET / "fixtureCGAZ_ADM0.geojson", adm1=adm1)


def test_building_tolerates_float_noise_just_beyond_180_but_not_more(tmp_path):
    def stretch(by):
        return lambda lon, lat: (lon + by if lon > 179.9 else lon, lat)

    noisy = rewrite_coordinates(
        FIXTURE_DATASET / "fixtureCGAZ_ADM0.geojson", tmp_path / "noisy.geojson", stretch(1e-12)
    )
    beyond = rewrite_coordinates(
        FIXTURE_DATASET / "fixtureCGAZ_ADM0.geojson", tmp_path / "beyond.geojson", stretch(1e-3)
    )
    adm1 = FIXTURE_DATASET / "fixtureCGAZ_ADM1.geojson"

    assert BoundaryIndex.build(adm0=noisy, adm1=adm1).lookup(-17.0, 180.0).status is LookupStatus.MATCHED
    with pytest.raises(BoundaryDataError, match="ADM0"):
        BoundaryIndex.build(adm0=beyond, adm1=adm1)


@pytest.mark.parametrize(
    "lat, lon, reason",
    [
        (float("nan"), -125.0, "latitude"),
        (55.0, float("nan"), "longitude"),
        (float("inf"), -125.0, "latitude"),
        (55.0, float("-inf"), "longitude"),
        (-125.0, 55.0, "latitude"),  # British Columbia with latitude and longitude swapped
        (90.5, 0.0, "latitude"),
        (-90.5, 0.0, "latitude"),
        (0.0, 180.5, "longitude"),
        (0.0, -180.5, "longitude"),
    ],
    ids=["NaN latitude", "NaN longitude", "infinite latitude", "infinite longitude",
         "swapped latitude and longitude", "latitude above 90", "latitude below -90",
         "longitude above 180", "longitude below -180"],
)
def test_coordinates_that_are_not_finite_or_out_of_range_are_invalid_input_with_a_reason(
    index, lat, lon, reason
):
    result = index.lookup(lat, lon)

    assert result.status is LookupStatus.INVALID_INPUT
    assert reason in result.reason
    assert result.location is None
    assert result.candidates == ()


@pytest.mark.parametrize("lat, lon", [(90.0, 0.0), (-90.0, 0.0)], ids=["North Pole", "South Pole"])
def test_the_poles_are_valid_input(index, lat, lon):
    assert index.lookup(lat, lon).status is not LookupStatus.INVALID_INPUT


def test_point_in_a_country_but_in_no_region_is_a_country_only_location(index):
    # France's second square, like French Guiana, has no ADM1 unit and none within reach.
    result = index.lookup(4.0, -53.0)

    assert result.status is LookupStatus.COUNTRY_ONLY
    assert result.location == Location("France", "FR")
    assert result.location.caption == "France"


def test_point_in_a_whole_country_feature_is_a_country_only_location_not_region_and_country(index):
    # Vatican City's ADM1 feature is the whole Country (shapeType ADM0).
    result = index.lookup(41.5, 12.5)

    assert result.status is LookupStatus.COUNTRY_ONLY
    assert result.location == Location("Vatican City", "VA")
    assert result.location.caption == "Vatican City"


def test_point_in_a_disputed_area_is_a_country_only_location_under_its_dataset_name_with_no_code(index):
    # The Falklands' ADM1 feature is a Disputed area (shapeType DISP, non-ISO shapeGroup 117).
    result = index.lookup(-51.5, -59.0)

    assert result.status is LookupStatus.COUNTRY_ONLY
    assert result.location == Location("Falkland Islands (UK)", None)
    assert result.location.caption == "Falkland Islands (UK)"
