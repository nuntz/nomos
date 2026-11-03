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
None). Rows for later Lookup statuses that need more (the candidates of an ambiguous lookup,
the distance of a Nearby match) add an optional field to Golden and an assertion for it.
"""

import os
import subprocess
from dataclasses import dataclass

import pytest

from conftest import NOMOS_EXECUTABLE
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
]


@pytest.fixture(scope="session")
def v6_index() -> BoundaryIndex:
    """The boundary index of the packaged Dataset release, built through `nomos build-index`."""
    manifest = Manifest.packaged()
    assert manifest.release == "v6.0.0"
    env = {name: value for name, value in os.environ.items() if name != MANIFEST_ENV}
    built = subprocess.run([NOMOS_EXECUTABLE, "build-index"], env=env, capture_output=True, text=True)
    if built.returncode != 0:
        pytest.fail(f"nomos build-index failed\nstdout:\n{built.stdout}\nstderr:\n{built.stderr}")
    return load_index(manifest)


@pytest.mark.parametrize("golden", GOLDEN, ids=lambda golden: golden.case)
def test_golden(v6_index, golden):
    result = v6_index.lookup(golden.lat, golden.lon)

    assert result.status is golden.status
    assert result.location == golden.location
