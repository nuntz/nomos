"""The packaged manifest pins the Dataset release Nomos resolves against (ADR 0002).

The expected values are copied from the spec, not from the manifest. Updating the Dataset
release means changing both, then re-running the golden suite (`uv run pytest -m golden`).
"""

from nomos.dataset import Manifest

COMMIT = "1289e40e366c7b320550be1ee0614a9472d572d4"
LFS = f"https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/{COMMIT}/releaseData/CGAZ"


def test_packaged_manifest_pins_cgaz_v6_0_0_by_commit_size_and_checksum():
    manifest = Manifest.packaged()

    assert manifest.release == "v6.0.0"
    assert manifest.commit == COMMIT
    adm0, adm1 = manifest.files["ADM0"], manifest.files["ADM1"]
    assert adm0.url == f"{LFS}/geoBoundariesCGAZ_ADM0.geojson"
    assert adm0.bytes == 401_198_724
    assert adm0.sha256 == "5e97632703209f192d87724c3c02c3ed70eccec32ebddb605af9647002b65d67"
    assert adm1.url == f"{LFS}/geoBoundariesCGAZ_ADM1.geojson"
    assert adm1.bytes == 361_574_443
    assert adm1.sha256 == "f77bb14b78ccbebb48f9eeeffaba1a0b0c395d9d1cf503d1243b5ac4ccecee3f"


def test_the_manifest_override_does_not_change_the_packaged_manifest(fixture_manifest, monkeypatch):
    monkeypatch.setenv("NOMOS_MANIFEST", str(fixture_manifest))

    assert Manifest.load().release == "fixture-v1"
    assert Manifest.packaged().release == "v6.0.0"
