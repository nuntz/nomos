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

## Develop

```sh
uv run pytest
```

The test suite needs ExifTool on `PATH`. It runs against a tiny hand-drawn fixture Dataset release
(`tests/fixtures/dataset/`), which the CLI is pointed at through the `NOMOS_MANIFEST` environment
variable, with a temporary `XDG_CACHE_HOME`.
