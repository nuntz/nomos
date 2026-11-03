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


def test_a_missing_latitude_ref_is_invalid_input_and_the_hemisphere_is_not_guessed(resolve, tmp_path):
    library = tmp_path / "library"
    make_jpeg(library / "no-lat-ref.jpg", "-GPSLatitude=45.76", "-GPSLongitude=4.84", "-GPSLongitudeRef=E")

    records = resolve(library)

    record = records["no-lat-ref.jpg"]
    assert record["lookup_status"] == "invalid_input"
    assert "GPSLatitudeRef" in record["reason"]
    assert record["latitude"] is None
    assert "country" not in record


def test_a_missing_longitude_ref_is_invalid_input(resolve, tmp_path):
    library = tmp_path / "library"
    make_jpeg(library / "no-lon-ref.jpg", "-GPSLatitude=45.76", "-GPSLatitudeRef=N", "-GPSLongitude=4.84")

    records = resolve(library)

    record = records["no-lon-ref.jpg"]
    assert record["lookup_status"] == "invalid_input"
    assert "GPSLongitudeRef" in record["reason"]
    assert "GPSLatitudeRef" not in record["reason"]


def test_southern_and_western_coordinates_are_read_with_the_right_sign(resolve, tmp_path):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "south-east.jpg", -22.0, 22.0)
    make_geotagged_jpeg(library / "north-west.jpg", 47.0, -120.0)
    make_geotagged_jpeg(library / "south-west.jpg", -51.5, -59.0)

    records = resolve(library)

    assert (records["south-east.jpg"]["latitude"], records["south-east.jpg"]["longitude"]) == (-22.0, 22.0)
    assert records["south-east.jpg"]["region"] == "Free State"
    assert (records["north-west.jpg"]["latitude"], records["north-west.jpg"]["longitude"]) == (47.0, -120.0)
    assert records["north-west.jpg"]["region"] == "Washington"
    assert (records["south-west.jpg"]["latitude"], records["south-west.jpg"]["longitude"]) == (-51.5, -59.0)
    assert records["south-west.jpg"]["country"] == "Falkland Islands (UK)"


def test_without_exif_gps_the_signed_xmp_gps_is_used(resolve, tmp_path):
    library = tmp_path / "library"
    make_jpeg(library / "xmp-only.jpg", "-XMP-exif:GPSLatitude=-25.0", "-XMP-exif:GPSLongitude=25.0")
    make_jpeg(library / "xmp-west.jpg", "-XMP-exif:GPSLatitude=55.5", "-XMP-exif:GPSLongitude=-125.25")

    records = resolve(library)

    assert (records["xmp-only.jpg"]["latitude"], records["xmp-only.jpg"]["longitude"]) == (-25.0, 25.0)
    assert records["xmp-only.jpg"]["region"] == "Maseru District"
    assert (records["xmp-west.jpg"]["latitude"], records["xmp-west.jpg"]["longitude"]) == (55.5, -125.25)
    assert records["xmp-west.jpg"]["region"] == "British Columbia"


def test_exif_gps_takes_precedence_over_xmp_gps(resolve, tmp_path):
    library = tmp_path / "library"
    both = make_geotagged_jpeg(library / "both.jpg", 55.5, -125.25)
    exiftool("-overwrite_original", "-XMP-exif:GPSLatitude=-25.0", "-XMP-exif:GPSLongitude=25.0", both)

    records = resolve(library)

    assert records["both.jpg"]["region"] == "British Columbia"


def test_resolve_finds_jpegs_in_nested_subfolders_with_any_letter_case(resolve, tmp_path):
    library = tmp_path / "library"
    for name in ("DCIM/100CANON/IMG_0001.JPG", "DCIM/100CANON/IMG_0002.jpeg", "DCIM/101MSDCF/deep/a.JpG", "b.JPEG"):
        make_geotagged_jpeg(library / name, 55.5, -125.25)
    (library / "DCIM" / "100CANON" / "notes.txt").write_text("not a photo")
    make_jpeg(library / "DCIM" / "100CANON" / "IMG_0003.png")

    records = resolve(library)

    assert sorted(records) == [
        "DCIM/100CANON/IMG_0001.JPG",
        "DCIM/100CANON/IMG_0002.jpeg",
        "DCIM/101MSDCF/deep/a.JpG",
        "b.JPEG",
    ]


def test_resolve_skips_hidden_files_hidden_folders_macos_resource_files_and_symlinks(resolve, tmp_path):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "DCIM" / "IMG_0001.JPG", 55.5, -125.25)
    make_geotagged_jpeg(library / "DCIM" / ".hidden.jpg", 55.5, -125.25)
    # Hidden folders macOS leaves on SD cards: deleted photos and the Spotlight index.
    make_geotagged_jpeg(library / ".Trashes" / "501" / "deleted.jpg", 55.5, -125.25)
    make_geotagged_jpeg(library / ".Spotlight-V100" / "Store-V2" / "preview.jpg", 55.5, -125.25)
    make_geotagged_jpeg(library / "DCIM" / ".thumbnails" / "IMG_0001.JPG", 55.5, -125.25)
    (library / "DCIM" / "._IMG_0001.JPG").write_bytes(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        ")
    outside = make_geotagged_jpeg(tmp_path / "outside" / "elsewhere.jpg", 55.5, -125.25)
    (library / "DCIM" / "link.jpg").symlink_to(outside)
    (library / "DCIM" / "linked-folder").symlink_to(outside.parent, target_is_directory=True)
    (library / "DCIM" / "loop").symlink_to(library, target_is_directory=True)

    records = resolve(library)

    assert sorted(records) == ["DCIM/IMG_0001.JPG"]
