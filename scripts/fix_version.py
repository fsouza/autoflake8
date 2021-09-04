#!/usr/bin/env python
from __future__ import annotations

import pathlib
import sys


def main() -> int:
    init_file = "autoflake8/__init__.py"

    poetry_version = get_poetry_version()
    package_version_info = get_package_version(init_file)

    if not poetry_version or not package_version_info:
        print_err(
            "couldn't find the version in pyproject.toml or autoflake8/__init__.py",
        )
        return 1

    package_version, lineno = package_version_info
    if poetry_version != package_version:
        print_err(
            f"ERROR: version mismatch.\n"
            f"version in __init__.py: {package_version}\n"
            f"version in pyproject.toml: {poetry_version}",
        )
        rewrite_file_line(init_file, lineno, f'__version__ = "{poetry_version}"')
        print_err(f"fixed {init_file}")

        return 1

    return 0


def print_err(v: str) -> None:
    print(v, file=sys.stderr)


def get_package_version(filepath: str) -> tuple[str, int] | None:
    with open(filepath) as f:
        for lineno, line in enumerate(f, start=1):
            if line.startswith("__version__ = "):
                return _get_version(line), lineno

    return None


def get_poetry_version() -> str | None:
    with open("pyproject.toml") as f:
        for line in f:
            if line.startswith("version = "):
                return _get_version(line)

    return None


def rewrite_file_line(filepath: str, lineno: int, content_overwrite: str) -> None:
    # this is done the stupid way because I never expect __init__.py to grow too much :)
    f = pathlib.Path(filepath)
    original_lines = f.read_text().splitlines(keepends=True)
    original_lines[lineno - 1] = f"{content_overwrite}\n"
    f.write_text("".join(original_lines))


def _get_version(line: str) -> str:
    _, _, version = line.partition(" = ")
    return version.strip().strip('"')


if __name__ == "__main__":
    sys.exit(main())
