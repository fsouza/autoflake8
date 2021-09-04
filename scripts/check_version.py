#!/usr/bin/env python
from __future__ import annotations

import sys


def main() -> int:
    poetry_version = get_poetry_version()
    package_version = get_package_version()

    if poetry_version != package_version:
        print(
            f"ERROR: version mismatch.\n"
            f"version in __init__.py: {package_version}\n"
            f"version in pyproject.toml: {poetry_version}",
            file=sys.stderr,
        )
        return 1

    return 0


def get_package_version() -> str | None:
    with open("autoflake8/__init__.py") as f:
        for line in f:
            if line.startswith("__version__ = "):
                return _get_version(line)


def get_poetry_version() -> str | None:
    with open("pyproject.toml") as f:
        for line in f:
            if line.startswith("version = "):
                return _get_version(line)

    return None


def _get_version(line: str) -> str:
    _, _, version = line.partition(" = ")
    return version.strip().strip('"')


if __name__ == "__main__":
    sys.exit(main())
