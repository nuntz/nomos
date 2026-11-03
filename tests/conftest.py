"""Shared test support for both seams.

The fixture Dataset release (tests/fixtures/dataset/) is a tiny hand-drawn
stand-in for geoBoundaries CGAZ, with the same field names. Its layout, in
(lon, lat) degrees:

ADM0 (Countries)
  Canada        CAN  [-130, -110] x [50, 60]
  United States USA  [-130, -110] x [45, 50]     shares the lat 50 edge with Canada
  France        FRA  [0, 5] x [40, 45]  and  [-54, -52] x [3, 5] (no ADM1 there)
  South Africa  ZAF  [20, 30] x [-30, -20] with a hole [24, 26] x [-26, -24]
  Lesotho       LSO  the hole [24, 26] x [-26, -24]
  Fiji          FJI  [178, 180.0000000000001] and [-180, -178], x [-18, -16]
                     (the east edge carries the same one-ulp noise as CGAZ v6.0.0)
  Vatican City  VAT  [12, 13] x [41, 42]
  Falkland Islands (UK)  117  shapeType DISP, [-60, -58] x [-52, -51]
  South Sudan   SSD  [30, 35] x [5, 10]
  Sudan         SDN  [30, 35] x [10, 15]

ADM1 (Regions)
  British Columbia     CAN  [-130, -120] x [50, 60]   shares lon -120 with Alberta
  Alberta              CAN  [-120, -110] x [50, 60]
  Washington           USA  [-130, -110] x [45, 49.9] (USA strip 49.9..50 has no ADM1)
  Auvergne-Rhône-Alpes FRA  [0, 5] x [40, 45]
  Free State           ZAF  ZAF's square, with the Lesotho hole
  Maseru District      LSO  the hole
  Northern             FJI  both antimeridian pieces
  Vatican City         VAT  shapeType ADM0 (a whole-country feature)
  Falkland Islands (UK) 117 shapeType DISP, shapeID DIS007, same square as in ADM0
                            (as in CGAZ: a non-ISO shapeGroup, in both layers)
  Upper Nile           SSD  [30, 35] x [5, 9.5]
  Kordofan             SDN  [30, 35] x [9.5, 15]  (9.5..10 lies in ADM0 South Sudan)

The sea west of lon -130 is the coastline gap for Nearby match tests
(at lat 55, 5 km is about 0.078 degrees of longitude).

After changing a fixture file, update its bytes and sha256 in manifest.json.
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

FIXTURE_DATASET = Path(__file__).parent / "fixtures" / "dataset"
# The `nomos` console script installed into the test environment (by `uv sync` / `uv run`).
NOMOS_EXECUTABLE = str(Path(sys.executable).parent / "nomos")


def write_fixture_manifest(dest: Path, dataset_dir: Path = FIXTURE_DATASET) -> Path:
    """Write the fixture manifest with its files served from file:// URLs in dataset_dir."""
    manifest = json.loads((FIXTURE_DATASET / "manifest.json").read_text())
    for entry in manifest["files"].values():
        entry["url"] = (dataset_dir / entry["url"]).resolve().as_uri()
    dest.write_text(json.dumps(manifest, indent=2))
    return dest


@pytest.fixture
def fixture_manifest(tmp_path: Path) -> Path:
    return write_fixture_manifest(tmp_path / "manifest.json")


@dataclass
class Nomos:
    """Runs the installed `nomos` CLI end to end, in a temporary cache and working directory."""

    env: dict[str, str]
    cwd: Path

    def __call__(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [NOMOS_EXECUTABLE, *args],
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"nomos {' '.join(args)} exited {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result


@pytest.fixture
def nomos(tmp_path: Path, fixture_manifest: Path) -> Nomos:
    cwd = tmp_path / "work"
    cwd.mkdir()
    env = dict(os.environ)
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    env["NOMOS_MANIFEST"] = str(fixture_manifest)
    return Nomos(env=env, cwd=cwd)


def exiftool(*args: str | Path) -> str:
    """Run ExifTool directly, as test code (not through Nomos)."""
    result = subprocess.run(
        ["exiftool", *map(str, args)], capture_output=True, text=True, check=True
    )
    return result.stdout


def read_tags(photo: Path, *tags: str) -> dict:
    """Read tags back from a photo with ExifTool, keyed as ExifTool's -G1 JSON output."""
    (data,) = json.loads(exiftool("-json", "-G1", "-n", *(f"-{t}" for t in tags), photo))
    data.pop("SourceFile")
    return data


def make_jpeg(path: Path, *exiftool_args: str) -> Path:
    """Generate a small JPEG and tag it with ExifTool. No binaries are committed."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (90, 140, 200)).save(path, "JPEG")
    if exiftool_args:
        exiftool("-overwrite_original", *exiftool_args, path)
    return path


def make_geotagged_jpeg(path: Path, lat: float, lon: float) -> Path:
    """A JPEG with EXIF GPS written as a camera does: unsigned values plus Ref fields."""
    return make_jpeg(
        path,
        f"-EXIF:GPSLatitude={abs(lat)}",
        f"-EXIF:GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
        f"-EXIF:GPSLongitude={abs(lon)}",
        f"-EXIF:GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
    )


@pytest.fixture(scope="session", autouse=True)
def _require_exiftool():
    if shutil.which("exiftool") is None:
        pytest.exit("ExifTool must be installed to run the Nomos test suite", returncode=1)
