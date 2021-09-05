"""Test that autoflake performs correctly on arbitrary Python files.

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
from typing import IO
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


class Autoflake8Error(Exception):
    ...


class Worker:
    def __init__(
        self,
        queue: asyncio.Queue[str],
        args: argparse.Namespace,
        options: Sequence[str],
    ) -> None:
        self.queue = queue
        self.args = args
        self.options = options

    async def run(self) -> None:
        self.running = True
        while self.running:
            try:
                filename = await asyncio.wait_for(self.queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            else:
                try:
                    print(
                        colored(f"--->  Testing with {filename}", YELLOW),
                        file=sys.stderr,
                    )

                    await run(
                        filename=filename,
                        command=self.args.command,
                        verbose=self.args.verbose,
                        options=self.options,
                    )
                except Autoflake8Error as e:
                    print(f"fuzz error: {e}", file=sys.stderr)
                    if e.__cause__:
                        print(f"caused by: {e.__cause__}", file=sys.stderr)
                    raise
                finally:
                    self.queue.task_done()

    def stop(self) -> None:
        self.running = False


def colored(text, color):
    """Return color coded text."""
    return color + text + END


async def pyflakes_count(filename: str) -> int:
    """Return pyflakes error count."""
    async with aiofiles.open(filename, "rb") as f:
        return len(list(autoflake8_check(await f.read())))


async def readlines(filename: str) -> Sequence[str]:
    """Return contents of file as a list of lines."""
    async with aiofiles.open(filename, "rb") as f:
        source = await f.read()

        return source.decode(
            encoding=detect_source_encoding(source),
        ).splitlines(keepends=True)


async def diff(before: str, after: str) -> str:
    """Return diff of two files."""

    return "".join(
        difflib.unified_diff(
            await readlines(before),
            await readlines(after),
            before,
            after,
        ),
    )


async def run(
    filename: str,
    command: str,
    verbose: bool = False,
    options: Sequence[str] | None = None,
) -> None:
    """
    Run autoflake on file at filename.

    Return True on success.
    """
    if not options:
        options = []

    temp_directory: str | None = None
    try:
        temp_directory = await asyncio.to_thread(tempfile.mkdtemp)
        await _run(filename, command, temp_directory, verbose, options)
    finally:
        if temp_directory is not None:
            await asyncio.to_thread(shutil.rmtree, temp_directory)


async def _run(
    filename: str,
    command: str,
    temp_directory: str,
    verbose: bool,
    options: list[str],
) -> None:
    temp_filename = os.path.join(temp_directory, os.path.basename(filename))

    await asyncio.to_thread(shutil.copyfile, filename, temp_filename)

    cmd = shlex.split(command)
    proc = await asyncio.subprocess.create_subprocess_exec(
        cmd[0],
        *cmd[1:],
        "--in-place",
        temp_filename,
        *options,
    )

    status = await proc.wait()
    if status != 0:
        raise Autoflake8Error(f"autoflake crashed on {filename}")

    try:
        file_diff = await diff(filename, temp_filename)
        if verbose:
            print(file_diff, file=sys.stderr)

        if await check_syntax(filename):
            try:
                await check_syntax(temp_filename, raise_error=True)
            except (
                SyntaxError,
                TypeError,
                ValueError,
            ) as exc:
                raise Autoflake8Error(f"autoflake broke {filename}") from exc

        before_count = await pyflakes_count(filename)
        after_count = await pyflakes_count(temp_filename)

        if verbose:
            print("(before, after):", (before_count, after_count))

        if file_diff and after_count > before_count:
            raise Autoflake8Error(f"autoflake made {filename} worse")
    except OSError as exc:
        raise Autoflake8Error("something went wrong") from exc


async def check_syntax(filename: str, raise_error: bool = False) -> bool:
    """Return True if syntax is okay."""
    try:
        source = "".join(await readlines(filename))
        compile(source, "<string>", "exec", dont_inherit=True)
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

    parser.add_argument(
        "-n",
        "--num-workers",
        type=int,
        dest="num_workers",
        help="number of workers to run (default: %(default)d)",
        default=1,
    )

    return parser.parse_args()


async def check(args: argparse.Namespace, stdin: IO[str]) -> bool:
    """
    Run recursively run autoflake on directory of files.

    Return False if the fix results in broken syntax.
    """
    options = []
    if args.expand_star_imports:
        options.append("--expand-star-imports")

    if args.remove_duplicate_keys:
        options.append("--remove-duplicate-keys")

    if args.remove_unused_variables:
        options.append("--remove-unused-variables")

    queue: asyncio.Queue[str] = asyncio.Queue()

    print(f"starting {args.num_workers} workers")
    workers = [
        Worker(
            queue=queue,
            args=args,
            options=options,
        )
        for _ in range(args.num_workers)
    ]
    worker_tasks = [asyncio.create_task(worker.run()) for worker in workers]

    files_to_skip = {"bad_coding.py", "badsyntax_pep3120.py"}

    for line in stdin.readlines():
        filename = line.strip()
        basename = os.path.basename(filename)
        if not os.path.exists(filename):
            # Invalid symlink.
            continue

        if basename not in files_to_skip:
            queue.put_nowait(filename)

    await queue.join()
    for w in workers:
        w.stop()

    await asyncio.gather(*worker_tasks)

    return True


def main() -> int:
    """Run main."""
    result = asyncio.run(check(process_args(), sys.stdin))
    return 0 if result else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
