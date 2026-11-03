"""The Dataset release: its manifest, the verified download in the user cache, and the cached index.

The manifest ships inside the package. The NOMOS_MANIFEST environment variable points Nomos at
another one (tests use it for the fixture Dataset release). Downloads and the built index live in
$XDG_CACHE_HOME/nomos/<release>/.
"""

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from nomos.boundary_index import BoundaryIndex
from nomos.errors import NomosError

MANIFEST_ENV = "NOMOS_MANIFEST"
LAYERS = ("ADM0", "ADM1")
INDEX_NAME = "index.pickle"


class DatasetError(NomosError):
    pass


@dataclass(frozen=True)
class DatasetFile:
    url: str
    bytes: int
    sha256: str

    @property
    def filename(self) -> str:
        return self.url.rstrip("/").rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Manifest:
    release: str
    commit: str
    files: dict[str, DatasetFile]

    @classmethod
    def load(cls) -> "Manifest":
        """The manifest named by NOMOS_MANIFEST, or else the one shipped in the package."""
        override = os.environ.get(MANIFEST_ENV)
        if override:
            try:
                text = Path(override).read_text(encoding="utf-8")
            except OSError as error:
                raise DatasetError(f"cannot read manifest {override} ({MANIFEST_ENV}): {error}")
        else:
            text = resources.files("nomos").joinpath("data/manifest.json").read_text(encoding="utf-8")
        data = json.loads(text)
        return cls(
            release=data["release"],
            commit=data["commit"],
            files={layer: DatasetFile(**data["files"][layer]) for layer in LAYERS},
        )


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(base) / "nomos"


def release_dir(manifest: Manifest) -> Path:
    return cache_root() / manifest.release


def build_index(manifest: Manifest, progress=print) -> Path:
    """Download and verify the release's files, build the boundary index and save it to the cache."""
    folder = release_dir(manifest)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for layer in LAYERS:
        entry = manifest.files[layer]
        progress(f"Downloading {layer} from {entry.url}")
        paths[layer] = _download_verified(layer, entry, folder / entry.filename)
    progress(f"Building the boundary index for Dataset release {manifest.release}")
    index = BoundaryIndex.build(adm0=paths["ADM0"], adm1=paths["ADM1"])
    index_path = folder / INDEX_NAME
    index.save(index_path)
    return index_path


def load_index(manifest: Manifest) -> BoundaryIndex:
    """Load the prebuilt boundary index for the release. The raw boundary files are not read."""
    path = release_dir(manifest) / INDEX_NAME
    if not path.exists():
        raise DatasetError(
            f"no boundary index for Dataset release {manifest.release}; run `nomos build-index` first"
        )
    return BoundaryIndex.load(path)


def _download_verified(layer: str, entry: DatasetFile, dest: Path) -> Path:
    partial = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(entry.url) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise DatasetError(f"cannot download {layer} from {entry.url}: {error}")
    if size != entry.bytes or digest.hexdigest() != entry.sha256:
        partial.unlink(missing_ok=True)
        raise DatasetError(
            f"checksum mismatch for {layer} from {entry.url}: expected {entry.bytes} bytes with "
            f"SHA-256 {entry.sha256}, got {size} bytes with SHA-256 {digest.hexdigest()}. "
            "Refusing to use it."
        )
    partial.replace(dest)
    return dest
