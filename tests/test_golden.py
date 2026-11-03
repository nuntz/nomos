"""The golden suite: real coordinates against the real Dataset release, geoBoundaries CGAZ v6.0.0.

It is kept apart from the fixture suite by the `golden` marker, which the default `pytest` run
excludes. Run it with:

    uv run pytest -m golden

It runs `nomos build-index` with the packaged manifest in the normal Nomos cache
($XDG_CACHE_HOME/nomos/v6.0.0/, else ~/.cache/nomos/v6.0.0/). The first run downloads about
760 MB; later runs reuse the verified download and the index. To seed the cache from files
already on disk, copy them there under their release file names first: build-index verifies
them and downloads nothing. CI runs this suite on a schedule and when the manifest changes
(.github/workflows/golden.yml).

To add a case, add a row to GOLDEN. Every coordinate that the spec does not give is chosen and
verified against v6.0.0 when the row is written, never guessed; note the margin to the nearest
boundary in the comment. A row states the Lookup status and the whole expected Location (or
None), for an ambiguous lookup every candidate, and for a Nearby match its distance in metres.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import NOMOS_EXECUTABLE, make_geotagged_jpeg
from nomos.boundary_index import BoundaryIndex
from nomos.dataset import MANIFEST_ENV, Manifest, load_index
from nomos.location import Location, LookupStatus

pytestmark = pytest.mark.golden


@dataclass(frozen=True)
class Golden:
    case: str
    lat: float
    lon: float
    status: LookupStatus
    location: Location | None = None
    candidates: frozenset[Location] = frozenset()
    distance_m: float | None = None  # a Nearby match's distance, checked to within 1 m


BRITISH_COLUMBIA = Location("Canada", "CA", "British Columbia", "82249235B24619009834807")
ALBERTA = Location("Canada", "CA", "Alberta", "82249235B5553315981608")
NORTHERN_FIJI = Location("Fiji", "FJ", "Northern", "53030831B91072554514863")

GOLDEN = [
    Golden("Vancouver", 49.28, -123.12, LookupStatus.MATCHED, BRITISH_COLUMBIA),
    Golden(
        "Lyon", 45.76, 4.84, LookupStatus.MATCHED,
        Location("France", "FR", "Auvergne-Rhône-Alpes", "19338628B73800214047876"),
    ),
    Golden(
        "Maseru, inside the hole in South Africa", -29.31, 27.48, LookupStatus.MATCHED,
        Location("Lesotho", "LS", "Maseru District", "63558799B83139219064193"),
    ),
    # Chosen: 3.2 km inside the coast of Graham Island.
    Golden("Haida Gwaii, onshore", 53.5, -132.0, LookupStatus.MATCHED, BRITISH_COLUMBIA),
    # Off Haida Gwaii, outside every Region and Country: 285.7 m from British Columbia.
    Golden(
        "Haida Gwaii, offshore", 53.25, -132.07, LookupStatus.NEARBY, BRITISH_COLUMBIA, distance_m=285.7,
    ),
    Golden("Taveuni, east of 180", -16.896, 179.975, LookupStatus.MATCHED, NORTHERN_FIJI),
    Golden("Taveuni, west of -180", -16.818, -179.931, LookupStatus.MATCHED, NORTHERN_FIJI),
    # Chosen: on Taveuni, where CGAZ splits Northern at the antimeridian.
    Golden("Taveuni, exactly on lon 180", -16.85, 180.0, LookupStatus.MATCHED, NORTHERN_FIJI),
    Golden("Taveuni, exactly on lon -180", -16.85, -180.0, LookupStatus.MATCHED, NORTHERN_FIJI),
    # 600 m either side of the British Columbia / Alberta border at 120°W.
    Golden("British Columbia side of 120°W", 57.0, -120.01, LookupStatus.MATCHED, BRITISH_COLUMBIA),
    Golden("Alberta side of 120°W", 57.0, -119.99, LookupStatus.MATCHED, ALBERTA),
    # Chosen: Pristina. Kosovo's shapeGroup XKX is not an ISO 3166-1 code, so it gets no code.
    Golden(
        "Pristina, Kosovo", 42.66, 21.17, LookupStatus.MATCHED,
        Location("Kosovo", None, "District of Prishtina", "2360587B5118871504069"),
    ),
    # Country-only Locations. In ADM0 France, with no Region within 50 km; 1.3 km inside France.
    Golden("Cayenne, French Guiana", 4.9372, -52.326, LookupStatus.COUNTRY_ONLY, Location("France", "FR")),
    # Chosen: in US waters, 25.7 km inside ADM0 and 31.8 km from Michigan, beyond any Nearby match.
    Golden(
        "Mid-Lake Superior", 47.7, -87.5, LookupStatus.COUNTRY_ONLY, Location("United States", "US"),
    ),
    # Chosen: Longyearbyen, in ADM0 Norway with no Region within 50 km.
    Golden("Svalbard", 78.22, 15.65, LookupStatus.COUNTRY_ONLY, Location("Norway", "NO")),
    # Chosen: a Disputed area (DIS007, shapeType DISP), 8.6 km inside it. Stanley is not used: it
    # lies 231 m outside every feature.
    Golden(
        "Falkland Islands", -51.8, -58.5, LookupStatus.COUNTRY_ONLY, Location("Falkland Islands (UK)", None),
    ),
    # Chosen: a Disputed area whose shapeGroup ESH is an ISO code. It still gets no country code.
    Golden("Western Sahara", 24.0, -13.0, LookupStatus.COUNTRY_ONLY, Location("Western Sahara", None)),
    # A whole-country ADM1 feature (shapeType ADM0), 276 m inside it.
    Golden("Vatican City", 41.9029, 12.4534, LookupStatus.COUNTRY_ONLY, Location("Vatican City", "VA")),
    # Chosen: inland Antarctica, another whole-country ADM1 feature.
    Golden("Antarctica", -82.0, 0.0, LookupStatus.COUNTRY_ONLY, Location("Antarctica", "AQ")),
    # Near features that stand for a whole Country, a Nearby hit is country only, not nearby.
    # The South Pole is in ADM0 Antarctica, 120 m from the whole-country ADM1 feature.
    Golden("South Pole", -90.0, 0.0, LookupStatus.COUNTRY_ONLY, Location("Antarctica", "AQ")),
    # Stanley lies outside every feature, 231.6 m from the Disputed area DIS007.
    Golden(
        "Stanley, Falkland Islands", -51.69, -57.86, LookupStatus.COUNTRY_ONLY,
        Location("Falkland Islands (UK)", None),
    ),
    # Open water: the nearest Region, British Columbia, is 15.4 km away, beyond any Nearby match.
    Golden("Strait of Georgia", 49.25, -123.6, LookupStatus.NO_MATCH),
    # Chosen: in the Kafia Kingi area, ADM1 South Darfur (Sudan) lies inside ADM0 South Sudan.
    # 49.4 km inside South Darfur and 39.4 km inside South Sudan.
    Golden(
        "South Darfur inside South Sudan", 9.3, 24.1, LookupStatus.AMBIGUOUS,
        candidates=frozenset({
            Location("Sudan", "SD", "South Darfur", "86620642B33888251991816"),
            Location("South Sudan", "SS"),
        }),
    ),
]


def run_nomos(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed `nomos` CLI with the packaged manifest."""
    env = {name: value for name, value in os.environ.items() if name != MANIFEST_ENV}
    result = subprocess.run([NOMOS_EXECUTABLE, *args], env=env, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"nomos {' '.join(args)} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


@pytest.fixture(scope="session")
def build_index() -> subprocess.CompletedProcess[str]:
    """`nomos build-index` with the packaged manifest: it verifies the download against the
    pinned sizes and SHA-256 checksums (downloading what is missing), then builds the index."""
    return run_nomos("build-index")


@pytest.fixture(scope="session")
def v6_index(build_index) -> BoundaryIndex:
    """The boundary index of the packaged Dataset release, built through `nomos build-index`."""
    return load_index(Manifest.packaged())


def test_photos_are_resolved_against_the_pinned_dataset_release_v6_0_0(build_index, tmp_path: Path):
    make_geotagged_jpeg(tmp_path / "library" / "vancouver.jpg", 49.28, -123.12)

    run_nomos("resolve", str(tmp_path / "library"), "--report", str(tmp_path / "report.json"))

    assert "Dataset release v6.0.0" in build_index.stdout
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["dataset_release"] == "v6.0.0"
    assert [record["region_id"] for record in report["photos"]] == [BRITISH_COLUMBIA.region_id]


@pytest.mark.parametrize("golden", GOLDEN, ids=lambda golden: golden.case)
def test_golden(v6_index, golden):
    result = v6_index.lookup(golden.lat, golden.lon)

    assert result.status is golden.status
    assert result.location == golden.location
    assert set(result.candidates) == golden.candidates
    if golden.distance_m is None:
        assert result.distance_m is None
    else:
        assert result.distance_m == pytest.approx(golden.distance_m, abs=1)
