"""The ExifTool wrapper: one long-running ExifTool process (stay-open mode) per Nomos run."""

import json
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from importlib import resources
from pathlib import Path

from nomos.errors import NomosError


# Defines the Nomos XMP namespace (ADR 0001), so that XMP-nomos tags can be written.
NOMOS_CONFIG = Path(str(resources.files("nomos").joinpath("data/nomos.ExifTool_config")))


class ExifToolNotFound(NomosError):
    pass


class ExifToolError(NomosError):
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


class ExifTool:
    """A running ExifTool process. Use as a context manager.

    Each command is sent as an argument list over stdin, so no process is started per photo.
    The process loads the Nomos namespace config, so every command can write XMP-nomos tags.
    """

    def __init__(self) -> None:
        self._executable = find_exiftool()
        self._process: subprocess.Popen | None = None
        self._sequence = 0

    def __enter__(self) -> "ExifTool":
        self._process = subprocess.Popen(
            # -config is only honoured as the very first argument.
            [self._executable, "-config", NOMOS_CONFIG, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return self

    def __exit__(self, *exc_info) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            process.stdin.write(b"-stay_open\nFalse\n")
            process.stdin.close()
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()

    def execute(self, *args: str | Path) -> tuple[str, str]:
        """Run one ExifTool command and return its (stdout, stderr)."""
        if self._process is None:
            raise RuntimeError("ExifTool is not running; use it as a context manager")
        self._sequence += 1
        ready = f"{{ready{self._sequence}}}"
        lines = [str(arg) for arg in args]
        if any("\n" in line for line in lines):
            raise ValueError("ExifTool arguments cannot contain newlines")
        # -echo4 prints the marker on stderr once the command is done, so both streams can be read to it.
        lines += ["-echo4", ready, f"-execute{self._sequence}"]
        self._process.stdin.write(("\n".join(lines) + "\n").encode("utf-8"))
        self._process.stdin.flush()
        return self._read_until(self._process.stdout, ready), self._read_until(self._process.stderr, ready)

    def read(self, photos: Sequence[Path], tags: Iterable[str]) -> dict[Path, dict]:
        """Read tags from photos as numbers (-n), keyed by "Group:Tag" (-G). Unreadable photos are left out."""
        if not photos:
            return {}
        stdout, _ = self.execute("-json", "-G", "-n", *(f"-{tag}" for tag in tags), *photos)
        by_name = {str(photo): photo for photo in photos}
        records = json.loads(stdout) if stdout.strip() else []
        return {by_name[record.pop("SourceFile")]: record for record in records}

    def write(self, photo: Path, values: Mapping[str, str | None], keep_backup: bool = True) -> None:
        """Write tag values into a photo. Fails unless ExifTool reports the photo updated or unchanged.

        A value of None deletes the tag; an empty string writes the tag with an empty value.
        With keep_backup, ExifTool keeps the original file as "<photo>_original"; it never replaces
        an existing backup, so that always holds the photo as it was before the first write.
        """
        options = [] if keep_backup else ["-overwrite_original"]
        assignments = (_assignment(tag, value) for tag, value in values.items())
        stdout, stderr = self.execute(*options, *assignments, photo)
        if "Error" in stderr or ("1 image files updated" not in stdout and "1 image files unchanged" not in stdout):
            raise ExifToolError(f"ExifTool could not write {photo}: {(stderr or stdout).strip()}")

    @staticmethod
    def _read_until(stream, marker: str) -> str:
        lines = []
        while True:
            raw = stream.readline()
            if not raw:
                raise ExifToolError("ExifTool exited unexpectedly")
            line = raw.decode("utf-8", errors="replace")
            if line.rstrip("\r\n") == marker:
                return "".join(lines)
            lines.append(line)


def _assignment(tag: str, value: str | None) -> str:
    if value is None:
        return f"-{tag}="  # deletes the tag
    if value == "":
        return f"-{tag}^="  # "-TAG=" would delete it instead
    return f"-{tag}={value}"
