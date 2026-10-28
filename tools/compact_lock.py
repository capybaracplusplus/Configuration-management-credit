"""Keep npm's generated dependency data below the PDF's file-line limit."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Retain valid lock JSON with one compact line per package record."""
    path = ROOT / "package-lock.json"
    data = json.loads(path.read_text())
    packages = data.pop("packages")
    lines = ["{"]
    for key, value in data.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value)},")
    lines.append('  "packages": {')
    entries = [
        f"    {json.dumps(key)}: {json.dumps(value, separators=(',', ':'))}"
        for key, value in packages.items()
    ]
    lines.append(",\n".join(entries))
    lines.extend(["  }", "}"])
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
