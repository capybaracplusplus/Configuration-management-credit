"""Check repository file size, source width, and Python structure."""

import subprocess
import sys
from pathlib import Path

from check_python import python_problems

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_LINES = 1000
MAX_CODE_COLUMNS = 80
MAX_OTHER_COLUMNS = 120
CODE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}
OTHER_SUFFIXES = {".svelte", ".css", ".html", ".sh", ".toml", ".yaml", ".yml"}


def repository_paths() -> list[Path]:
    """Include indexed files and untracked files unless Git ignores them."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    entries = result.stdout.decode().split("\0")
    return sorted({Path(item) for item in entries if item})


def column_limit(path: Path, inside_script: bool) -> int | None:
    """Select the applicable width limit for a source line."""
    if path.suffix in CODE_SUFFIXES or inside_script:
        return MAX_CODE_COLUMNS
    if path.suffix in OTHER_SUFFIXES:
        return MAX_OTHER_COLUMNS
    return None


def width_problems(path: Path, lines: list[str]) -> list[str]:
    """Check source columns, including script sections of Svelte files."""
    issues = []
    inside_script = False
    for number, line in enumerate(lines, start=1):
        if path.suffix == ".svelte" and "<script" in line:
            inside_script = True
        limit = column_limit(path, inside_script)
        if limit is not None and len(line) > limit:
            message = f"{len(line)} columns; maximum {limit}"
            issues.append(f"{path}:{number}: {message}")
        if path.suffix == ".svelte" and "</script>" in line:
            inside_script = False
    return issues


def file_problems(path: Path) -> list[str]:
    """Validate a readable text file without inspecting generated assets."""
    absolute = ROOT / path
    if not absolute.is_file():
        return []
    try:
        content = absolute.read_text(encoding="utf-8")
    except UnicodeError:
        return [f"{path}: binary or non-UTF-8 file must not be committed"]
    lines = content.splitlines()
    issues = []
    if len(lines) > MAX_FILE_LINES:
        issues.append(f"{path}: {len(lines)} lines; maximum {MAX_FILE_LINES}")
    issues.extend(width_problems(path, lines))
    if path.suffix == ".py":
        issues.extend(python_problems(path, content))
    return issues


def main() -> int:
    """Report every violation and return a command-line exit status."""
    paths = repository_paths()
    issues = [issue for path in paths for issue in file_problems(path)]
    for issue in issues:
        print(issue, file=sys.stderr)
    if issues:
        message = f"Repository checks failed: {len(issues)} issue(s)."
        print(message, file=sys.stderr)
        return 1
    print(f"Repository checks passed for {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
