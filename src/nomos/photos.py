"""Finding the photos in a Photo library and reading their GPS coordinates."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import batched
from pathlib import Path

from nomos.exiftool import ExifTool
from nomos.location import LookupStatus

JPEG_SUFFIXES = {".jpg", ".jpeg"}
READ_BATCH = 200

_EXIF_GPS_TAGS = ("EXIF:GPSLatitude", "EXIF:GPSLatitudeRef", "EXIF:GPSLongitude", "EXIF:GPSLongitudeRef")


@dataclass(frozen=True)
class GpsReading:
    """A photo's coordinates, or the Lookup status (no GPS, invalid input) that stands in for them."""

    latitude: float | None = None
    longitude: float | None = None
    status: LookupStatus | None = None
    reason: str | None = None


def discover_photos(library: Path) -> list[Path]:
    """The JPEG photos in a Photo library, sorted."""
    return sorted(
        path for path in library.rglob("*") if path.suffix.lower() in JPEG_SUFFIXES and path.is_file()
    )


def read_gps(exiftool: ExifTool, photos: Sequence[Path]) -> Iterator[tuple[Path, GpsReading]]:
    """Read each photo's GPS coordinates, in order."""
    for batch in batched(photos, READ_BATCH):
        tags = exiftool.read(batch, _EXIF_GPS_TAGS)
        for photo in batch:
            yield photo, _gps_from_tags(tags.get(photo, {}))


def _gps_from_tags(tags: dict) -> GpsReading:
    # The raw values are unsigned; the sign comes from the Ref fields, applied here rather than
    # relying on ExifTool's Composite values, which silently drop the sign when a Ref is missing.
    lat, lon = tags.get("EXIF:GPSLatitude"), tags.get("EXIF:GPSLongitude")
    if lat is None or lon is None:
        return GpsReading(status=LookupStatus.NO_GPS)
    lat_ref, lon_ref = tags.get("EXIF:GPSLatitudeRef"), tags.get("EXIF:GPSLongitudeRef")
    if lat_ref not in ("N", "S") or lon_ref not in ("E", "W"):
        return GpsReading(status=LookupStatus.INVALID_INPUT, reason="GPS hemisphere reference missing")
    return GpsReading(
        latitude=-float(lat) if lat_ref == "S" else float(lat),
        longitude=-float(lon) if lon_ref == "W" else float(lon),
    )
