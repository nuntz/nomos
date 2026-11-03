"""The Dataset release: its manifest, the verified download in the user cache, and the cached index.

The manifest ships inside the package. The NOMOS_MANIFEST environment variable points Nomos at
another one (tests use it for the fixture Dataset release). Downloads and the built index live in
$XDG_CACHE_HOME/nomos/<release>/. A download is reused only while it verifies against the
manifest, and the index is keyed by the manifest, so a changed manifest never reuses a stale one.
"""

import hashlib
import json
import os
import urllib.request
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path

from nomos.boundary_index import INDEX_FORMAT, BoundaryIndex, IndexFormatError
from nomos.errors import NomosError

MANIFEST_ENV = "NOMOS_MANIFEST"
LAYERS = ("ADM0", "ADM1")


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
            return cls.packaged()
        return cls._parse(text)

    @classmethod
    def packaged(cls) -> "Manifest":
        """The manifest shipped in the package, ignoring NOMOS_MANIFEST."""
        return cls._parse(resources.files("nomos").joinpath("data/manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def _parse(cls, text: str) -> "Manifest":
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


def index_path(manifest: Manifest) -> Path:
    """Where the index built from this exact manifest lives. The name is keyed by the manifest
    (and the index format), so any change to the manifest makes the cached index stale."""
    canonical = json.dumps(
        {"index_format": INDEX_FORMAT, "manifest": asdict(manifest)}, sort_keys=True
    ).encode("utf-8")
    return release_dir(manifest) / f"index-{hashlib.sha256(canonical).hexdigest()[:16]}.pickle"


def build_index(manifest: Manifest, progress=print) -> Path:
    """Make sure the release's files are downloaded and verified, and that the boundary index
    built from this manifest is in the cache. Only what is missing or stale is fetched or built."""
    path = index_path(manifest)
    paths = _verified_files(manifest, progress, download=True)
    if _load_current(path) is not None:
        progress(f"The boundary index for Dataset release {manifest.release} is up to date")
        return path
    _build(manifest, paths, progress)
    return path


def load_index(manifest: Manifest, progress=print) -> BoundaryIndex:
    """Load the boundary index built from this manifest. A missing or stale index is rebuilt from
    the verified downloads in the cache; nothing is downloaded."""
    index = _load_current(index_path(manifest))
    if index is None:
        try:
            paths = _verified_files(manifest, progress, download=False)
        except DatasetError as error:
            raise DatasetError(
                f"no boundary index for the current manifest of Dataset release {manifest.release} "
                f"({error}); run `nomos build-index` first"
            )
        index = _build(manifest, paths, progress)
    return index


def _load_current(path: Path) -> BoundaryIndex | None:
    try:
        return BoundaryIndex.load(path)
    except (OSError, IndexFormatError):
        return None


def _build(manifest: Manifest, paths: dict[str, Path], progress) -> BoundaryIndex:
    progress(f"Building the boundary index for Dataset release {manifest.release}")
    index = BoundaryIndex.build(adm0=paths["ADM0"], adm1=paths["ADM1"])
    path = index_path(manifest)
    index.save(path)
    for stale in path.parent.glob("index*.pickle"):
        if stale != path:
            stale.unlink(missing_ok=True)
    return index


def _verified_files(manifest: Manifest, progress, *, download: bool) -> dict[str, Path]:
    folder = release_dir(manifest)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for layer in LAYERS:
        entry = manifest.files[layer]
        dest = folder / entry.filename
        if _verifies(entry, dest):
            progress(f"{layer}: using the verified download at {dest}")
        elif download:
            progress(f"Downloading {layer} from {entry.url}")
            _download_verified(layer, entry, dest)
        else:
            raise DatasetError(f"no verified {layer} download")
        paths[layer] = dest
    return paths


def _verifies(entry: DatasetFile, path: Path) -> bool:
    """Whether path holds exactly the file the manifest pins: same byte size and SHA-256."""
    try:
        if path.stat().st_size != entry.bytes:
            return False
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == entry.sha256


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
