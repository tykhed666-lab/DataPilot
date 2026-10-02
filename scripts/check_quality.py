"""Run the same deterministic checks used by CI."""

from __future__ import annotations

import subprocess
import sys

COMMANDS = (
    ("ruff", "format", "--check", "."),
    ("ruff", "check", "."),
    ("pyright", "src"),
    ("pytest", "-q"),
)


def main() -> int:
    for command in COMMANDS:
        print(f"\n> {' '.join(command)}", flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
