import argparse
import logging
import signal
import sys
from typing import IO
from typing import Sequence
from typing import Set

from autoflake8 import __version__
from autoflake8.fix import find_files
from autoflake8.fix import fix_file
from autoflake8.fix import fix_stdin


def _main(
    argv: Sequence[str],
    stdout: IO[bytes],
    stdin: IO[bytes],
    logger: logging.Logger,
) -> int:
    """
    Returns exit status.

    0 means no error.
    """

    parser = argparse.ArgumentParser(description=__doc__, prog="autoflake8")
    parser.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="return error code if changes are needed",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="drill down directories recursively",
    )
    parser.add_argument(
        "--exclude",
        metavar="globs",
        type=_split_comma_separated,
        default=set(),
        help="exclude file/directory names that match these comma-separated globs",
    )
    parser.add_argument(
        "--expand-star-imports",
        action="store_true",
        help="expand wildcard star imports with undefined "
        "names; this only triggers if there is only "
        "one star import in the file; this is skipped if "
        "there are any uses of `__all__` or `del` in the "
        "file",
    )
    parser.add_argument(
        "--remove-duplicate-keys",
        action="store_true",
        help="remove all duplicate keys in objects",
    )
    parser.add_argument(
        "--remove-unused-variables",
        action="store_true",
        help="remove unused variables",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + __version__,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbosity",
        default=0,
        help="print more verbose logs (you can " "repeat `-v` to make it more verbose)",
    )
    parser.add_argument("--exit-zero-even-if-changed", action="store_true")
    parser.add_argument("files", nargs="+", help="files to format")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-i",
        "--in-place",
        action="store_true",
        help="make changes to files instead of printing diffs",
    )
    group.add_argument(
        "-s",
        "--stdout",
        action="store_true",
        dest="write_to_stdout",
        help=(
            "print changed text to stdout. defaults to true "
            "when formatting stdin, or to false otherwise"
        ),
    )

    args = parser.parse_args(argv[1:])
    set_logging_level(logger, args.verbosity)

    exit_status = 0

    filenames = list(set(args.files))
    for name in find_files(
        filenames,
        args.recursive,
        args.exclude,
        logger=logger,
    ):
        if name == "-":
            exit_status |= fix_stdin(
                stdin=stdin,
                stdout=stdout,
                args=args,
                logger=logger,
            )
        else:
            try:
                exit_status |= fix_file(
                    filename=name,
                    args=args,
                    stdout=stdout,
                    logger=logger,
                )
            except OSError as exception:
                logger.error(str(exception))
                exit_status = 3

    return exit_status


def make_logger(stderr: IO[str]) -> logging.Logger:
    logger = logging.getLogger("autoflake8")
    logger.propagate = False
    logger.addHandler(logging.StreamHandler(stderr))

    return logger


def set_logging_level(logger: logging.Logger, verbosity: int) -> None:
    log_levels = [logging.WARNING, logging.INFO, logging.DEBUG]

    try:
        log_level = log_levels[verbosity]
    except IndexError:
        log_level = log_levels[-1]

    logger.setLevel(log_level)


def _split_comma_separated(string: str) -> Set[str]:
    """Return a set of strings."""
    return {text.strip() for text in string.split(",") if text.strip()}


def main() -> int:
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except AttributeError:
        # SIGPIPE is not available on Windows.
        pass

    try:
        return _main(
            sys.argv,
            stdout=sys.stdout.buffer,
            stdin=sys.stdin.buffer,
            logger=make_logger(sys.stderr),
        )
    except KeyboardInterrupt:
        return 2


if __name__ == "__main__":
    sys.exit(main())
