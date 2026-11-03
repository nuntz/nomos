"""The boundary index: one Dataset release's Regions and Countries, and the lookup on them.

This is a deep module with a small interface: build it from a Dataset release's ADM0 and
ADM1 files (or load a saved one), then call `lookup(lat, lon)`.
"""

import math
import pickle
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import shapely
from pyproj import CRS, Transformer
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

# A point outside every Region is a Nearby match to the nearest Region this close, in metres.
NEARBY_RADIUS_M = 5000.0


class IndexFormatError(Exception):
    """A saved index was written by an incompatible version of Nomos."""


class BoundaryDataError(NomosError):
    """A boundary file is not usable as a Dataset release layer."""


class ShapeType(StrEnum):
    """The kind of a boundary feature, as the dataset's shapeType field names it."""

    REGION = "ADM1"
    COUNTRY = "ADM0"  # in ADM1, a whole-country feature such as Vatican City
    DISPUTED = "DISP"  # a Disputed area


@dataclass(frozen=True)
class _Unit:
    """One feature of a layer: a Region (ADM1) or a Country (ADM0).

    shape_group is the Country's ISO alpha-3 code, or a non-ISO code for a Disputed area.
    shape_type is the dataset's shapeType, compared with ShapeType: ADM1, ADM0 (a whole-country
    feature) or DISP (a Disputed area).
    """

    name: str
    shape_id: str | None
    shape_group: str
    shape_type: str

    @property
    def is_country(self) -> bool:
        """Whether the unit stands for a Country rather than a Region: an ADM0 unit, or in ADM1 a
        whole-country feature (such as Vatican City) or a Disputed area."""
        return self.shape_type != ShapeType.REGION


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

    def within(self, lat: float, lon: float, radius_m: float) -> list[tuple[float, _Unit]]:
        """The units within radius_m of the point, measured geodesically, nearest first, each
        with its distance in metres. Every component in the search window is measured, since the
        nearest component in degrees is not always the nearest one on the ground."""
        windows = _search_windows(lat, lon, radius_m)
        hits = np.unique(np.concatenate([self._tree.query(window, predicate="intersects") for window in windows]))
        if hits.size == 0:
            return []
        to_metres = _azimuthal_equidistant(lat, lon)
        distances = np.full(hits.size, np.inf)
        for window in windows:
            # Clip to the window so that only the part near the point is projected, and densify
            # so that edges stay true once projected.
            near = shapely.segmentize(shapely.clip_by_rect(self.components[hits], *window.bounds), 0.01)
            projected = shapely.transform(near, lambda xy: np.column_stack(to_metres.transform(xy[:, 0], xy[:, 1])))
            distances = np.fmin(distances, shapely.distance(projected, _ORIGIN))
        nearest: dict[int, float] = {}
        for unit, distance in zip(self.component_unit[hits], distances):
            if distance <= radius_m and distance < nearest.get(int(unit), np.inf):
                nearest[int(unit)] = float(distance)
        return sorted(((distance, self.units[unit]) for unit, distance in nearest.items()), key=lambda hit: hit[0])

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
        # ADM1 has no Country name field, so a Region's Country is named by its ADM0 unit. A
        # Disputed area may share a Country's shapeGroup; the Country's own unit names it.
        self._country_names: dict[str, str] = {}
        for unit in sorted(countries.units, key=lambda unit: unit.shape_type == ShapeType.DISPUTED):
            self._country_names.setdefault(unit.shape_group, unit.name)

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
        # 5. Otherwise, the nearest Region within 5 km is a Nearby match.
        if (nearby := self._nearby(lat, lon, countries)) is not None:
            return nearby
        # 6. A point in a Country but in no Region gets a Country-only Location.
        if countries:
            return self._resolve_countries(countries)
        return LookupResult(LookupStatus.NO_MATCH)

    def _nearby(self, lat: float, lon: float, countries: list[_Unit]) -> LookupResult | None:
        """The nearest Region within 5 km, as a Nearby match. A point inside a Country only
        matches that Country's Regions, so that a lake-shore photo isn't assigned across a border."""
        containing = {country.shape_group for country in countries}
        for distance, region in self._regions.within(lat, lon, NEARBY_RADIUS_M):
            if containing and region.shape_group not in containing:
                continue
            if region.is_country:
                # Near a whole-country feature or a Disputed area, the point gets that Country.
                return LookupResult(LookupStatus.COUNTRY_ONLY, self._region_location(region))
            return LookupResult(LookupStatus.NEARBY, self._region_location(region), distance_m=distance)
        return None

    def _resolve_regions(self, regions: list[_Unit], countries: list[_Unit]) -> LookupResult:
        """Matched when exactly one Region covers the point and its Country is a containing
        Country (or no Country contains it); country only instead when that ADM1 feature is a
        whole Country or a Disputed area. Otherwise ambiguous, listing every Region and every
        containing Country that none of those Regions belongs to."""
        containing = {country.shape_group for country in countries}
        if len(regions) == 1 and (not containing or regions[0].shape_group in containing):
            status = LookupStatus.COUNTRY_ONLY if regions[0].is_country else LookupStatus.MATCHED
            return LookupResult(status, self._region_location(regions[0]))
        region_countries = {region.shape_group for region in regions}
        candidates = [self._region_location(region) for region in regions] + [
            self._country_location(country) for country in countries if country.shape_group not in region_countries
        ]
        return LookupResult(LookupStatus.AMBIGUOUS, candidates=tuple(candidates))

    def _resolve_countries(self, countries: list[_Unit]) -> LookupResult:
        """Country only when exactly one Country contains the point. A point on a border between
        Countries, in no Region, is ambiguous between them."""
        if len(countries) == 1:
            return LookupResult(LookupStatus.COUNTRY_ONLY, self._country_location(countries[0]))
        return LookupResult(
            LookupStatus.AMBIGUOUS, candidates=tuple(self._country_location(country) for country in countries)
        )

    def _region_location(self, region: _Unit) -> Location:
        """The Location of an ADM1 feature. A whole-country or Disputed-area feature gives a
        Country-only Location, never "Vatican City, Vatican City"."""
        if region.is_country:
            return self._country_location(region)
        return Location(
            country=self._country_names.get(region.shape_group, region.shape_group),
            country_code=alpha2_for(region.shape_group),
            region=region.name,
            region_id=region.shape_id,
        )

    def _country_location(self, country: _Unit) -> Location:
        """The Country-only Location of a unit that stands for a Country, under the dataset's name
        for it. A Disputed area has no country code, even when its shapeGroup is an ISO code."""
        code = None if country.shape_type == ShapeType.DISPUTED else alpha2_for(country.shape_group)
        return Location(country=country.name, country_code=code)


