"""Seam 2: `nomos write-tags` Write outcomes and overwrite policy, end to end with real ExifTool."""

import json
import os
import shutil
from pathlib import Path

import pytest

from conftest import exiftool, make_geotagged_jpeg, read_tags

LYON = (44.75, 4.5)  # Auvergne-Rhône-Alpes, France, in the fixture Dataset release
XMP_LOCATION = ("XMP-photoshop:State", "XMP-photoshop:Country", "XMP-iptcCore:CountryCode")


def edit_report(report: Path, path: str | None = None, **fields) -> None:
    """Change a report as another Dataset release could have resolved it: the report's own fields,
    or with path, that photo's record. None removes a field."""
    data = json.loads(report.read_text(encoding="utf-8"))
    (target,) = [data] if path is None else [record for record in data["photos"] if record["path"] == path]
    target.update(fields)
    for name in [name for name, value in target.items() if value is None]:
        del target[name]
    report.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def tag_with_an_older_nomos_run(nomos, library: Path, path: str, *options: str) -> None:
    """Tag a photo through `nomos write-tags` as a run against an older Dataset release did, which
    resolved it to the older Region Rhône-Alpes."""
    older = nomos.cwd / "older-report.json"
    nomos("build-index")
    nomos("resolve", str(library), "--report", str(older))
    edit_report(older, dataset_release="fixture-v0")
    edit_report(older, path, region="Rhône-Alpes", region_id="fixture-old-id", caption="Rhône-Alpes, France")
    nomos("write-tags", "--in-place", *options, str(older))


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
    tag_with_an_older_nomos_run(nomos, tmp_path / "library", "lyon.jpg")
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
    tag_with_an_older_nomos_run(nomos, tmp_path / "library", "lyon.jpg")
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


IIM_LOCATION = ("IPTC:Province-State", "IPTC:Country-PrimaryLocationName", "IPTC:Country-PrimaryLocationCode")


@pytest.mark.parametrize("options", [[], ["--iptc"]], ids=["xmp only", "with iptc"])
def test_overwrite_keeps_an_iim_location_entered_by_hand_after_nomos_tagged_the_photo(nomos, tmp_path, options):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    tag_with_an_older_nomos_run(nomos, tmp_path / "library", "lyon.jpg")
    exiftool("-overwrite_original", "-IPTC:Province-State=Rhône", photo)  # by hand, in older software
    before = read_tags(photo, *XMP_LOCATION, *IIM_LOCATION, "XMP-nomos:all")
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", "--overwrite", *options, str(report))

    assert "skipped_existing lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, *XMP_LOCATION, *IIM_LOCATION, "XMP-nomos:all") == before
    assert before["IPTC:Province-State"] == "Rhône"


def test_overwrite_without_iptc_removes_the_iim_location_nomos_wrote(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    tag_with_an_older_nomos_run(nomos, tmp_path / "library", "lyon.jpg", "--iptc")
    assert read_tags(photo, "IPTC:Province-State") == {"IPTC:Province-State": "Rhône-Alpes"}
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", "--overwrite", str(report))

    assert "written lyon.jpg" in result.stdout.splitlines()
    assert read_tags(photo, *IIM_LOCATION) == {}
    assert read_tags(photo, "XMP-photoshop:State") == {"XMP-photoshop:State": "Auvergne-Rhône-Alpes"}


def test_overwrite_with_a_country_only_location_removes_the_stale_region(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    tag_with_an_older_nomos_run(nomos, tmp_path / "library", "lyon.jpg", "--iptc")  # IIM fields too
    report = resolve(nomos, tmp_path / "library")
    edit_report(
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
    assert lines[-1] == "3 photos: written 1, skipped_existing 0, skipped_unresolved 0, skipped_stale 2"
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


DESCRIPTIONS = ("IFD0:ImageDescription", "XMP-dc:Description", "IPTC:Caption-Abstract")


def read_descriptions(photo: Path) -> dict:
    # Without -n, so text is decoded as any reader would see it.
    (data,) = json.loads(exiftool("-json", "-G1", *(f"-{tag}" for tag in DESCRIPTIONS), photo))
    data.pop("SourceFile")
    return data


def test_write_tags_leaves_the_description_intact(nomos, tmp_path):
    photo = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", *LYON)
    exiftool(
        "-overwrite_original",
        "-EXIF:ImageDescription=Marché, quai Saint-Antoine",
        "-XMP-dc:Description=Marché, quai Saint-Antoine",
        "-IPTC:CodedCharacterSet=UTF8",
        "-IPTC:Caption-Abstract=Marché, quai Saint-Antoine",
        photo,
    )
    before = read_descriptions(photo)
    assert len(before) == 3
    report = resolve(nomos, tmp_path / "library")

    result = nomos("write-tags", "--iptc", str(report))

    assert "written lyon.jpg" in result.stdout.splitlines()
    assert read_descriptions(photo) == before


def log_exiftool_arguments(nomos, tmp_path: Path) -> Path:
    """Put an `exiftool` first on Nomos's PATH that logs every argument Nomos sends it (on the
    command line and, in stay-open mode, on stdin) before passing them to the real ExifTool."""
    log, shim = tmp_path / "exiftool-arguments.log", tmp_path / "bin" / "exiftool"
    shim.parent.mkdir()
    shim.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{log}"\ntee -a "{log}" | exec "{shutil.which("exiftool")}" "$@"\n'
    )
    shim.chmod(0o755)
    nomos.env["PATH"] = f"{shim.parent}{os.pathsep}{nomos.env['PATH']}"
    return log


def test_nomos_never_asks_exiftool_for_the_description(nomos, tmp_path):
    library = tmp_path / "library"
    photo = make_geotagged_jpeg(library / "lyon.jpg", *LYON)
    exiftool("-overwrite_original", "-IPTC:Caption-Abstract=Café à Lyon", "-XMP-dc:Description=Café", photo)
    tag_with_an_older_nomos_run(nomos, library, "lyon.jpg")
    log = log_exiftool_arguments(nomos, tmp_path)
    report = resolve(nomos, library)

    nomos("write-tags", "--overwrite", "--iptc", str(report))

    arguments = log.read_text(encoding="utf-8").splitlines()
    assert any(argument.startswith("-XMP-photoshop:State") for argument in arguments)  # the log works
    requested = [argument for argument in arguments if argument.startswith("-") and "=" not in argument]
    assert [
        argument
        for argument in requested
        if "description" in argument.lower() or "caption" in argument.lower() or argument.lower().endswith(":all")
    ] == []


def library_state(library: Path) -> dict[Path, tuple[bytes, int]]:
    """Every file in the library (backups included) with its content and modification time."""
    return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in library.rglob("*") if path.is_file()}


@pytest.mark.parametrize(
    "options",
    [[], ["--overwrite"], ["--overwrite", "--iptc"], ["--in-place", "--overwrite"]],
    ids=" ".join,
)
def test_a_second_run_on_the_same_report_changes_no_file(nomos, tmp_path, options):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "lyon.jpg", *LYON)
    make_geotagged_jpeg(library / "maseru.jpg", -25.0, 25.0)
    make_geotagged_jpeg(library / "vatican.jpg", 41.5, 12.5)  # Country-only: no State, an empty RegionID
    make_geotagged_jpeg(library / "open-water.jpg", 55.0, -140.0)
    report = resolve(nomos, library)
    first = nomos("write-tags", *options, str(report))
    assert "written 3" in first.stdout
    state = library_state(library)

    second = nomos("write-tags", *options, str(report))

    assert "written 0, skipped_existing 3, skipped_unresolved 1" in second.stdout
    assert library_state(library) == state
