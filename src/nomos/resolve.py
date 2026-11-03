"""`nomos resolve`: look up the Location of every photo in a Photo library. Changes no photo."""

from pathlib import Path

from nomos.boundary_index import BoundaryIndex
from nomos.errors import NomosError
from nomos.exiftool import ExifTool
from nomos.location import LookupResult
from nomos.photos import discover_photos, read_gps
from nomos.report import PhotoRecord, Report


def resolve_library(library: Path, index: BoundaryIndex, dataset_release: str) -> Report:
    root = library.resolve()
    if not root.is_dir():
        raise NomosError(f"{library} is not a folder")
    records = []
    with ExifTool() as exiftool:
        for photo, gps in read_gps(exiftool, discover_photos(root)):
            if gps.status is not None:
                result = LookupResult(gps.status, reason=gps.reason)
            else:
                result = index.lookup(gps.latitude, gps.longitude)
            records.append(PhotoRecord(photo.relative_to(root).as_posix(), gps.latitude, gps.longitude, result))
    return Report(root, dataset_release, records)