def _invalid_input_reason(lat: float, lon: float) -> str | None:
    """Why a coordinate makes no sense, or None if it is finite and in range."""
    for name, value, limit in (("latitude", lat, 90), ("longitude", lon, 180)):
        if not math.isfinite(value):
            return f"{name} {value!r} is not a finite number"
        if not -limit <= value <= limit:
            return f"{name} {value!r} is outside [-{limit}, {limit}]"
    return None


# Below the Earth's smallest radius of curvature (6,335 km, north-south at the equator), so that a
# search window made with it is never too small.
_SEARCH_EARTH_RADIUS_M = 6_300_000.0
_LON_LAT = CRS.from_epsg(4326)
_ORIGIN = shapely.Point(0, 0)


def _search_windows(lat: float, lon: float, radius_m: float) -> list[shapely.Polygon]:
    """Longitude and latitude boxes that together hold every point within radius_m of the point.
    A window that crosses ±180 is split in two, and one that reaches a pole spans every longitude."""
    angle = radius_m / _SEARCH_EARTH_RADIUS_M  # radians of arc
    south, north = max(lat - math.degrees(angle), -90.0), min(lat + math.degrees(angle), 90.0)
    reach = math.sin(angle) / math.cos(math.radians(lat))
    if south == -90.0 or north == 90.0 or reach >= 1:
        return [shapely.box(-180.0, south, 180.0, north)]
    dlon = math.degrees(math.asin(reach))
    west, east = lon - dlon, lon + dlon
    windows = [shapely.box(max(west, -180.0), south, min(east, 180.0), north)]
    if east > 180:
        windows.append(shapely.box(-180.0, south, east - 360, north))
    if west < -180:
        windows.append(shapely.box(west + 360, south, 180.0, north))
    return windows


def _azimuthal_equidistant(lat: float, lon: float) -> Transformer:
    """A projection in metres centred on the point, in which the distance from the centre to any
    point is its geodesic distance."""
    centred = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    return Transformer.from_crs(_LON_LAT, centred, always_xy=True)


def _check_lon_lat(layer: str, bounds) -> None:
    min_lon, min_lat, max_lon, max_lat = (float(b) for b in bounds)
    limit_lon, limit_lat = 180 + COORDINATE_TOLERANCE, 90 + COORDINATE_TOLERANCE
    if not (-limit_lon <= min_lon and max_lon <= limit_lon and -limit_lat <= min_lat and max_lat <= limit_lat):
        raise BoundaryDataError(
            f"{layer} boundary data is not in longitude and latitude degrees: its bounds are "
            f"lon [{min_lon!r}, {max_lon!r}], lat [{min_lat!r}, {max_lat!r}]"
        )
