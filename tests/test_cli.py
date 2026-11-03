"""Seam 2: the `nomos` CLI, end to end, with real ExifTool on generated JPEGs."""

import json
import shutil
from pathlib import Path

from conftest import (
    FIXTURE_DATASET,
    exiftool,
    make_geotagged_jpeg,
    make_jpeg,
    read_tags,
    write_fixture_manifest,
)


def test_help_lists_the_three_commands(nomos):
    result = nomos("--help")

    for command in ("build-index", "resolve", "write-tags"):
        assert command in result.stdout


def test_exits_with_a_clear_error_when_exiftool_is_not_installed(nomos, tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    nomos.env["PATH"] = str(empty_bin)

    result = nomos("build-index", check=False)

    assert result.returncode != 0
    assert "ExifTool" in result.stderr
    assert "not found" in result.stderr
    assert "Traceback" not in result.stderr


def test_build_index_downloads_the_release_into_a_per_release_cache_folder(nomos):
    nomos("build-index")

    release_dir = Path(nomos.env["XDG_CACHE_HOME"]) / "nomos" / "fixture-v1"
    for name in ("fixtureCGAZ_ADM0.geojson", "fixtureCGAZ_ADM1.geojson"):
        downloaded = release_dir / name
        assert downloaded.read_bytes() == (FIXTURE_DATASET / name).read_bytes()


def test_build_index_refuses_a_download_whose_checksum_does_not_match(nomos, tmp_path):
    tampered = tmp_path / "tampered-release"
    shutil.copytree(FIXTURE_DATASET, tampered)
    adm1 = tampered / "fixtureCGAZ_ADM1.geojson"
    adm1.write_bytes(adm1.read_bytes().replace(b"British Columbia", b"British Colombia"))
    write_fixture_manifest(Path(nomos.env["NOMOS_MANIFEST"]), dataset_dir=tampered)

    result = nomos("build-index", check=False)

    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert "ADM1" in result.stderr
    release_dir = Path(nomos.env["XDG_CACHE_HOME"]) / "nomos" / "fixture-v1"
    assert not (release_dir / "fixtureCGAZ_ADM1.geojson").exists()
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "a.jpg", 55.0, -125.0)
    resolved = nomos("resolve", str(library), check=False)
    assert resolved.returncode != 0
    assert "run `nomos build-index`" in resolved.stderr


def test_resolve_reports_the_location_of_each_photo_and_changes_no_photo(nomos, tmp_path):
    library = tmp_path / "library"
    bc = make_geotagged_jpeg(library / "DCIM" / "100CANON" / "bc.jpg", 55.5, -125.25)
    maseru = make_geotagged_jpeg(library / "maseru.jpg", -25.0, 25.0)
    before = {photo: photo.read_bytes() for photo in (bc, maseru)}
    nomos("build-index")

    result = nomos("resolve", str(library))

    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    assert report["library_root"] == str(library.resolve())
    assert report["dataset_release"] == "fixture-v1"
    assert sorted(report["photos"], key=lambda record: record["path"]) == [
        {
            "path": "DCIM/100CANON/bc.jpg",
            "latitude": 55.5,
            "longitude": -125.25,
            "lookup_status": "matched",
            "country_code": "CA",
            "country": "Canada",
            "region_id": "fixture-CAN-BC",
            "region": "British Columbia",
            "caption": "British Columbia, Canada",
        },
        {
            "path": "maseru.jpg",
            "latitude": -25.0,
            "longitude": 25.0,
            "lookup_status": "matched",
            "country_code": "LS",
            "country": "Lesotho",
            "region_id": "fixture-LSO-MAS",
            "region": "Maseru District",
            "caption": "Maseru District, Lesotho",
        },
    ]
    assert result.stdout.splitlines()[-1] == (
        "2 photos: matched 2, nearby 0, country_only 0, ambiguous 0, no_match 0, no_gps 0, invalid_input 0"
    )
    assert {photo: photo.read_bytes() for photo in (bc, maseru)} == before
    assert sorted(p.name for p in library.rglob("*") if p.is_file()) == ["bc.jpg", "maseru.jpg"]


