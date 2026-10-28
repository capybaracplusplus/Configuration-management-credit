"""Generate deterministic ZIP demonstrations from tracked text manifests."""

import base64
import json
import os
import stat
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / ".generated" / "vfs"
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
POSIX_CREATOR = 3
PERMISSION_SHIFT = 16
DIRECTORY_ATTRIBUTE = 0x10
PERMISSION_MASK = 0o777
FALLBACK_HOME = "/home/student"


def member_path(value: str, home: str) -> str:
    """Expand only the virtual home placeholder into an archive member."""
    name = value.replace("${HOME}", home.strip("/"))
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError(f"Недопустимый путь в манифесте: {name!r}")
    if any(part in {".", ".."} for part in name.split("/")):
        raise ValueError(f"Выход за пределы VFS: {name!r}")
    return name


def member_metadata(entry: dict, home: str) -> ZipInfo:
    """Give every member fixed timestamps and POSIX type/permission bits."""
    name = member_path(entry["path"], home)
    directory = name.endswith("/")
    default_mode = "0755" if directory else "0644"
    mode = int(entry.get("mode", default_mode), 8)
    if mode & ~PERMISSION_MASK:
        raise ValueError(f"Недопустимые права: {entry.get('mode')}")
    kind = stat.S_IFDIR if directory else stat.S_IFREG
    info = ZipInfo(name, date_time=FIXED_TIMESTAMP)
    info.create_system = POSIX_CREATOR
    info.external_attr = (kind | mode) << PERMISSION_SHIFT
    if directory:
        info.external_attr |= DIRECTORY_ATTRIBUTE
    info.compress_type = ZIP_STORED
    return info


def member_content(entry: dict) -> bytes:
    """Decode manifest bytes without consulting any host filesystem data."""
    if "text" in entry and "base64" in entry:
        raise ValueError("У файла должен быть один источник содержимого.")
    if entry["path"].endswith("/"):
        return b""
    if "base64" in entry:
        return base64.b64decode(entry["base64"], validate=True)
    return entry.get("text", "").encode("utf-8")


def generate(
    manifest: Path, destination: Path, home: str | None = None,
) -> None:
    """Write one ZIP as an explicit service operation, never extraction."""
    document = json.loads(manifest.read_text(encoding="utf-8"))
    virtual_home = home if home is not None else os.environ.get(
        "HOME", FALLBACK_HOME,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_STORED) as archive:
        for entry in document["entries"]:
            archive.writestr(
                member_metadata(entry, virtual_home), member_content(entry),
            )


def main() -> None:
    """Create the required valid archives and a deliberately invalid file."""
    for name in ("minimal", "multiple", "deep"):
        destination = OUTPUT_DIRECTORY / f"{name}.zip"
        generate(PROJECT_ROOT / "fixtures" / f"{name}.json", destination)
        print(destination)
    invalid = OUTPUT_DIRECTORY / "invalid.zip"
    invalid.write_bytes(b"This file is deliberately not a ZIP archive.\n")
    print(invalid)


if __name__ == "__main__":
    main()
