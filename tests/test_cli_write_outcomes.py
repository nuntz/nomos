"""Seam 2: `nomos write-tags` Write outcomes and overwrite policy, end to end with real ExifTool."""

import json
from pathlib import Path

from conftest import exiftool, make_geotagged_jpeg, read_tags
from nomos.exiftool import NOMOS_CONFIG

LYON = (44.75, 4.5)  # Auvergne-Rhône-Alpes, France, in the fixture Dataset release
XMP_LOCATION = ("XMP-photoshop:State", "XMP-photoshop:Country", "XMP-iptcCore:CountryCode")


def tag_as_older_nomos_run(photo: Path, *location_args: str, release: str = "fixture-v0") -> None:
    """Tag a photo as a Nomos run against an older Dataset release would have."""
    exiftool(
        "-config",  # must come first; it defines the Nomos namespace so ExifTool can write it
        NOMOS_CONFIG,
        "-overwrite_original",
        *location_args,
        "-XMP-nomos:RegionID=fixture-old-id",
        f"-XMP-nomos:DatasetRelease={release}",
        "-XMP-nomos:LookupStatus=matched",
        photo,
    )


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


def test_overwrite_replaces_a_location_nomos_wrote_with_an_older_dataset_release(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    tag_as_older_nomos_run(
        photo, "-XMP-photoshop:State=Rhône-Alpes", "-XMP-photoshop:Country=France", "-XMP-iptcCore:CountryCode=FR"
    )
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", "--overwrite", str(report))

    assert "written lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, *XMP_LOCATION, "XMP-nomos:all") == {
        "XMP-photoshop:State": "Auvergne-Rhône-Alpes",
        "XMP-photoshop:Country": "France",
        "XMP-iptcCore:CountryCode": "FR",
        "XMP-nomos:RegionID": "fixture-FRA-ARA",
        "XMP-nomos:DatasetRelease": "fixture-v1",
        "XMP-nomos:LookupStatus": "matched",
    }
    assert read_tags(photo, "IPTC:all") == {}


def test_without_overwrite_a_location_nomos_wrote_earlier_is_kept(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    tag_as_older_nomos_run(photo, "-XMP-photoshop:State=Rhône-Alpes", "-XMP-photoshop:Country=France")
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", str(report))

    assert "skipped_existing lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, "XMP-photoshop:State", "XMP-nomos:DatasetRelease") == {
        "XMP-photoshop:State": "Rhône-Alpes",
        "XMP-nomos:DatasetRelease": "fixture-v0",
    }


def test_overwrite_keeps_a_location_entered_by_hand(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    exiftool("-overwrite_original", "-XMP-photoshop:State=Rhône", "-XMP-photoshop:Country=France", photo)
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", "--overwrite", str(report))

    assert "skipped_existing lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, *XMP_LOCATION, "XMP-nomos:all") == {
        "XMP-photoshop:State": "Rhône",
        "XMP-photoshop:Country": "France",
    }


def edit_report_record(report: Path, path: str, **fields) -> None:
    """Change one record of a report, as a later Dataset release could resolve it. None removes a field."""
    data = json.loads(report.read_text(encoding="utf-8"))
    (record,) = (record for record in data["photos"] if record["path"] == path)
    record.update(fields)
    for name in [name for name, value in record.items() if value is None]:
        del record[name]
    report.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_overwrite_with_a_country_only_location_removes_the_stale_region(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    tag_as_older_nomos_run(
        photo,
        "-XMP-photoshop:State=Rhône-Alpes",
        "-XMP-photoshop:Country=France",
        "-XMP-iptcCore:CountryCode=FR",
        # An older run with --iptc also wrote the IIM fields.
        "-IPTC:CodedCharacterSet=UTF8",
        "-IPTC:Province-State=Rhône-Alpes",
        "-IPTC:Country-PrimaryLocationName=France",
        "-IPTC:Country-PrimaryLocationCode=FR",
    )
    report = resolve(nomos, tmp_path / "library")
    edit_report_record(
        report, "lyon.jpg", lookup_status="country_only", region=None, region_id=None, caption="France"
    )

    result = nomos("write-tags", "--overwrite", "--iptc", str(report))

    assert "written lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, *XMP_LOCATION, "XMP-nomos:all") == {
        "XMP-photoshop:Country": "France",
        "XMP-iptcCore:CountryCode": "FR",
        "XMP-nomos:RegionID": "",
        "XMP-nomos:DatasetRelease": "fixture-v1",
        "XMP-nomos:LookupStatus": "country_only",
    }
    iim = read_tags(photo, "IPTC:Province-State", "IPTC:Country-PrimaryLocationName")
    assert iim == {"IPTC:Country-PrimaryLocationName": "France"}


def test_photos_moved_or_regeotagged_after_resolve_are_skipped_stale(nomos, tmp_path):
    library = tmp_path / "library"
    moved = make_geotagged_jpeg(library / "moved.jpg", *LYON)
    regeotagged = make_geotagged_jpeg(library / "regeotagged.jpg", *LYON)
    unchanged = make_geotagged_jpeg(library / "unchanged.jpg", *LYON)
    report = resolve(nomos, library)
    moved.rename(library / "elsewhere.jpg")
    exiftool("-overwrite_original", "-EXIF:GPSLatitude=55.5", "-EXIF:GPSLongitude=125.25", regeotagged)

    result = nomos("write-tags", str(report))

    lines = result.stdout.splitlines()
    assert "skipped_stale moved.jpg" in lines
    assert "skipped_stale regeotagged.jpg" in lines
    assert "written unchanged.jpg" in lines
    assert "3 photos: written 1, skipped_existing 0, skipped_unresolved 0, skipped_stale 2" in lines
    assert "re-run `nomos resolve`" in result.stdout.lower()
    assert read_tags(regeotagged, *XMP_LOCATION, "XMP-nomos:all") == {}
    assert read_tags(library / "elsewhere.jpg", *XMP_LOCATION, "XMP-nomos:all") == {}


def test_no_resolve_hint_when_no_photo_is_stale(nomos, tmp_path):
    make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", str(report))

    assert "nomos resolve" not in result.stdout


def test_write_tags_keeps_a_backup_of_each_written_photo_and_says_how_to_remove_them(nomos, tmp_path):
    library = tmp_path / "library"
    photo = make_geotagged_jpeg(library / "DCIM" / "lyon.jpg", *LYON)
    original = photo.read_bytes()
    report = resolve(nomos, library)

    result = nomos("write-tags", str(report))

    backup = library / "DCIM" / "lyon.jpg_original"
    assert backup.read_bytes() == original
    assert f"exiftool -r '-delete_original!' {library.resolve()}" in result.stdout


def test_write_tags_in_place_keeps_no_backups(nomos, tmp_path):
    library = tmp_path / "library"
    photo = make_geotagged_jpeg(library / "lyon.jpg", *LYON)
    report = resolve(nomos, library)

    result = nomos("write-tags", "--in-place", str(report))

    assert "written lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, "XMP-photoshop:State") == {"XMP-photoshop:State": "Auvergne-Rhône-Alpes"}
    assert sorted(path.name for path in library.iterdir()) == ["lyon.jpg"]
    assert "delete_original" not in result.stdout
