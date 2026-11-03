"""`nomos write-tags`: write each resolved Location from a report into its photo's XMP fields.

ExifTool rewrites only the metadata; the image data is never re-encoded.
"""

from collections import Counter
from collections.abc import Callable
from enum import StrEnum

from nomos.exiftool import ExifTool
from nomos.location import Location, LookupStatus
from nomos.report import PhotoRecord, Report

WRITABLE_STATUSES = {LookupStatus.MATCHED}
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
        "XMP-nomos:RegionID": record.result.location.region_id,
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


# The fields that make up an existing Location, in XMP and IPTC-IIM, as ExifTool's -G keys them.
_EXISTING_LOCATION_FIELDS = ("XMP:State", "XMP:Country", "IPTC:Province-State", "IPTC:Country-PrimaryLocationName")
_EXISTING_LOCATION_TAGS = (
    "XMP-photoshop:State",
    "XMP-photoshop:Country",
    "IPTC:Province-State",
    "IPTC:Country-PrimaryLocationName",
)


def _text(value) -> str:
    """A tag value as stripped text; ExifTool reads numeric-looking text as a number."""
    return "" if value is None else str(value).strip()


def has_location(current: dict) -> bool:
    """Whether a photo already has a Location: a non-empty State or Country in XMP or IPTC-IIM."""
    return any(_text(current.get(field)) for field in _EXISTING_LOCATION_FIELDS)


def write_tags(
    report: Report,
    iptc: bool = False,
    warn: Callable[[str], None] = lambda message: None,
    on_outcome: Callable[[PhotoRecord, WriteOutcome], None] = lambda record, outcome: None,
) -> Counter[WriteOutcome]:
    """Write the report's Locations into its photos and count the Write outcomes.

    Each photo's Write outcome is passed to on_outcome as soon as it is known.

    With iptc, the legacy IPTC-IIM location fields are written too, except into a photo whose
    existing IIM text is not UTF-8: that photo gets its XMP fields only, and a warning.
    """
    outcomes: Counter[WriteOutcome] = Counter()
    with ExifTool() as exiftool:
        for record in report.photos:
            outcome = _write_photo(exiftool, report, record, iptc, warn)
            outcomes[outcome] += 1
            on_outcome(record, outcome)
    return outcomes


def _write_photo(
    exiftool: ExifTool, report: Report, record: PhotoRecord, iptc: bool, warn: Callable[[str], None]
) -> WriteOutcome:
    location = record.result.location
    if record.result.status not in WRITABLE_STATUSES or location is None:
        return WriteOutcome.SKIPPED_UNRESOLVED
    photo = report.photo_path(record)
    current = exiftool.read([photo], _EXISTING_LOCATION_TAGS).get(photo, {})
    if has_location(current):
        return WriteOutcome.SKIPPED_EXISTING
    tags = location_tags(location) | nomos_tags(record, report.dataset_release)
    if iptc:
        if marking_iim_utf8_would_garble(exiftool.read([photo], ["IPTC:all"]).get(photo, {})):
            warn(
                f"{record.path}: existing IPTC-IIM text is not UTF-8, so only the XMP fields "
                "were written (writing UTF-8 IIM would garble it)"
            )
        else:
            tags |= iptc_tags(location)
    exiftool.write(photo, tags)
    return WriteOutcome.WRITTEN


def summary(outcomes: Counter[WriteOutcome]) -> str:
    """One line with the count of photos per Write outcome."""
    total = sum(outcomes.values())
    noun = "photo" if total == 1 else "photos"
    return f"{total} {noun}: " + ", ".join(f"{outcome} {outcomes[outcome]}" for outcome in WriteOutcome)
