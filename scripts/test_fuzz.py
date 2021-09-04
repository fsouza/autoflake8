"""Test that autoflake performs correctly on arbitrary Python files.
file.is_dir():
This checks that autoflake never introduces incorrect syntax. This is
done by doing a syntax check after the autoflake run. The number of
Pyflakes warnings is also confirmed to always improve.
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import os
import pathlib
import shlex
import shutil
import sys
import tempfile
from typing import Iterator
from typing import Sequence

import aiofiles
from autoflake8.fix import check as autoflake8_check
from autoflake8.fix import detect_source_encoding


ROOT_PATH = pathlib.Path(__file__).parent.parent.absolute()
AUTOFLAKE8_BIN = f"'{sys.executable}' '{ROOT_PATH / 'autoflake8' / 'cli.py'}'"

if sys.stdout.isatty():
    YELLOW = "\x1b[33m"
    END = "\x1b[0m"
else:
    YELLOW = ""
    END = ""


def colored(text, color):
    """Return color coded text."""
    return color + text + END


async def info(msg: str) -> None:
    await asyncio.to_thread(print, msg)


async def debug(msg: str) -> None:
    await asyncio.to_thread(print, msg, file=sys.stderr)


async def pyflakes_count(file: pathlib.Path) -> int:
    """Return pyflakes error count."""
    async with aiofiles.open(file, "rb") as f:
        return len(list(autoflake8_check(await f.read())))


async def walk(dir_path: pathlib.Path) -> Iterator[tuple[str, list[str], list[str]]]:
    def walk(p: str) -> Iterator[tuple[str, list[str], list[str]]]:
        return os.walk(p)

    return await asyncio.to_thread(walk, str(dir_path))


async def exists(path: pathlib.Path) -> bool:
    return await asyncio.to_thread(path.exists)


async def is_dir(path: pathlib.Path) -> bool:
    return await asyncio.to_thread(path.is_dir)


async def readlines(file: pathlib.Path) -> Sequence[str]:
    """Return contents of file as a list of lines."""
    async with aiofiles.open(file, "rb") as f:
        source = await f.read()

        return source.decode(
            encoding=detect_source_encoding(source),
        ).splitlines(keepends=True)


async def diff(before: pathlib.Path, after: pathlib.Path) -> str:
    """Return diff of two files."""

    return "".join(
        difflib.unified_diff(
            await readlines(before),
            await readlines(after),
            str(before),
            str(after),
        ),
    )


async def run(
    file: pathlib.Path,
    command: str,
    verbose: bool = False,
    options: list[str] | None = None,
) -> bool:
    """
    Run autoflake on file at filename.

    Return True on success.
    """
    await info(colored(f"--->  Testing with {file}", YELLOW))

    if not options:
        options = []

    temp_directory: str | None = None
    try:
        temp_directory = await asyncio.to_thread(tempfile.mkdtemp)
        return await _run(file, command, pathlib.Path(temp_directory), verbose, options)
    finally:
        if temp_directory is not None:
            await asyncio.to_thread(shutil.rmtree, temp_directory)


async def _run(
    file: pathlib.Path,
    command: str,
    temp_directory: pathlib.Path,
    verbose: bool,
    options: list[str],
) -> bool:
    temp_file = temp_directory / file.name

    await asyncio.to_thread(shutil.copyfile, file, temp_file)

    parts = shlex.split(command)
    proc = await asyncio.create_subprocess_exec(
        parts[0],
        *parts[1:],
        "--in-place",
        str(temp_file),
        *options,
    )
    status = await proc.wait()
    if status != 0:
        await debug(f"autoflake8 crashed on {file} with exit status {status}")
        return False

    try:
        file_diff = await diff(file, temp_file)
        if verbose:
            await debug(file_diff)

        if await check_syntax(file):
            try:
                await check_syntax(temp_file, raise_error=True)
            except (SyntaxError, TypeError, ValueError) as exc:
                await debug(
                    f"autoflake broke {file}\n{str(exc)}",
                )
                return False

        before_count = await pyflakes_count(file)
        after_count = await pyflakes_count(temp_file)

        if verbose:
            print("(before, after):", (before_count, after_count))

        if file_diff and after_count > before_count:
            sys.stderr.write(f"autoflake made {file} worse\n")
            return False
    except OSError as exc:
        sys.stderr.write(f"{str(exc)}\n")

    return True


async def check_syntax(file: pathlib.Path, raise_error: bool = False) -> bool:
    """Return True if syntax is okay."""
    async with aiofiles.open(file, "rb") as input_file:
        try:
            compile(await input_file.read(), "<string>", "exec", dont_inherit=True)
            return True
        except (SyntaxError, TypeError, ValueError):
            if raise_error:
                raise
            else:
                return False


def process_args() -> argparse.Namespace:
    """Return processed arguments (options and positional arguments)."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--command",
        default=AUTOFLAKE8_BIN,
        help="autoflake command (default: %(default)s)",
    )

    parser.add_argument(
        "--expand-star-imports",
        action="store_true",
        help="expand wildcard star imports with undefined " "names",
    )

    parser.add_argument("--imports", help='pass to the autoflake "--imports" option')

    parser.add_argument(
        "--remove-all-unused-imports",
        action="store_true",
        help='pass "--remove-all-unused-imports" option to ' "autoflake",
    )

    parser.add_argument(
        "--remove-duplicate-keys",
        action="store_true",
        help='pass "--remove-duplicate-keys" option to ' "autoflake",
    )

    parser.add_argument(
        "--remove-unused-variables",
        action="store_true",
        help='pass "--remove-unused-variables" option to ' "autoflake",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print verbose messages",
    )

    parser.add_argument("files", nargs="*", help="files to test against")

    return parser.parse_args()


