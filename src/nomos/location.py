"""The domain types shared by lookup, the report and writing: Locations and Lookup statuses."""

from dataclasses import dataclass
from enum import StrEnum


class LookupStatus(StrEnum):
    """The result of resolving one photo's coordinates to a Location (see GLOSSARY.md)."""

    MATCHED = "matched"
    NEARBY = "nearby"
    COUNTRY_ONLY = "country_only"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"
    NO_GPS = "no_gps"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class Location:
    """The Region and Country a photo was taken in. A Country-only Location has no Region."""

    country: str
    country_code: str | None
    region: str | None = None
    region_id: str | None = None

    @property
    def caption(self) -> str:
        """The Caption a viewer would build: "Region, Country", or "Country" alone."""
        return f"{self.region}, {self.country}" if self.region else self.country


@dataclass(frozen=True)
class LookupResult:
    """What a lookup found: a Lookup status and, where there is one, the Location."""

    status: LookupStatus
    location: Location | None = None
    candidates: tuple[Location, ...] = ()
    distance_m: float | None = None
    reason: str | None = None
