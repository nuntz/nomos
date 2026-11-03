"""The `nomos` command line: build-index, resolve and write-tags."""

import argparse
import sys
from pathlib import Path

from nomos.errors import NomosError
from nomos.exiftool import find_exiftool


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nomos",
        description="Tag geotagged photos with the Region and Country they were taken in, offline.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    commands.add_parser(
        "build-index",
        help="download and verify the pinned Dataset release, and build the boundary index",
        description="Download and verify the pinned Dataset release, and build the boundary index.",
    )

    resolve = commands.add_parser(
        "resolve",
        help="resolve every JPEG in a Photo library to a Location and write a JSON report",
        description="Resolve every JPEG in a Photo library to a Location and write a JSON report. "
        "No photo is changed.",
    )
    resolve.add_argument("library", type=Path, help="the Photo library folder")
    resolve.add_argument(
        "--report",
        type=Path,
        default=Path("nomos-report.json"),
        help="where to write the report (default: ./nomos-report.json)",
    )

    write_tags = commands.add_parser(
        "write-tags",
        help="write the Locations from a report into the photos' XMP location fields",
        description="Write the Locations from a report into the photos' XMP location fields.",
    )
    write_tags.add_argument("report", type=Path, help="a report written by `nomos resolve`")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        find_exiftool()
        raise NotImplementedError(args.command)
    except NomosError as error:
        print(f"nomos: error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
