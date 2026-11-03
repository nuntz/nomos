"""Seam 2: the `nomos` CLI, end to end, with real ExifTool on generated JPEGs."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

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


def test_help_credits_the_boundary_data(nomos):
    result = nomos("--help")

    assert "Boundary data from geoBoundaries (www.geoboundaries.org), CC BY 4.0" in " ".join(result.stdout.split())


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


def serve_fixture_release(nomos, tmp_path: Path, name: str = "served-release") -> Path:
    """Copy the fixture Dataset release to its own folder and point the manifest's URLs at it."""
    served = tmp_path / name
    shutil.copytree(FIXTURE_DATASET, served)
    write_fixture_manifest(Path(nomos.env["NOMOS_MANIFEST"]), dataset_dir=served)
    return served


def test_build_index_reuses_a_verified_download_instead_of_downloading_again(nomos, tmp_path):
    served = serve_fixture_release(nomos, tmp_path)
    nomos("build-index")
    shutil.rmtree(served)  # any download attempt would now fail

    result = nomos("build-index")

    assert "Downloading" not in result.stdout
    assert "verified" in result.stdout
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "a.jpg", 55.5, -125.25)
    nomos("resolve", str(library))
    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    assert report["photos"][0]["region"] == "British Columbia"


def test_build_index_downloads_again_when_the_cached_download_does_not_verify(nomos, tmp_path):
    nomos("build-index")
    cached = Path(nomos.env["XDG_CACHE_HOME"]) / "nomos" / "fixture-v1" / "fixtureCGAZ_ADM1.geojson"
    cached.write_bytes(cached.read_bytes().replace(b"British Columbia", b"British Colombia"))

    result = nomos("build-index")

    assert "Downloading ADM1" in result.stdout
    assert "Downloading ADM0" not in result.stdout
    assert cached.read_bytes() == (FIXTURE_DATASET / "fixtureCGAZ_ADM1.geojson").read_bytes()


def change_fixture_release(nomos, tmp_path: Path) -> Path:
    """Point the manifest at a changed fixture release, under the same release name, in which
    British Columbia is renamed. Returns the folder that serves it."""
    changed = tmp_path / "changed-release"
    shutil.copytree(FIXTURE_DATASET, changed)
    adm1 = changed / "fixtureCGAZ_ADM1.geojson"
    adm1.write_bytes(adm1.read_bytes().replace(b"British Columbia", b"Colombie-Britannique"))
    manifest_path = Path(nomos.env["NOMOS_MANIFEST"])
    write_fixture_manifest(manifest_path, dataset_dir=changed)
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["ADM1"]["bytes"] = adm1.stat().st_size
    manifest["files"]["ADM1"]["sha256"] = hashlib.sha256(adm1.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return changed


def resolved_region(nomos, tmp_path: Path, *resolve_args: str) -> str:
    library = tmp_path / "library"
    if not library.exists():
        make_geotagged_jpeg(library / "a.jpg", 55.5, -125.25)
    nomos("resolve", str(library), *resolve_args)
    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    return report["photos"][0]["region"]


def test_build_index_does_not_rebuild_an_index_that_is_up_to_date(nomos):
    nomos("build-index")

    result = nomos("build-index")

    assert "Building" not in result.stdout
    assert "up to date" in result.stdout


def test_build_index_rebuilds_the_index_when_the_manifest_changes(nomos, tmp_path):
    nomos("build-index")
    assert resolved_region(nomos, tmp_path) == "British Columbia"
    change_fixture_release(nomos, tmp_path)

    nomos("build-index")

    assert resolved_region(nomos, tmp_path) == "Colombie-Britannique"


def test_resolve_never_uses_an_index_built_from_another_manifest(nomos, tmp_path):
    nomos("build-index")
    change_fixture_release(nomos, tmp_path)
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "a.jpg", 55.5, -125.25)

    result = nomos("resolve", str(library), check=False)

    assert result.returncode != 0
    assert "run `nomos build-index`" in result.stderr
    assert not (nomos.cwd / "nomos-report.json").exists()


