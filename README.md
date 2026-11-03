# nomos

An offline photo Location tagger. Nomos reads the GPS coordinates of the JPEGs in a Photo library,
resolves each one to a Region and Country against a pinned boundary Dataset release, and writes the
Location into the photos' standard XMP location fields. See `GLOSSARY.md` for the domain language.

## Install

Nomos needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and [ExifTool](https://exiftool.org/).

```sh
uv tool install .
```

## Use

```sh
nomos build-index              # download and verify the Dataset release once, build the index
nomos resolve ~/Photos         # write nomos-report.json for review; changes no photo
nomos write-tags nomos-report.json
```

`resolve` processes every JPEG (`.jpg` or `.jpeg`, in any letter case) in the Photo library and
all its subfolders. It skips hidden files and hidden folders, whose names start with `.`: this
keeps macOS `._` resource files and the `.Trashes` and `.Spotlight-V100` folders on SD cards out
of the report. It never follows symlinks, so a link cannot add photos from outside the library.

`build-index` downloads geoBoundaries CGAZ v6.0.0 (about 760 MB), pinned by commit hash and
checked against the SHA-256 checksums in `src/nomos/data/manifest.json`. The files and the index
live in `$XDG_CACHE_HOME/nomos/v6.0.0/` (by default `~/.cache/nomos/v6.0.0/`). Re-running it
verifies the existing download instead of fetching it again, and the index is rebuilt whenever the
manifest changes.

## Develop

```sh
uv run pytest              # the fixture suite
uv run pytest -m golden    # the golden suite, against the real Dataset release
```

The test suites need ExifTool on `PATH`.

- The **fixture suite** runs against a tiny hand-drawn fixture Dataset release
  (`tests/fixtures/dataset/`), which the CLI is pointed at through the `NOMOS_MANIFEST` environment
  variable, with a temporary `XDG_CACHE_HOME`. It runs in CI on every push.
- The **golden suite** (`tests/test_golden.py`) checks real coordinates against geoBoundaries
  CGAZ v6.0.0. It runs `nomos build-index` in the normal Nomos cache, so the first run downloads
  the data and later runs reuse it. To use files you already have, copy them into
  `$XDG_CACHE_HOME/nomos/v6.0.0/` first. It runs in CI weekly, on demand and when the manifest
  changes (`.github/workflows/golden.yml`).

To move to a new Dataset release, change the release, commit, URLs, sizes and checksums in the
manifest, and re-run the golden suite.

## Boundary data

Boundary data from geoBoundaries (www.geoboundaries.org), CC BY 4.0. Nomos does not ship the data;
`build-index` downloads it. See `NOTICE` for the full attribution.
