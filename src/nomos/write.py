"""`nomos write-tags`: write each resolved Location from a report into its photo's XMP fields.

Only the location fields and the Nomos namespace are written; the Description is never changed.
ExifTool rewrites only the metadata; the image data is never re-encoded.
"""

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from operator import attrgetter
from pathlib import Path

from nomos.exiftool import ExifTool, PhotoError
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


@dataclass(frozen=True)
class LocationField:
    """One part of a Location, with the XMP field and the legacy IPTC-IIM field that hold it."""

    xmp: str
    iim: str
    part: Callable[[Location], str | None]
    marks_existing: bool  # whether a non-empty value means the photo already has a Location


# Every location field Nomos may write. When Nomos replaces a Location it wrote, each of these
# that the new Location leaves out is removed, so no stale Region survives.
LOCATION_FIELDS = (
    LocationField("XMP-photoshop:State", "IPTC:Province-State", attrgetter("region"), marks_existing=True),
    LocationField(
        "XMP-photoshop:Country", "IPTC:Country-PrimaryLocationName", attrgetter("country"), marks_existing=True
    ),
    LocationField(
        "XMP-iptcCore:CountryCode", "IPTC:Country-PrimaryLocationCode", attrgetter("country_code"),
        marks_existing=False,
    ),
)
LOCATION_TAGS = tuple(tag for field in LOCATION_FIELDS for tag in (field.xmp, field.iim))
NOMOS_TAGS = ("XMP-nomos:RegionID", "XMP-nomos:DatasetRelease", "XMP-nomos:LookupStatus")


def location_tags(location: Location) -> dict[str, str]:
    """The standard XMP location fields for a Location."""
    return {field.xmp: value for field in LOCATION_FIELDS if (value := field.part(location))}


def iptc_tags(location: Location) -> dict[str, str]:
    """The legacy IPTC-IIM location fields for a Location, marked as UTF-8 so accents survive."""
    return {"IPTC:CodedCharacterSet": "UTF8"} | {
        field.iim: value for field in LOCATION_FIELDS if (value := field.part(location))
    }


def nomos_tags(record: PhotoRecord, dataset_release: str) -> dict[str, str]:
    """The Nomos XMP namespace fields (ADR 0001): how this photo's Location was found."""
    return {
        "XMP-nomos:RegionID": record.result.location.region_id or "",  # empty for a Country-only Location
        "XMP-nomos:DatasetRelease": dataset_release,
        "XMP-nomos:LookupStatus": record.result.status.value,
    }


# What tells whether a photo has IPTC-IIM text, and in which character set, without reading
# that text (it may hold the Description): the UTF-8 marker, and the digest ExifTool computes
# over the IIM block when there is one.
IIM_CHARSET_TAGS = ("IPTC:CodedCharacterSet", "File:CurrentIPTCDigest")


def marking_iim_utf8_would_garble(current: dict) -> bool:
    """Whether setting the UTF-8 marker might garble a photo's existing IPTC-IIM text.

    Without the marker, IIM text is read as Latin-1 (or another legacy character set), so any
    non-ASCII text, such as an accented Description, would no longer decode once the marker
    says UTF-8. Nomos never reads the Description to find out, so any existing IIM block
    without the marker counts.
    """
    return "File:CurrentIPTCDigest" in current and current.get("IPTC:CodedCharacterSet") != IIM_UTF8_MARKER


def _current_text(current: dict, tag: str) -> str:
    """A tag's current value in a photo as stripped text ("" when absent).

    ExifTool's -G keys a read by family-0 group (XMP-photoshop:State reads as XMP:State), and
    reads numeric-looking text as a number. IIM pads the country code to 3 bytes ("FR ").
    """
    group, name = tag.split(":")
    value = current.get(f"{group.split('-')[0]}:{name}")
    return "" if value is None else str(value).strip()


def has_location(current: dict) -> bool:
    """Whether a photo already has a Location: a non-empty State or Country in XMP or IPTC-IIM."""
    return any(
        _current_text(current, tag)
        for field in LOCATION_FIELDS
        if field.marks_existing
        for tag in (field.xmp, field.iim)
    )


