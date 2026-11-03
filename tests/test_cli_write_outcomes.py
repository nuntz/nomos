"""Seam 2: `nomos write-tags` Write outcomes and overwrite policy, end to end with real ExifTool."""

import json
from pathlib import Path

from conftest import exiftool, make_geotagged_jpeg, read_tags

LYON = (44.75, 4.5)  # Auvergne-Rhône-Alpes, France, in the fixture Dataset release
XMP_LOCATION = ("XMP-photoshop:State", "XMP-photoshop:Country", "XMP-iptcCore:CountryCode")


def resolve(nomos, library: Path) -> Path:
    nomos("build-index")
    nomos("resolve", str(library))
    return nomos.cwd / "nomos-report.json"


def test_a_photo_with_a_state_in_xmp_is_skipped_existing(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    exiftool("-overwrite_original", "-XMP-photoshop:State=Rhône", photo)
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", str(report))

    lines = result.stdout.splitlines()
    assert "skipped_existing lyon.jpg" in lines
    assert "1 photo: written 0, skipped_existing 1, skipped_unresolved 0, skipped_stale 0" in lines
    assert read_tags(photo, *XMP_LOCATION, "XMP-nomos:all") == {"XMP-photoshop:State": "Rhône"}


def test_a_photo_with_a_location_in_iptc_iim_only_is_skipped_existing(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    exiftool("-overwrite_original", "-IPTC:Country-PrimaryLocationName=France", photo)
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", str(report))

    assert "skipped_existing lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, *XMP_LOCATION, "XMP-nomos:all") == {}
