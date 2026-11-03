"""`nomos write-tags`: write each resolved Location from a report into its photo's XMP fields.

ExifTool rewrites only the metadata; the image data is never re-encoded.
"""

import math
from collections import Counter
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from nomos.exiftool import ExifTool
from nomos.location import Location, LookupStatus
from nomos.photos import read_photo_gps
from nomos.report import PhotoRecord, Report

# How far a photo's re-read coordinates may be from the report's before it counts as changed:
# about 1 cm, far below any real re-geotagging, but above float noise between two readings.
STALE_TOLERANCE_DEGREES = 1e-7
WRITABLE_STATUSES = {LookupStatus.MATCHED, LookupStatus.NEARBY, LookupStatus.COUNTRY_ONLY}
IIM_UTF8_MARKER = "\x1b%G"  # IPTC:CodedCharacterSet for UTF-8, as ExifTool reads it with -n


class WriteOutcome(StrEnum):
    """What happened when Nomos tried to write a Location into one photo (see GLOSSARY.md)."""

    WRITTEN = "written"
    SKIPPED_EXISTING = "skipped_existing"
    SKIPPED_UNRESOLVED = "skipped_unresolved"
    SKIPPED_STALE = "skipped_stale"


def location_tags(location: Location) -> dict[str, str]:
    """The standard XMP location fields for a Location."""
    tags = {}
    if location.region:
        tags["XMP-photoshop:State"] = location.region
    tags["XMP-photoshop:Country"] = location.country
    if location.country_code:
        tags["XMP-iptcCore:CountryCode"] = location.country_code
    return tags


def iptc_tags(location: Location) -> dict[str, str]:
    """The legacy IPTC-IIM location fields for a Location, marked as UTF-8 so accents survive."""
    tags = {"IPTC:CodedCharacterSet": "UTF8"}
    if location.region:
        tags["IPTC:Province-State"] = location.region
    tags["IPTC:Country-PrimaryLocationName"] = location.country
    if location.country_code:
        tags["IPTC:Country-PrimaryLocationCode"] = location.country_code
    return tags


def nomos_tags(record: PhotoRecord, dataset_release: str) -> dict[str, str]:
    """The Nomos XMP namespace fields (ADR 0001): how this photo's Location was found."""
    return {
        "XMP-nomos:RegionID": record.result.location.region_id or "",  # empty for a Country-only Location
        "XMP-nomos:DatasetRelease": dataset_release,
        "XMP-nomos:LookupStatus": record.result.status.value,
    }


def marking_iim_utf8_would_garble(iim: dict) -> bool:
    """Whether setting the UTF-8 marker would garble a photo's existing IPTC-IIM text.

    Without the marker, IIM text is read as Latin-1 (or another legacy character set), so
    any non-ASCII value would no longer decode once the marker says UTF-8.
    """
    if iim.get("IPTC:CodedCharacterSet") == IIM_UTF8_MARKER:
        return False
    values = [v for value in iim.values() for v in (value if isinstance(value, list) else [value])]
    return any(isinstance(value, str) and not value.isascii() for value in values)


# Every location field Nomos may write, in XMP and IPTC-IIM. When Nomos replaces a Location it
# wrote, each of these that the new Location leaves out is removed, so no stale Region survives.
LOCATION_FIELDS = (
    "XMP-photoshop:State",
    "XMP-photoshop:Country",
    "XMP-iptcCore:CountryCode",
    "IPTC:Province-State",
    "IPTC:Country-PrimaryLocationName",
    "IPTC:Country-PrimaryLocationCode",
)
NOMOS_FIELDS = ("XMP-nomos:RegionID", "XMP-nomos:DatasetRelease", "XMP-nomos:LookupStatus")
# A non-empty one of these means the photo already has a Location.
_EXISTING_LOCATION_FIELDS = (
    "XMP-photoshop:State",
    "XMP-photoshop:Country",
    "IPTC:Province-State",
    "IPTC:Country-PrimaryLocationName",
)


def _value(current: dict, field: str) -> str:
    """A field's current value as stripped text ("" when absent).

    ExifTool's -G keys a read by family-0 group (XMP-photoshop:State reads as XMP:State), and
    reads numeric-looking text as a number. IIM pads the country code to 3 bytes ("FR ").
    """
    group, name = field.split(":")
    value = current.get(f"{group.split('-')[0]}:{name}")
    return "" if value is None else str(value).strip()


def has_location(current: dict) -> bool:
    """Whether a photo already has a Location: a non-empty State or Country in XMP or IPTC-IIM."""
    return any(_value(current, field) for field in _EXISTING_LOCATION_FIELDS)


