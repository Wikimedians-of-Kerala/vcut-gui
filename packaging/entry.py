"""Entry point for the bundled application.

PyInstaller runs its entry script as a top-level module, so the relative
imports inside ``vcut.gui.app`` have no package to resolve against. Importing
through the installed package name instead keeps them working.
"""

import sys


def main() -> int:
    from vcut.gui.app import main as run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
