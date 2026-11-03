"""`nomos write-tags`: write each resolved Location from a report into its photo's XMP fields.

ExifTool rewrites only the metadata; the image data is never re-encoded.
"""

from collections import Counter
from enum import StrEnum

from nomos.exiftool import ExifTool
from nomos.location import Location, LookupStatus
from nomos.report import Report

WRITABLE_STATUSES = {LookupStatus.MATCHED}


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


def write_tags(report: Report, iptc: bool = False) -> Counter[WriteOutcome]:
    """Write the report's Locations into its photos and count the Write outcomes.

    With iptc, the legacy IPTC-IIM location fields are written too.
    """
    outcomes: Counter[WriteOutcome] = Counter()
    with ExifTool() as exiftool:
        for record in report.photos:
            location = record.result.location
            if record.result.status not in WRITABLE_STATUSES or location is None:
                outcomes[WriteOutcome.SKIPPED_UNRESOLVED] += 1
                continue
            tags = location_tags(location)
            if iptc:
                tags |= iptc_tags(location)
            exiftool.write(report.photo_path(record), tags)
            outcomes[WriteOutcome.WRITTEN] += 1
    return outcomes


def summary(outcomes: Counter[WriteOutcome]) -> str:
    """One line with the count of photos per Write outcome."""
    total = sum(outcomes.values())
    noun = "photo" if total == 1 else "photos"
    return f"{total} {noun}: " + ", ".join(f"{outcome} {outcomes[outcome]}" for outcome in WriteOutcome)
