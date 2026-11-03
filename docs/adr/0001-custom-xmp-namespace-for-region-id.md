# Custom XMP namespace for Region ID and provenance

Nomos writes the standard location fields (XMP-photoshop:State, XMP-photoshop:Country, XMP-iptcCore:CountryCode) and also a small custom XMP namespace that holds the Region ID, the Dataset release and the Lookup status. The viewer needs a stable key to join a photo to its Region's shape on the map, and no standard field carries one. We rejected joining on country code plus region name, because names can change between Dataset releases and are not guaranteed unique. We also rejected having the viewer read the JSON report, because the viewer should depend only on the photo file.

The namespace URI is `https://github.com/nuntz/nomos/ns/xmp/1.0/` with prefix `nomos`, and it holds `RegionID` (empty for a Country-only Location), `DatasetRelease` and `LookupStatus` (`matched`, `nearby` or `country_only`).

## Consequences

- Nomos can recognise the Locations it wrote. `--overwrite` replaces only those, and never a Location entered by hand.
- Software that does not know the namespace (Lightroom, digiKam) ignores it.
- The Region IDs written into the Photo library tie it to the boundary dataset's identifier scheme. Changing datasets means re-tagging.
