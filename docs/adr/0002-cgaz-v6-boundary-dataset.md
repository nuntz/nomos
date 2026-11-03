# geoBoundaries CGAZ v6.0.0 as the boundary dataset

Nomos resolves Locations against the geoBoundaries CGAZ ADM0 and ADM1 layers (CC BY 4.0), pinned to release v6.0.0 by commit hash, with each file's SHA-256 taken from its Git LFS pointer at that commit. CGAZ is a single harmonised global layer with better ADM1 coverage than Natural Earth 10m Admin 1. Its disputed areas follow US Department of State definitions, which we accept as the boundary policy for a personal Photo library. The choice is hard to reverse because Region IDs written into photos (ADR 0001) are CGAZ shapeIDs.

## Considered Options

- **Natural Earth 10m Admin 1** (public domain, about 25 MB). Smaller and simpler to license, but the project itself flags missing subdivisions and stale units in some countries. It is the fallback if CGAZ ever becomes impractical.
- **geoBoundaries `main` branch.** It has a newer ADM1 file, but it is not a tagged release and can change under us.

## Consequences

- CGAZ ADM1 is not fully nested in ADM0. Some land has a Country but no Region (French Guiana, Svalbard, inland water), and a small share of points get different countries from the two layers. Nomos handles these as country-only Locations and ambiguous lookups respectively.
- Simplified coastlines drop small islets and inlets, which is why Nomos has Nearby matches.
- Country codes in the dataset are ISO alpha-3, and disputed areas carry non-ISO codes. Nomos maps alpha-3 to alpha-2 and writes no code for disputed areas.
