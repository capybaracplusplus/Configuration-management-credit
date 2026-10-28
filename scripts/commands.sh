#!/bin/sh
# Демонстрация всех основных команд на глубокой виртуальной файловой системе.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/tools/generate_fixtures.py"
printf '%s\n' 'Просмотрите диалог всех команд и ошибок, затем введите exit.'
exec "$PROJECT_DIR/run.sh" \
    --vfs "$PROJECT_DIR/.generated/vfs/deep.zip" \
    --startup-script "$PROJECT_DIR/demos/stage-4.emu"
