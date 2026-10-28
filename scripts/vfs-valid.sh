#!/bin/sh
# Последовательно показать минимальную, многокомпонентную и глубокую VFS.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/tools/generate_fixtures.py"

for variant in minimal multiple deep; do
    printf 'VFS %s: проверьте сводку, диалог и ошибки; затем введите exit.\n' "$variant"
    "$PROJECT_DIR/run.sh" \
        --vfs "$PROJECT_DIR/.generated/vfs/$variant.zip" \
        --startup-script "$PROJECT_DIR/demos/stage-3.emu"
done

printf '%s\n' 'Все три варианта VFS проверены.'
