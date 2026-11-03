# Nomos

Nomos tags geotagged photos with the country and region they were taken in, so that a viewer can show where each photo is from without any network access.

## Places

**Country**:
A first-level unit (ADM0) of the boundary dataset, identified by its ISO 3166-1 alpha-2 code.
_Avoid_: nation, state (as a synonym for country)

**Region**:
A first-level administrative subdivision (ADM1) of a Country as the boundary dataset defines it: a région in France, a province or territory in Canada, a state in the United States.
_Avoid_: province, state, area, ADM2 units such as départements

**Disputed area**:
A territory the boundary dataset carves out as disputed rather than assigning to a Country, such as the Falkland Islands or the West Bank. It has a name but no country code.
_Avoid_: territory, contested zone

**Location**:
The Region and Country a photo was taken in, together with the Country code. This is what Nomos writes into a photo.
_Avoid_: place, address, geotag

**Country-only Location**:
A Location with a Country but no Region: the point is in a Country the dataset does not subdivide there, in a Country with no subdivisions at all, or in a Disputed area (which then stands in for the Country).
_Avoid_: partial match

**Region ID**:
The boundary dataset's own identifier for a Region. It is what joins a tagged photo to that Region's shape on a map.
_Avoid_: region code, shape

**Dataset release**:
One pinned, checksummed release of the boundary dataset. Every Location is resolved against exactly one Dataset release.
_Avoid_: data version, map version

**Caption**:
The display string a viewer builds from a Location, in the form "Region, Country" (for example "Auvergne-Rhône-Alpes, France"). Nomos never writes a Caption into a photo.
_Avoid_: label, title

**Description**:
The photographer's own free-text description of a photo. Nomos never reads or changes it.
_Avoid_: caption (even though IPTC calls this field Caption-Abstract)

## Tagging

**Lookup status**:
The result of resolving one photo's coordinates to a Location: matched, nearby match, country only, ambiguous, no match, no GPS, or invalid input.

**Nearby match**:
A Lookup status for a photo that falls just outside every Region, typically on a shoreline, pier or boat, and is assigned to the closest Region within a small tolerance.
_Avoid_: snapped, fuzzy match

**Write outcome**:
What happened when Nomos tried to write a Location into one photo: written, skipped because the photo already has a Location, skipped because the lookup did not produce one, or skipped as stale because the photo is missing or its coordinates changed since the lookup.

**Photo library**:
The folder tree (for example a local folder or an SD card's DCIM tree) whose JPEG photos Nomos processes in one run.
_Avoid_: collection, album