def written_by_nomos(current: dict) -> bool:
    """Whether a photo carries the Nomos namespace (ADR 0001). RegionID alone may be empty."""
    return any(_value(current, field) for field in ("XMP-nomos:DatasetRelease", "XMP-nomos:LookupStatus"))


def is_stale(exiftool: ExifTool, photo: Path, record: PhotoRecord) -> bool:
    """Whether a photo is missing, or its GPS coordinates changed since the report was made."""
    if not photo.is_file():
        return True
    gps = read_photo_gps(exiftool, photo)
    if gps.status is not None or record.latitude is None or record.longitude is None:
        return True
    return not (
        math.isclose(gps.latitude, record.latitude, rel_tol=0, abs_tol=STALE_TOLERANCE_DEGREES)
        and math.isclose(gps.longitude, record.longitude, rel_tol=0, abs_tol=STALE_TOLERANCE_DEGREES)
    )


def replacement(current: dict, tags: dict[str, str]) -> dict[str, str | None] | None:
    """The values that replace a Location Nomos wrote, or None when the photo already has them.

    Location fields the new values leave out are removed (None), such as the State of a
    Region-level Location replaced by a Country-only one. ExifTool rewrites a photo even when
    nothing changes, so skipping identical values is what keeps --overwrite idempotent.
    """
    if all(_value(current, field) == (tags.get(field) or "") for field in LOCATION_FIELDS + NOMOS_FIELDS):
        return None
    return {field: None for field in LOCATION_FIELDS} | tags


def write_tags(
    report: Report,
    iptc: bool = False,
    overwrite: bool = False,
    in_place: bool = False,
    warn: Callable[[str], None] = lambda message: None,
    on_outcome: Callable[[PhotoRecord, WriteOutcome], None] = lambda record, outcome: None,
) -> Counter[WriteOutcome]:
    """Write the report's Locations into its photos and count the Write outcomes.

    Each photo's GPS is re-read first: a photo that is missing, or whose coordinates changed
    since the report was made, is skipped as stale.

    A photo that already has a Location is skipped, unless overwrite is set and the photo
    carries the Nomos namespace: then Nomos wrote that Location, and it is replaced.

    ExifTool keeps a "<photo>_original" backup of each written photo, unless in_place is set.

    Each photo's Write outcome is passed to on_outcome as soon as it is known.

    With iptc, the legacy IPTC-IIM location fields are written too, except into a photo whose
    existing IIM text is not UTF-8: that photo gets its XMP fields only, and a warning.
    """
    outcomes: Counter[WriteOutcome] = Counter()
    with ExifTool() as exiftool:
        for record in report.photos:
            outcome = _write_photo(exiftool, report, record, iptc, overwrite, in_place, warn)
            outcomes[outcome] += 1
            on_outcome(record, outcome)
    return outcomes


def _write_photo(
    exiftool: ExifTool,
    report: Report,
    record: PhotoRecord,
    iptc: bool,
    overwrite: bool,
    in_place: bool,
    warn: Callable[[str], None],
) -> WriteOutcome:
    location = record.result.location
    if record.result.status not in WRITABLE_STATUSES or location is None:
        return WriteOutcome.SKIPPED_UNRESOLVED
    photo = report.photo_path(record)
    if is_stale(exiftool, photo, record):
        return WriteOutcome.SKIPPED_STALE
    current = exiftool.read([photo], LOCATION_FIELDS + NOMOS_FIELDS).get(photo, {})
    replacing = has_location(current)
    if replacing and not (overwrite and written_by_nomos(current)):
        return WriteOutcome.SKIPPED_EXISTING
    tags: dict[str, str | None] = location_tags(location) | nomos_tags(record, report.dataset_release)
    if iptc:
        if marking_iim_utf8_would_garble(exiftool.read([photo], ["IPTC:all"]).get(photo, {})):
            warn(
                f"{record.path}: existing IPTC-IIM text is not UTF-8, so only the XMP fields "
                "were written (writing UTF-8 IIM would garble it)"
            )
        else:
            tags |= iptc_tags(location)
    if replacing:
        tags = replacement(current, tags)
        if tags is None:
            return WriteOutcome.SKIPPED_EXISTING
    exiftool.write(photo, tags, keep_backup=not in_place)
    return WriteOutcome.WRITTEN


def summary(outcomes: Counter[WriteOutcome]) -> str:
    """One line with the count of photos per Write outcome."""
    total = sum(outcomes.values())
    noun = "photo" if total == 1 else "photos"
    return f"{total} {noun}: " + ", ".join(f"{outcome} {outcomes[outcome]}" for outcome in WriteOutcome)
