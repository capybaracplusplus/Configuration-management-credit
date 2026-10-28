"""Verify generated ZIP structure, binary content, and reproducibility."""

import stat
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.generate_fixtures import generate, member_path

MANIFEST_DIRECTORY = Path(__file__).resolve().parents[2] / "fixtures"


def test_minimal_archive_is_empty(tmp_path):
    """The smallest valid source needs no explicit root ZIP entry."""
    target = tmp_path / "minimal.zip"
    generate(MANIFEST_DIRECTORY / "minimal.json", target)
    with ZipFile(target) as archive:
        assert archive.namelist() == []


def test_multiple_files_preserve_text_binary_and_permissions(tmp_path):
    """The generated fixture carries exact contents and POSIX metadata."""
    target = tmp_path / "multiple.zip"
    generate(MANIFEST_DIRECTORY / "multiple.json", target, "/home/student")
    with ZipFile(target) as archive:
        assert archive.read("assets/payload.bin") == bytes(
            [0, 255, 128, 1, 2, 3, 10],
        )
        assert archive.read("docs/repeated.txt") == (
            b"alpha\nalpha\nbeta\nbeta\ngamma\nalpha\n"
        )
        assert "пробелами" in archive.read("docs/read me.txt").decode()
        assert "Привет" in archive.read("docs/привет.txt").decode()
        file_mode = archive.getinfo(".hidden").external_attr >> 16
        directory_mode = archive.getinfo("empty/").external_attr >> 16
        assert file_mode == stat.S_IFREG | 0o600
        assert directory_mode == stat.S_IFDIR | 0o755
        assert archive.getinfo("empty/").is_dir()


def test_deep_archive_has_nested_files_and_virtual_home(tmp_path):
    """Home is a name in the ZIP; no host contents are copied into it."""
    target = tmp_path / "deep.zip"
    home = "/a/home path/that/does/not/exist"
    generate(MANIFEST_DIRECTORY / "deep.json", target, home)
    with ZipFile(target) as archive:
        names = archive.namelist()
        assert "tree/level1/level2/level3/note.txt" in names
        assert "tree/level1/empty/" in names
        assert f"{home.lstrip('/')}/" in names
        assert not any("${HOME}" in name for name in names)
        assert not any(name.startswith("/") for name in names)
        assert archive.read(f"{home.lstrip('/')}/") == b""


@pytest.mark.parametrize("name", ["minimal", "multiple", "deep"])
def test_generation_is_byte_identical_for_the_same_home(tmp_path, name):
    """Archive bytes are independent of generation time and output path."""
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    manifest = MANIFEST_DIRECTORY / f"{name}.json"
    generate(manifest, first, "/home/student")
    generate(manifest, second, "/home/student")
    assert first.read_bytes() == second.read_bytes()


def test_default_home_uses_environment(tmp_path, monkeypatch):
    """The default virtual home matches the emulator's real HOME variable."""
    monkeypatch.setenv("HOME", "/virtual/test user")
    target = tmp_path / "multiple.zip"
    generate(MANIFEST_DIRECTORY / "multiple.json", target)
    with ZipFile(target) as archive:
        assert "virtual/test user/" in archive.namelist()


@pytest.mark.parametrize("path", ["/absolute", "../escape", "a/../b"])
def test_generator_rejects_unsafe_member_paths(path):
    """Fixture edits cannot introduce archive traversal names."""
    with pytest.raises(ValueError):
        member_path(path, "/home/student")
