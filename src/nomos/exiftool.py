"""The ExifTool wrapper: one long-running ExifTool process (stay-open mode) per Nomos run."""

import shutil

from nomos.errors import NomosError


class ExifToolNotFound(NomosError):
    pass


def find_exiftool() -> str:
    """Return the path of the ExifTool executable, or fail with a clear message."""
    path = shutil.which("exiftool")
    if path is None:
        raise ExifToolNotFound(
            "ExifTool not found on PATH. Nomos needs it to read and write photo metadata; "
            "install it from https://exiftool.org/ (or your package manager) and try again."
        )
    return path
