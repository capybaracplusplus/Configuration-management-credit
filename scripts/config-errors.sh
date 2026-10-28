#!/bin/sh
# Проверка ошибок CLI и отсутствующего стартового файла без запуска GUI.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEMO_DIR=$(mktemp -d "${TMPDIR:-/tmp}/shell config errors.XXXXXX")
trap 'rm -rf "$DEMO_DIR"' EXIT HUP INT TERM
VFS_PATH="$DEMO_DIR/empty archive.zip"
"$PROJECT_DIR/.venv/bin/python" -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1], "w").close()' "$VFS_PATH"

expect_failure() {
    expected_status=$1
    shift
    if "$PROJECT_DIR/run.sh" "$@"; then
        printf '%s\n' 'Ошибка проверки: приложение неожиданно завершилось успешно.' >&2
        exit 1
    else
        actual_status=$?
    fi
    if [ "$actual_status" != "$expected_status" ]; then
        printf 'Ожидался код %s, получен %s.\n' "$expected_status" "$actual_status" >&2
        exit 1
    fi
    printf 'Получен ожидаемый код %s.\n' "$expected_status"
}

expect_failure 2 --unknown
expect_failure 2 --vfs
expect_failure 2 --startup-script
expect_failure 1 --startup-script "$DEMO_DIR/missing script.emu"
expect_failure 1 --vfs "$VFS_PATH" --startup-script "$DEMO_DIR/missing script.emu"

printf '%s\n' 'Проверка обработки ошибок завершена.'