def test_resolve_writes_the_report_to_an_explicit_path(nomos, tmp_path):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "a.jpg", 42.5, 2.5)
    nomos("build-index")

    nomos("resolve", str(library), "--report", str(tmp_path / "reports" / "lyon.json"))

    report = json.loads((tmp_path / "reports" / "lyon.json").read_text(encoding="utf-8"))
    assert report["photos"][0]["caption"] == "Auvergne-Rhône-Alpes, France"
    assert not (nomos.cwd / "nomos-report.json").exists()


def test_resolve_uses_the_cached_index_without_the_boundary_files(nomos, tmp_path):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "a.jpg", 55.5, -125.25)
    nomos("build-index")
    release_dir = Path(nomos.env["XDG_CACHE_HOME"]) / "nomos" / "fixture-v1"
    for boundary_file in release_dir.glob("*.geojson"):
        boundary_file.unlink()

    nomos("resolve", str(library))

    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    assert report["photos"][0]["region"] == "British Columbia"


def image_data_hash(photo: Path) -> str:
    return exiftool("-s3", "-api", "ImageHashType=SHA256", "-ImageDataHash", photo).strip()


def test_write_tags_writes_the_location_of_matched_photos_into_standard_xmp_fields(nomos, tmp_path):
    library = tmp_path / "library"
    lyon = make_geotagged_jpeg(library / "DCIM" / "lyon.jpg", 44.75, 4.5)
    maseru = make_geotagged_jpeg(library / "maseru.jpg", -25.0, 25.0)
    image_data = {photo: image_data_hash(photo) for photo in (lyon, maseru)}
    nomos("build-index")
    nomos("resolve", str(library))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    shutil.move(nomos.cwd / "nomos-report.json", elsewhere / "report.json")

    nomos("write-tags", str(elsewhere / "report.json"))

    location_tags = ("XMP-photoshop:State", "XMP-photoshop:Country", "XMP-iptcCore:CountryCode")
    assert read_tags(lyon, *location_tags) == {
        "XMP-photoshop:State": "Auvergne-Rhône-Alpes",
        "XMP-photoshop:Country": "France",
        "XMP-iptcCore:CountryCode": "FR",
    }
    assert read_tags(maseru, *location_tags) == {
        "XMP-photoshop:State": "Maseru District",
        "XMP-photoshop:Country": "Lesotho",
        "XMP-iptcCore:CountryCode": "LS",
    }
    assert {photo: image_data_hash(photo) for photo in (lyon, maseru)} == image_data


NOMOS_TAGS = ("XMP-nomos:RegionID", "XMP-nomos:DatasetRelease", "XMP-nomos:LookupStatus")


def test_write_tags_writes_the_nomos_namespace_into_each_written_photo(nomos, tmp_path):
    library = tmp_path / "library"
    lyon = make_geotagged_jpeg(library / "lyon.jpg", 44.75, 4.5)
    maseru = make_geotagged_jpeg(library / "maseru.jpg", -25.0, 25.0)
    nomos("build-index")
    nomos("resolve", str(library))

    nomos("write-tags", "nomos-report.json")

    assert read_tags(lyon, *NOMOS_TAGS) == {
        "XMP-nomos:RegionID": "fixture-FRA-ARA",
        "XMP-nomos:DatasetRelease": "fixture-v1",
        "XMP-nomos:LookupStatus": "matched",
    }
    assert read_tags(maseru, *NOMOS_TAGS) == {
        "XMP-nomos:RegionID": "fixture-LSO-MAS",
        "XMP-nomos:DatasetRelease": "fixture-v1",
        "XMP-nomos:LookupStatus": "matched",
    }


def test_write_tags_writes_no_nomos_namespace_into_photos_it_does_not_write(nomos, tmp_path):
    library = tmp_path / "library"
    no_gps = make_jpeg(library / "no-gps.jpg")
    open_water = make_geotagged_jpeg(library / "open-water.jpg", 55.0, -140.0)
    nomos("build-index")
    nomos("resolve", str(library))
    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    assert {record["path"]: record["lookup_status"] for record in report["photos"]} == {
        "no-gps.jpg": "no_gps",
        "open-water.jpg": "no_match",
    }

    result = nomos("write-tags", "nomos-report.json")

    assert "skipped_unresolved 2" in result.stdout
    for photo in (no_gps, open_water):
        assert read_tags(photo, "XMP-nomos:all") == {}