async def check(args: argparse.Namespace) -> bool:
    """
    Run recursively runs autoflake8 on directory of files.

    Return False if the fix results in broken syntax.
    """
    if args.files:
        dir_paths = [pathlib.Path(file).absolute() for file in args.files]
    else:
        dir_paths = [
            pathlib.Path(path).absolute() for path in sys.path if os.path.isdir(path)
        ]

    options = []
    if args.expand_star_imports:
        options.append("--expand-star-imports")

    if args.imports:
        options.append("--imports=" + args.imports)

    if args.remove_all_unused_imports:
        options.append("--remove-all-unused-imports")

    if args.remove_duplicate_keys:
        options.append("--remove-duplicate-keys")

    if args.remove_unused_variables:
        options.append("--remove-unused-variables")

    files: asyncio.Queue[pathlib.Path] = asyncio.Queue()
    for dir_path in dir_paths:
        files.put_nowait(dir_path)

    completed_filenames = set()

    files_to_skip = {"bad_coding.py", "badsyntax_pep3120.py"}

    while not files.empty():
        file = await files.get()
        if not await exists(file):
            continue

        name = str(file)
        if name in completed_filenames:
            await info(
                colored(f"--->  Skipping previously tested {name}", YELLOW),
            )
            continue
        else:
            completed_filenames.update(name)

        if await is_dir(file):
            walk_iter = await walk(file)
            for root, directories, children in walk_iter:
                root_p = pathlib.Path(root)
                py_files = (
                    root_p / f
                    for f in children
                    if f.endswith(".py")
                    and not f.startswith(".")
                    and f not in files_to_skip
                )

                # this is horrible, we need a worker model.
                results = await asyncio.gather(
                    *(
                        run(
                            f,
                            command=args.command,
                            verbose=args.verbose,
                            options=options,
                        )
                        for f in py_files
                    )
                )

                if not all(results):
                    return False

                directories[:] = [d for d in directories if not d.startswith(".")]
        elif file.name not in files_to_skip:
            if not await run(
                file,
                command=args.command,
                verbose=args.verbose,
                options=options,
            ):
                return False

    return True


async def main() -> int:
    """Run main."""
    return 0 if await check(process_args()) else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(1)
