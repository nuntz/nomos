"""Seam 2: the `nomos` CLI, end to end, with real ExifTool on generated JPEGs."""

import json
import shutil
from pathlib import Path

import pytest

from conftest import FIXTURE_DATASET, exiftool, make_geotagged_jpeg, read_tags, write_fixture_manifest


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
    # Without --iptc, no legacy IPTC-IIM fields are written.
    assert read_tags(lyon, "IPTC:all") == {}
    assert read_tags(maseru, "IPTC:all") == {}


def test_write_tags_with_iptc_also_writes_the_location_into_utf8_iptc_iim_fields(nomos, tmp_path):
    lyon = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", 44.75, 4.5)
    nomos("build-index")
    nomos("resolve", str(tmp_path / "library"))

    nomos("write-tags", "--iptc", str(nomos.cwd / "nomos-report.json"))

    # Read back without -n, so ExifTool decodes IIM by its coded character set as any reader would.
    (iim,) = json.loads(exiftool("-json", "-G1", "-IPTC:all", lyon))
    assert iim["IPTC:CodedCharacterSet"] == "UTF8"
    assert iim["IPTC:Province-State"] == "Auvergne-Rhône-Alpes"
    assert iim["IPTC:Country-PrimaryLocationName"] == "France"
    # IIM stores the code in a fixed 3 octets, so ExifTool pads "FR" with a space.
    assert iim["IPTC:Country-PrimaryLocationCode"].rstrip() == "FR"
    assert read_tags(lyon, "XMP-photoshop:State")["XMP-photoshop:State"] == "Auvergne-Rhône-Alpes"


def test_write_tags_with_iptc_leaves_existing_latin1_iim_alone_and_still_writes_xmp(nomos, tmp_path):
    # Without a UTF-8 marker, ExifTool writes IIM text as Latin-1, as older software does. Setting
    # the marker would make that Description read as invalid UTF-8, so Nomos skips the IIM part.
    lyon = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", 44.75, 4.5)
    exiftool("-overwrite_original", "-IPTC:Caption-Abstract=Café à Lyon", lyon)
    iim_before = read_tags(lyon, "IPTC:all")
    nomos("build-index")
    nomos("resolve", str(tmp_path / "library"))

    result = nomos("write-tags", "--iptc", str(nomos.cwd / "nomos-report.json"))

    assert "lyon.jpg" in result.stderr
    assert "IPTC-IIM" in result.stderr
    assert read_tags(lyon, "IPTC:all") == iim_before
    (iim,) = json.loads(exiftool("-json", "-G1", "-IPTC:all", lyon))
    assert iim["IPTC:Caption-Abstract"] == "Café à Lyon"
    assert read_tags(lyon, "XMP-photoshop:State")["XMP-photoshop:State"] == "Auvergne-Rhône-Alpes"
    assert "written 1" in result.stdout


@pytest.mark.parametrize(
    "existing_iim",
    [
        pytest.param(["-IPTC:Caption-Abstract=Cafe in Lyon"], id="ascii-without-marker"),
        pytest.param(["-IPTC:CodedCharacterSet=UTF8", "-IPTC:Caption-Abstract=Café à Lyon"], id="utf8"),
    ],
)
def test_write_tags_with_iptc_adds_to_existing_iim_that_the_utf8_marker_cannot_garble(
    nomos, tmp_path, existing_iim
):
    lyon = make_geotagged_jpeg(tmp_path / "library" / "lyon.jpg", 44.75, 4.5)
    exiftool("-overwrite_original", *existing_iim, lyon)
    (before,) = json.loads(exiftool("-json", "-G1", "-IPTC:Caption-Abstract", lyon))
    nomos("build-index")
    nomos("resolve", str(tmp_path / "library"))

    result = nomos("write-tags", "--iptc", str(nomos.cwd / "nomos-report.json"))

    assert "warning" not in result.stderr
    (iim,) = json.loads(exiftool("-json", "-G1", "-IPTC:all", lyon))
    assert iim["IPTC:Province-State"] == "Auvergne-Rhône-Alpes"
    assert iim["IPTC:Caption-Abstract"] == before["IPTC:Caption-Abstract"]