def written_by_nomos(current: dict) -> bool:
    """Whether a photo's Location is the one Nomos wrote, so --overwrite may replace it.

    The photo must carry the Nomos namespace (ADR 0001; RegionID alone may be empty). Nomos
    writes the same Location into XMP and IIM, so an IIM location field holding a value other
    than its XMP field's means that Location was entered by hand since, and is not replaced.
    """
    tagged = any(_current_text(current, tag) for tag in ("XMP-nomos:DatasetRelease", "XMP-nomos:LookupStatus"))
    return tagged and all(
        _current_text(current, field.iim) in ("", _current_text(current, field.xmp)) for field in LOCATION_FIELDS
    )


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
    if all(_current_text(current, tag) == (tags.get(tag) or "") for tag in LOCATION_TAGS + NOMOS_TAGS):
        return None
    return {tag: None for tag in LOCATION_TAGS} | tags


@dataclass(frozen=True)
class WriteOptions:
    """How `write-tags` writes: its command-line options, and where its warnings go."""

    iptc: bool = False  # also write the legacy IPTC-IIM location fields
    overwrite: bool = False  # replace Locations that Nomos wrote earlier
    in_place: bool = False  # keep no "<photo>_original" backups
    warn: Callable[[str], None] = lambda message: None


def write_tags(
    report: Report,
    options: WriteOptions = WriteOptions(),
    on_outcome: Callable[[PhotoRecord, WriteOutcome], None] = lambda record, outcome: None,
    on_error: Callable[[PhotoRecord, str], None] = lambda record, message: None,
) -> Counter[WriteOutcome]:
    """Write the report's Locations into its photos and count the Write outcomes.

    Each photo's GPS is re-read first: a photo that is missing, or whose coordinates changed
    since the report was made, is skipped as stale.

    A photo that already has a Location is skipped, unless overwrite is set and Nomos wrote that
    Location (see written_by_nomos): then it is replaced. Replacing removes every location field
    the new Location leaves out, in XMP and IIM alike, so a stale Region never survives; without
    iptc, that includes the IIM location fields Nomos wrote.

    ExifTool keeps a "<photo>_original" backup of each written photo, unless in_place is set.

    Each photo's Write outcome is passed to on_outcome as soon as it is known. A photo ExifTool
    fails on gets no Write outcome: why it failed is passed to on_error instead, and the other
    photos are still written.

    With iptc, the legacy IPTC-IIM location fields are written too, except into a photo whose
    existing IIM is not marked as UTF-8: that photo gets its XMP fields only, and a warning.
    """
    outcomes: Counter[WriteOutcome] = Counter()
    with ExifTool() as exiftool:
        for record in report.photos:
            try:
                outcome = _write_photo(exiftool, report, record, options)
            except PhotoError as error:
                on_error(record, str(error))
                continue
            outcomes[outcome] += 1
            on_outcome(record, outcome)
    return outcomes


def _write_photo(exiftool: ExifTool, report: Report, record: PhotoRecord, options: WriteOptions) -> WriteOutcome:
    location = record.result.location
    if record.result.status not in WRITABLE_STATUSES or location is None:
        return WriteOutcome.SKIPPED_UNRESOLVED
    photo = report.photo_path(record)
    if is_stale(exiftool, photo, record):
        return WriteOutcome.SKIPPED_STALE
    current = exiftool.read([photo], LOCATION_TAGS + NOMOS_TAGS + IIM_CHARSET_TAGS).get(photo, {})
    replacing = has_location(current)
    if replacing and not (options.overwrite and written_by_nomos(current)):
        return WriteOutcome.SKIPPED_EXISTING
    tags: dict[str, str | None] = location_tags(location) | nomos_tags(record, report.dataset_release)
    iim_would_garble = options.iptc and marking_iim_utf8_would_garble(current)
    if options.iptc and not iim_would_garble:
        tags |= iptc_tags(location)
    if replacing:
        tags = replacement(current, tags)
        if tags is None:
            return WriteOutcome.SKIPPED_EXISTING
    exiftool.write(photo, tags, keep_backup=not options.in_place)
    if iim_would_garble:
        options.warn(
            f"{record.path}: the existing IPTC-IIM is not marked as UTF-8, so only the XMP fields "
            "were written (marking it as UTF-8 could garble its text)"
        )
    return WriteOutcome.WRITTEN
