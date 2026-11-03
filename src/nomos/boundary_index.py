"""The boundary index: one Dataset release's Regions and Countries, and the lookup on them.

This is a deep module with a small interface: build it from a Dataset release's ADM0 and
ADM1 files (or load a saved one), then call `lookup(lat, lon)`.
"""

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely import STRtree

from nomos.country_codes import alpha2_for
from nomos.location import Location, LookupResult, LookupStatus

# Bump when the saved index layout changes, so an old cached index is never loaded.
INDEX_FORMAT = 1


class IndexFormatError(Exception):
    """A saved index was written by an incompatible version of Nomos."""


@dataclass(frozen=True)
class _Region:
    name: str
    shape_id: str
    shape_group: str
    shape_type: str


class BoundaryIndex:
    def __init__(
        self,
        regions: list[_Region],
        components: np.ndarray,
        component_region: np.ndarray,
        country_names: dict[str, str],
    ):
        self._regions = regions
        # Every polygon component is indexed on its own, so a Country made of distant
        # islands does not get one huge bounding box.
        self._components = components
        self._component_region = component_region
        self._country_names = country_names
        self._tree = STRtree(components)

    @classmethod
    def build(cls, adm0: Path, adm1: Path) -> "BoundaryIndex":
        """Build the index from a Dataset release's ADM0 and ADM1 GeoJSON files."""
        import geopandas  # slow to import; only building needs it

        countries = geopandas.read_file(adm0, engine="pyogrio")
        country_names = dict(zip(countries["shapeGroup"], countries["shapeName"]))

        units = geopandas.read_file(adm1, engine="pyogrio")
        regions = [
            _Region(name=r.shapeName, shape_id=r.shapeID, shape_group=r.shapeGroup, shape_type=r.shapeType)
            for r in units.itertuples()
        ]
        parts, owners = shapely.get_parts(units.geometry.values, return_index=True)
        return cls(regions, parts, owners, country_names)

    def save(self, path: Path) -> None:
        state = {
            "format": INDEX_FORMAT,
            "regions": self._regions,
            "components": shapely.to_wkb(self._components),
            "component_region": self._component_region,
            "country_names": self._country_names,
        }
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "BoundaryIndex":
        state = pickle.loads(path.read_bytes())
        if not isinstance(state, dict) or state.get("format") != INDEX_FORMAT:
            raise IndexFormatError(f"{path} was built by an incompatible version of Nomos")
        return cls(
            state["regions"],
            shapely.from_wkb(state["components"]),
            state["component_region"],
            state["country_names"],
        )

    def lookup(self, lat: float, lon: float) -> LookupResult:
        """Resolve a coordinate to a Lookup status and, where there is one, a Location."""
        point = shapely.Point(lon, lat)
        # covered_by: a point on a boundary counts as inside. A bounding-box hit alone is never a match.
        hits = self._tree.query(point, predicate="covered_by")
        matched = sorted({int(i) for i in self._component_region[hits]})
        if len(matched) == 1:
            return LookupResult(LookupStatus.MATCHED, self._location(self._regions[matched[0]]))
        return LookupResult(LookupStatus.NO_MATCH)

    def _location(self, region: _Region) -> Location:
        return Location(
            country=self._country_names.get(region.shape_group, region.shape_group),
            country_code=alpha2_for(region.shape_group),
            region=region.name,
            region_id=region.shape_id,
        )
