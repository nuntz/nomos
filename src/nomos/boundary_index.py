"""The boundary index: one Dataset release's Regions and Countries, and the lookup on them.

This is a deep module with a small interface: build it from a Dataset release's ADM0 and
ADM1 files (or load a saved one), then call `lookup(lat, lon)`.
"""

import math
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely import STRtree

from nomos.country_codes import alpha2_for
from nomos.errors import NomosError
from nomos.location import Location, LookupResult, LookupStatus

# Bump when the saved index layout changes, so an old cached index is never loaded.
INDEX_FORMAT = 2

# CGAZ v6.0.0 has coordinates at 180.0000000000001 (one ulp beyond the antimeridian) where its
# polygons are split at ±180. Boundary data may stray this far outside the lon/lat range; input
# coordinates may not.
COORDINATE_TOLERANCE = 1e-9


class IndexFormatError(Exception):
    """A saved index was written by an incompatible version of Nomos."""


class BoundaryDataError(NomosError):
    """A boundary file is not usable as a Dataset release layer."""


@dataclass(frozen=True)
class _Unit:
    """One feature of a layer: a Region (ADM1) or a Country (ADM0).

    shape_group is the Country's ISO alpha-3 code, or a non-ISO code for a Disputed area.
    shape_type is ADM1, ADM0 (a whole-country feature) or DISP (a Disputed area).
    """

    name: str
    shape_id: str | None
    shape_group: str
    shape_type: str


class _Layer:
    """One layer's units, with every polygon component indexed on its own, so that a Country made
    of distant islands does not get one huge bounding box."""

    def __init__(self, units: list[_Unit], components: np.ndarray, component_unit: np.ndarray):
        self.units = units
        self.components = components
        self.component_unit = component_unit
        self._tree = STRtree(components)

    @classmethod
    def read(cls, layer: str, path: Path) -> "_Layer":
        import geopandas  # slow to import; only building needs it

        frame = geopandas.read_file(path, engine="pyogrio")
        _check_lon_lat(layer, frame.total_bounds)
        units = [
            _Unit(
                name=row["shapeName"],
                shape_id=row.get("shapeID"),
                shape_group=row["shapeGroup"],
                shape_type=row["shapeType"],
            )
            for row in frame.drop(columns="geometry").to_dict("records")
        ]
        parts, owners = shapely.get_parts(frame.geometry.values, return_index=True)
        return cls(units, parts, owners)

    def covering(self, point: shapely.Point) -> list[_Unit]:
        """The units covering the point, in dataset order. A point on a boundary counts as
        inside. A bounding-box hit alone is never a match."""
        hits = self._tree.query(point, predicate="covered_by")
        return [self.units[i] for i in sorted({int(i) for i in self.component_unit[hits]})]

    def to_state(self) -> dict:
        return {
            "units": self.units,
            "components": shapely.to_wkb(self.components),
            "component_unit": self.component_unit,
        }

    @classmethod
    def from_state(cls, state: dict) -> "_Layer":
        return cls(state["units"], shapely.from_wkb(state["components"]), state["component_unit"])


class BoundaryIndex:
    def __init__(self, countries: _Layer, regions: _Layer):
        self._countries = countries  # ADM0
        self._regions = regions  # ADM1
        # ADM1 has no Country name field, so a Region's Country is named by its ADM0 unit.
        self._country_names = {unit.shape_group: unit.name for unit in countries.units}

    @classmethod
    def build(cls, adm0: Path, adm1: Path) -> "BoundaryIndex":
        """Build the index from a Dataset release's ADM0 and ADM1 GeoJSON files."""
        return cls(_Layer.read("ADM0", adm0), _Layer.read("ADM1", adm1))

    def save(self, path: Path) -> None:
        state = {
            "format": INDEX_FORMAT,
            "countries": self._countries.to_state(),
            "regions": self._regions.to_state(),
        }
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "BoundaryIndex":
        state = pickle.loads(path.read_bytes())
        if not isinstance(state, dict) or state.get("format") != INDEX_FORMAT:
            raise IndexFormatError(f"{path} was built by an incompatible version of Nomos")
        return cls(_Layer.from_state(state["countries"]), _Layer.from_state(state["regions"]))

    def lookup(self, lat: float, lon: float) -> LookupResult:
        """Resolve a coordinate to a Lookup status and, where there is one, a Location.

        The numbered steps are the lookup order of the spec (#1, "Boundary index and lookup").
        """
        # 1. Coordinates that make no sense are invalid input.
        if (reason := _invalid_input_reason(lat, lon)) is not None:
            return LookupResult(LookupStatus.INVALID_INPUT, reason=reason)
        # 2. Exact matches in both layers.
        point = shapely.Point(lon, lat)
        regions = self._regions.covering(point)
        countries = self._countries.covering(point)
        # 3 and 4. A point in at least one Region is matched or ambiguous.
        if regions:
            return self._resolve_regions(regions, countries)
        # 5 (a Nearby match) and 6 (a Country-only Location) are tried here, before no match.
        return LookupResult(LookupStatus.NO_MATCH)

    def _resolve_regions(self, regions: list[_Unit], countries: list[_Unit]) -> LookupResult:
        """Matched when exactly one Region covers the point and its Country is a containing
        Country (or no Country contains it). Otherwise ambiguous, listing every Region and every
        containing Country that none of those Regions belongs to."""
        containing = {country.shape_group for country in countries}
        if len(regions) == 1 and (not containing or regions[0].shape_group in containing):
            return LookupResult(LookupStatus.MATCHED, self._region_location(regions[0]))
        region_countries = {region.shape_group for region in regions}
        candidates = [self._region_location(region) for region in regions] + [
            self._country_location(country) for country in countries if country.shape_group not in region_countries
        ]
        return LookupResult(LookupStatus.AMBIGUOUS, candidates=tuple(candidates))

    def _region_location(self, region: _Unit) -> Location:
        return Location(
            country=self._country_names.get(region.shape_group, region.shape_group),
            country_code=alpha2_for(region.shape_group),
            region=region.name,
            region_id=region.shape_id,
        )

    def _country_location(self, country: _Unit) -> Location:
        """The Country-only Location of an ADM0 unit. A Disputed area has no country code."""
        code = None if country.shape_type == "DISP" else alpha2_for(country.shape_group)
        return Location(country=country.name, country_code=code)


def _invalid_input_reason(lat: float, lon: float) -> str | None:
    """Why a coordinate makes no sense, or None if it is finite and in range."""
    for name, value, limit in (("latitude", lat, 90), ("longitude", lon, 180)):
        if not math.isfinite(value):
            return f"{name} {value!r} is not a finite number"
        if not -limit <= value <= limit:
            return f"{name} {value!r} is outside [-{limit}, {limit}]"
    return None


def _check_lon_lat(layer: str, bounds) -> None:
    min_lon, min_lat, max_lon, max_lat = (float(b) for b in bounds)
    limit_lon, limit_lat = 180 + COORDINATE_TOLERANCE, 90 + COORDINATE_TOLERANCE
    if not (-limit_lon <= min_lon and max_lon <= limit_lon and -limit_lat <= min_lat and max_lat <= limit_lat):
        raise BoundaryDataError(
            f"{layer} boundary data is not in longitude and latitude degrees: its bounds are "
            f"lon [{min_lon!r}, {max_lon!r}], lat [{min_lat!r}, {max_lat!r}]"
        )
