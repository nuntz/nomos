"""The `nomos` command line: build-index, resolve and write-tags."""

import argparse
import sys
from pathlib import Path

from nomos.dataset import Manifest, build_index, load_index
from nomos.errors import NomosError
from nomos.exiftool import find_exiftool
from nomos.report import DEFAULT_REPORT, Report
from nomos.resolve import resolve_library
from nomos.write import summary as write_summary
from nomos.write import write_tags


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
        default=DEFAULT_REPORT,
        help="where to write the report (default: ./nomos-report.json)",
    )

    write_tags = commands.add_parser(
        "write-tags",
        help="write the Locations from a report into the photos' XMP location fields",
        description="Write the Locations from a report into the photos' XMP location fields.",
    )
    write_tags.add_argument("report", type=Path, help="a report written by `nomos resolve`")
    write_tags.add_argument(
        "--iptc",
        action="store_true",
        help="also write the legacy IPTC-IIM location fields, in UTF-8, for older software",
    )
    return parser


def _warn(message: str) -> None:
    print(f"nomos: warning: {message}", file=sys.stderr)


def _build_index(args: argparse.Namespace) -> int:
    manifest = Manifest.load()
    index_path = build_index(manifest)
    print(f"Boundary index for Dataset release {manifest.release} written to {index_path}")
    return 0


def _resolve(args: argparse.Namespace) -> int:
    manifest = Manifest.load()
    index = load_index(manifest)
    report = resolve_library(args.library, index, manifest.release)
    report.save(args.report)
    print(f"Report written to {args.report}")
    print(report.summary())
    return 0


def _write_tags(args: argparse.Namespace) -> int:
    outcomes = write_tags(
        Report.load(args.report),
        iptc=args.iptc,
        warn=_warn,
        on_outcome=lambda record, outcome: print(f"{outcome} {record.path}", flush=True),
    )
    print(write_summary(outcomes))
    return 0


_COMMANDS = {"build-index": _build_index, "resolve": _resolve, "write-tags": _write_tags}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        find_exiftool()
        return _COMMANDS[args.command](args)
    except NomosError as error:
        print(f"nomos: error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
