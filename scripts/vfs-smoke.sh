#!/bin/sh
# Проверить все три допустимые VFS со стартовым сценарием и автоматическим exit.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/tools/generate_fixtures.py"

for variant in minimal multiple deep; do
    printf 'Краткая проверка VFS %s; сеанс завершится автоматически.\n' "$variant"
    "$PROJECT_DIR/run.sh" \
        --vfs "$PROJECT_DIR/.generated/vfs/$variant.zip" \
        --startup-script "$PROJECT_DIR/demos/vfs-smoke.emu"
done

printf '%s\n' 'Все три автоматические демонстрации завершены.'
