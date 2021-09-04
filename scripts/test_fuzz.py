"""Test that autoflake performs correctly on arbitrary Python files.

This checks that autoflake never introduces incorrect syntax. This is
done by doing a syntax check after the autoflake run. The number of
Pyflakes warnings is also confirmed to always improve.
"""
import argparse
import difflib
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import List
from typing import Optional
from typing import Sequence

from autoflake8.fix import check as autoflake8_check
from autoflake8.fix import detect_source_encoding


ROOT_PATH = pathlib.Path(__file__).parent.parent.absolute()
AUTOFLAKE8_BIN = f"'{sys.executable}' '{ROOT_PATH / 'autoflake8' / 'cli.py'}'"

print(AUTOFLAKE8_BIN)

if sys.stdout.isatty():
    YELLOW = "\x1b[33m"
    END = "\x1b[0m"
else:
    YELLOW = ""
    END = ""


def colored(text, color):
    """Return color coded text."""
    return color + text + END


def pyflakes_count(filename: str) -> int:
    """Return pyflakes error count."""
    with open(filename, "rb") as f:
        return len(list(autoflake8_check(f.read())))


def readlines(filename: str) -> Sequence[str]:
    """Return contents of file as a list of lines."""
    with open(filename, "rb") as f:
        source = f.read()

        return source.decode(
            encoding=detect_source_encoding(source),
        ).splitlines(keepends=True)


def diff(before: str, after: str) -> str:
    """Return diff of two files."""

    return "".join(
        difflib.unified_diff(readlines(before), readlines(after), before, after),
    )


def run(
    filename: str,
    command: str,
    verbose: bool = False,
    options: Optional[List[str]] = None,
) -> bool:
    """
    Run autoflake on file at filename.

    Return True on success.
    """
    if not options:
        options = []

    temp_directory: Optional[str] = None
    try:
        temp_directory = tempfile.mkdtemp()
        return _run(filename, command, temp_directory, verbose, options)
    finally:
        if temp_directory is not None:
            shutil.rmtree(temp_directory)


def _run(
    filename: str,
    command: str,
    temp_directory: str,
    verbose: bool,
    options: List[str],
) -> bool:
    temp_filename = os.path.join(temp_directory, os.path.basename(filename))

    shutil.copyfile(filename, temp_filename)

    if 0 != subprocess.call(
        shlex.split(command) + ["--in-place", temp_filename] + options,
    ):
        sys.stderr.write("autoflake crashed on " + filename + "\n")
        return False

    try:
        file_diff = diff(filename, temp_filename)
        if verbose:
            sys.stderr.write(file_diff)

        if check_syntax(filename):
            try:
                check_syntax(temp_filename, raise_error=True)
            except (
                SyntaxError,
                TypeError,
                ValueError,
            ) as exc:
                sys.stderr.write(
                    f"autoflake broke {filename}\n{str(exc)}\n",
                )
                return False

        before_count = pyflakes_count(filename)
        after_count = pyflakes_count(temp_filename)

        if verbose:
            print("(before, after):", (before_count, after_count))

        if file_diff and after_count > before_count:
            sys.stderr.write(f"autoflake made {filename} worse\n")
            return False
    except OSError as exc:
        sys.stderr.write(f"{str(exc)}\n")

    return True


def check_syntax(filename: str, raise_error: bool = False) -> bool:
    """Return True if syntax is okay."""
    with open(filename) as input_file:
        try:
            compile(input_file.read(), "<string>", "exec", dont_inherit=True)
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


def check(args: argparse.Namespace) -> bool:
    """
    Run recursively run autoflake on directory of files.

    Return False if the fix results in broken syntax.
    """
    if args.files:
        dir_paths = args.files
    else:
        dir_paths = [path for path in sys.path if os.path.isdir(path)]

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

    filenames = dir_paths
    completed_filenames = set()

    files_to_skip = {"bad_coding.py", "badsyntax_pep3120.py"}

    while filenames:
        name = os.path.realpath(filenames.pop(0))
        basename = os.path.basename(name)
        if not os.path.exists(name):
            # Invalid symlink.
            continue

        if name in completed_filenames:
            sys.stderr.write(
                colored(f"--->  Skipping previously tested {name}\n", YELLOW),
            )
            continue
        else:
            completed_filenames.update(name)

        if os.path.isdir(name):
            for root, directories, children in os.walk(name):
                filenames += [
                    os.path.join(root, f)
                    for f in children
                    if f.endswith(".py") and not f.startswith(".")
                ]

                directories[:] = [d for d in directories if not d.startswith(".")]
        elif basename not in files_to_skip:
            sys.stderr.write(colored(f"--->  Testing with {name}\n", YELLOW))

            if not run(
                os.path.join(name),
                command=args.command,
                verbose=args.verbose,
                options=options,
            ):
                return False

    return True


def main() -> int:
    """Run main."""
    return 0 if check(process_args()) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
