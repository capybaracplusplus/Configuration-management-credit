"""Command-line entry point for the graphical emulator."""

import sys

from .configuration import debug_parameters, load_startup, parse_configuration
from .engine import Shell
from .launcher import launch
from .session import Session
from .vfs_zip import load_zip


def main() -> int:
    """Load physical startup parameters and launch the graphical session."""
    configuration = parse_configuration()
    print(debug_parameters(configuration), flush=True)
    try:
        startup = load_startup(configuration)
        filesystem = load_zip(configuration.vfs)
        paths = {
            "vfs": str(configuration.vfs) if configuration.vfs else None,
            "startup_script": (
                str(configuration.startup_script)
                if configuration.startup_script else None
            ),
        }
        launch(Session(
            shell=Shell(vfs=filesystem), configuration=paths, startup=startup,
        ))
    except (OSError, ValueError) as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
