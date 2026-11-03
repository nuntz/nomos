"""Seam 2: the `nomos` CLI, end to end, with real ExifTool on generated JPEGs."""


def test_help_lists_the_three_commands(nomos):
    result = nomos("--help")

    for command in ("build-index", "resolve", "write-tags"):
        assert command in result.stdout


def test_exits_with_a_clear_error_when_exiftool_is_not_installed(nomos, tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    nomos.env["PATH"] = str(empty_bin)

    result = nomos("build-index", check=False)

    assert result.returncode != 0
    assert "ExifTool" in result.stderr
    assert "not found" in result.stderr
    assert "Traceback" not in result.stderr