def test_resolve_rebuilds_a_stale_index_from_verified_downloads_without_downloading(nomos, tmp_path):
    nomos("build-index")
    changed = change_fixture_release(nomos, tmp_path)
    release_dir = Path(nomos.env["XDG_CACHE_HOME"]) / "nomos" / "fixture-v1"
    shutil.copy(changed / "fixtureCGAZ_ADM1.geojson", release_dir / "fixtureCGAZ_ADM1.geojson")
    shutil.rmtree(changed)  # any download attempt would now fail

    assert resolved_region(nomos, tmp_path) == "Colombie-Britannique"


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


def test_resolve_lists_the_candidates_of_ambiguous_photos_in_the_report(nomos, tmp_path):
    library = tmp_path / "library"
    make_geotagged_jpeg(library / "border.jpg", 55.0, -120.0)  # on the British Columbia / Alberta edge
    make_geotagged_jpeg(library / "kordofan.jpg", 9.75, 32.0)  # Sudan's Kordofan inside South Sudan
    nomos("build-index")

    result = nomos("resolve", str(library))

    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    records = {record["path"]: record for record in report["photos"]}
    assert records["border.jpg"]["lookup_status"] == "ambiguous"
    assert "caption" not in records["border.jpg"]
    assert sorted(records["border.jpg"]["candidates"], key=lambda c: c["caption"]) == [
        {
            "country_code": "CA",
            "country": "Canada",
            "region_id": "fixture-CAN-AB",
            "region": "Alberta",
            "caption": "Alberta, Canada",
        },
        {
            "country_code": "CA",
            "country": "Canada",
            "region_id": "fixture-CAN-BC",
            "region": "British Columbia",
            "caption": "British Columbia, Canada",
        },
    ]
    assert records["kordofan.jpg"]["lookup_status"] == "ambiguous"
    assert sorted(records["kordofan.jpg"]["candidates"], key=lambda c: c["caption"]) == [
        {
            "country_code": "SD",
            "country": "Sudan",
            "region_id": "fixture-SDN-KOR",
            "region": "Kordofan",
            "caption": "Kordofan, Sudan",
        },
        {
            "country_code": "SS",
            "country": "South Sudan",
            "region_id": None,
            "region": None,
            "caption": "South Sudan",
        },
    ]
    assert "ambiguous 2" in result.stdout.splitlines()[-1]


def test_write_tags_writes_nothing_to_ambiguous_no_match_or_invalid_input_photos(nomos, tmp_path):
    library = tmp_path / "library"
    photos = {
        "border.jpg": make_geotagged_jpeg(library / "border.jpg", 55.0, -120.0),
        "open-water.jpg": make_geotagged_jpeg(library / "open-water.jpg", 55.0, -140.0),
        # ExifTool keeps an EXIF longitude beyond 180 as it is, as in corrupt metadata.
        "corrupt.jpg": make_jpeg(
            library / "corrupt.jpg",
            "-EXIF:GPSLatitude=55", "-EXIF:GPSLatitudeRef=N",
            "-EXIF:GPSLongitude=200", "-EXIF:GPSLongitudeRef=E",
        ),
    }
    before = {name: photo.read_bytes() for name, photo in photos.items()}
    nomos("build-index")
    nomos("resolve", str(library))
    report = json.loads((nomos.cwd / "nomos-report.json").read_text(encoding="utf-8"))
    records = {record["path"]: record for record in report["photos"]}
    assert {path: record["lookup_status"] for path, record in records.items()} == {
        "border.jpg": "ambiguous",
        "open-water.jpg": "no_match",
        "corrupt.jpg": "invalid_input",
    }
    assert "longitude" in records["corrupt.jpg"]["reason"]

    result = nomos("write-tags", "nomos-report.json")

    assert "written 0" in result.stdout
    assert "skipped_unresolved 3" in result.stdout
    assert {name: photo.read_bytes() for name, photo in photos.items()} == before
