#!/bin/sh
# Проверка каждого параметра, их сочетания и пробелов в физических путях.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEMO_DIR=$(mktemp -d "${TMPDIR:-/tmp}/shell config valid.XXXXXX")
trap 'rm -rf "$DEMO_DIR"' EXIT HUP INT TERM
VFS_PATH="$DEMO_DIR/empty archive.zip"
STARTUP_PATH="$DEMO_DIR/startup script.emu"
EXIT_PATH="$DEMO_DIR/exit script.emu"
"$PROJECT_DIR/.venv/bin/python" -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1], "w").close()' "$VFS_PATH"
cp "$PROJECT_DIR/demos/stage-2.emu" "$STARTUP_PATH"
cp "$PROJECT_DIR/demos/exit.emu" "$EXIT_PATH"

printf '%s\n' '1/4: Без параметров. Проверьте значения по умолчанию и введите exit.'
"$PROJECT_DIR/run.sh"

printf '%s\n' '2/4: Только --vfs. Проверьте путь с пробелами и введите exit.'
"$PROJECT_DIR/run.sh" --vfs "$VFS_PATH"

printf '%s\n' '3/4: Только --startup-script. Проверьте диалог и ошибки; введите exit.'
"$PROJECT_DIR/run.sh" --startup-script "$STARTUP_PATH"

printf '%s\n' '4/4: Оба параметра. Сценарий завершит сеанс автоматически.'
"$PROJECT_DIR/run.sh" --vfs "$VFS_PATH" --startup-script "$EXIT_PATH"
printf '%s\n' 'Проверка допустимых параметров завершена.'
