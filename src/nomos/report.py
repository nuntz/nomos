"""The JSON report `resolve` writes and `write-tags` reads.

The report records the absolute Photo library root and the Dataset release, and one record per
photo with its path relative to the root, so `write-tags` can find the photos from the report alone.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from nomos.errors import NomosError
from nomos.location import Location, LookupResult, LookupStatus

DEFAULT_REPORT = Path("nomos-report.json")


class ReportError(NomosError):
    pass


@dataclass(frozen=True)
class PhotoRecord:
    path: str  # relative to the library root, with "/" separators
    latitude: float | None
    longitude: float | None
    result: LookupResult

    def to_json(self) -> dict:
        record = {
            "path": self.path,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "lookup_status": self.result.status.value,
        }
        if (location := self.result.location) is not None:
            record |= _location_to_json(location)
        if self.result.candidates:
            record["candidates"] = [_location_to_json(candidate) for candidate in self.result.candidates]
        if self.result.reason is not None:
            record["reason"] = self.result.reason
        return record

    @classmethod
    def from_json(cls, record: dict) -> "PhotoRecord":
        result = LookupResult(
            status=LookupStatus(record["lookup_status"]),
            location=_location_from_json(record) if "country" in record else None,
            candidates=tuple(_location_from_json(candidate) for candidate in record.get("candidates", ())),
            reason=record.get("reason"),
        )
        return cls(record["path"], record.get("latitude"), record.get("longitude"), result)


def _location_to_json(location: Location) -> dict:
    return {
        "country_code": location.country_code,
        "country": location.country,
        "region_id": location.region_id,
        "region": location.region,
        "caption": location.caption,
    }


def _location_from_json(data: dict) -> Location:
    return Location(
        country=data["country"],
        country_code=data.get("country_code"),
        region=data.get("region"),
        region_id=data.get("region_id"),
    )


@dataclass(frozen=True)
class Report:
    library_root: Path
    dataset_release: str
    photos: list[PhotoRecord]

    def photo_path(self, record: PhotoRecord) -> Path:
        return self.library_root / record.path

    def summary(self) -> str:
        """One line with the count of photos per Lookup status."""
        counts = Counter(record.result.status for record in self.photos)
        noun = "photo" if len(self.photos) == 1 else "photos"
        return f"{len(self.photos)} {noun}: " + ", ".join(f"{status} {counts[status]}" for status in LookupStatus)

    def save(self, path: Path) -> None:
        data = {
            "library_root": str(self.library_root),
            "dataset_release": self.dataset_release,
            "photos": [record.to_json() for record in self.photos],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as error:
            raise ReportError(f"cannot write report {path}: {error}")

    @classmethod
    def load(cls, path: Path) -> "Report":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                library_root=Path(data["library_root"]),
                dataset_release=data["dataset_release"],
                photos=[PhotoRecord.from_json(record) for record in data["photos"]],
            )
        except OSError as error:
            raise ReportError(f"cannot read report {path}: {error}")
        except (ValueError, KeyError, TypeError) as error:
            raise ReportError(f"{path} is not a Nomos report: {error}")
