"""Seam 2: `nomos resolve` reading GPS from real camera output, on generated JPEGs."""

import json
from pathlib import Path

import pytest

from conftest import exiftool, make_geotagged_jpeg, make_jpeg


@pytest.fixture
def resolve(nomos):
    """Build the fixture index once, then run `nomos resolve` and return the report's records by path."""
    nomos("build-index")

    def run(library: Path) -> dict[str, dict]:
        nomos("resolve", str(library))
        report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
        return {record["path"]: record for record in report["photos"]}

    return run


def test_a_photo_without_a_gps_block_is_no_gps(resolve, tmp_path):
    library = tmp_path / "library"
    make_jpeg(library / "untagged.jpg")

    records = resolve(library)

    assert records["untagged.jpg"]["lookup_status"] == "no_gps"
    assert records["untagged.jpg"]["latitude"] is None
    assert records["untagged.jpg"]["longitude"] is None


def test_a_zero_zero_coordinate_is_no_gps(resolve, tmp_path):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "placeholder.jpg", 0.0, 0.0)

    records = resolve(library)

    assert records["placeholder.jpg"]["lookup_status"] == "no_gps"
    assert records["placeholder.jpg"]["latitude"] is None
    assert records["placeholder.jpg"]["longitude"] is None


def test_a_void_gps_status_is_no_gps(resolve, tmp_path):
    library = tmp_path / "library"
    void = make_geotagged_jpeg(library / "void.jpg", 55.5, -125.25)
    exiftool("-overwrite_original", "-GPSStatus#=V", void)

    records = resolve(library)

    assert records["void.jpg"]["lookup_status"] == "no_gps"
    assert records["void.jpg"]["latitude"] is None
