"""Finding the photos in a Photo library and reading their GPS coordinates."""

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import batched
from pathlib import Path

from nomos.exiftool import ExifTool
from nomos.location import LookupStatus

JPEG_SUFFIXES = {".jpg", ".jpeg"}
READ_BATCH = 200

_GPS_TAGS = (
    "EXIF:GPSLatitude",
    "EXIF:GPSLatitudeRef",
    "EXIF:GPSLongitude",
    "EXIF:GPSLongitudeRef",
    "EXIF:GPSStatus",
    "XMP-exif:GPSLatitude",
    "XMP-exif:GPSLongitude",
)


@dataclass(frozen=True)
class GpsReading:
    """A photo's coordinates, or the Lookup status (no GPS, invalid input) that stands in for them."""

    latitude: float | None = None
    longitude: float | None = None
    status: LookupStatus | None = None
    reason: str | None = None


def discover_photos(library: Path) -> list[Path]:
    """The JPEG photos in a Photo library and all its subfolders, sorted.

    Matches .jpg and .jpeg in any letter case. Skips hidden files and folders (which covers
    macOS "._" resource files) and never follows symlinks, so links can't add photos from
    outside the library or loop.
    """
    photos = []
    for folder, subfolders, files in os.walk(library, followlinks=False):
        subfolders[:] = [name for name in subfolders if not name.startswith(".")]
        for name in files:
            path = Path(folder, name)
            if name.startswith(".") or path.suffix.lower() not in JPEG_SUFFIXES:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            photos.append(path)
    return sorted(photos)


def read_photo_gps(exiftool: ExifTool, photo: Path) -> GpsReading:
    """Read one photo's GPS coordinates, exactly as `resolve` reads them.

    Use it to compare a photo's current coordinates with a report's. A photo ExifTool cannot
    read (including a missing one) reads as no GPS, so check that the file exists first.
    """
    ((_, reading),) = read_gps(exiftool, [photo])
    return reading


def read_gps(exiftool: ExifTool, photos: Sequence[Path]) -> Iterator[tuple[Path, GpsReading]]:
    """Read each photo's GPS coordinates, in order, in batches."""
    for batch in batched(photos, READ_BATCH):
        tags = exiftool.read(batch, _GPS_TAGS)
        for photo in batch:
            yield photo, _gps_from_tags(tags.get(photo, {}))


def _gps_from_tags(tags: dict) -> GpsReading:
    if tags.get("EXIF:GPSLatitude") is None or tags.get("EXIF:GPSLongitude") is None:
        return _xmp_gps(tags)
    if tags.get("EXIF:GPSStatus") == "V":  # the camera recorded a void fix
        return GpsReading(status=LookupStatus.NO_GPS)
    return _exif_gps(tags)


def _exif_gps(tags: dict) -> GpsReading:
    # The raw values are unsigned; the sign comes from the Ref fields, applied here rather than
    # relying on ExifTool's Composite values, which silently drop the sign when a Ref is missing.
    lat_ref, lon_ref = tags.get("EXIF:GPSLatitudeRef"), tags.get("EXIF:GPSLongitudeRef")
    missing = [
        name
        for name, ref, allowed in (("GPSLatitudeRef", lat_ref, "NS"), ("GPSLongitudeRef", lon_ref, "EW"))
        if ref not in tuple(allowed)
    ]
    if missing:
        return GpsReading(
            status=LookupStatus.INVALID_INPUT,
            reason=f"{' and '.join(missing)} missing, so the hemisphere is unknown",
        )
    lat, lon = float(tags["EXIF:GPSLatitude"]), float(tags["EXIF:GPSLongitude"])
    return _reading(-lat if lat_ref == "S" else lat, -lon if lon_ref == "W" else lon)


def _xmp_gps(tags: dict) -> GpsReading:
    # XMP-exif stores the coordinates signed, so there is no Ref to apply.
    lat, lon = tags.get("XMP:GPSLatitude"), tags.get("XMP:GPSLongitude")
    if lat is None or lon is None:
        return GpsReading(status=LookupStatus.NO_GPS)
    return _reading(float(lat), float(lon))


def _reading(latitude: float, longitude: float) -> GpsReading:
    if latitude == 0 and longitude == 0:
        # A placeholder some devices write when they have no fix.
        return GpsReading(status=LookupStatus.NO_GPS)
    return GpsReading(latitude=latitude, longitude=longitude)
