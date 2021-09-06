import argparse
import ast
import collections
import difflib
import fnmatch
import io
import logging
import os
import re
import tempfile
import tokenize
from typing import Dict
from typing import IO
from typing import Iterable
from typing import Iterator
from typing import List
from typing import Mapping
from typing import Sequence
from typing import Tuple
from typing import Union

import pyflakes.api
import pyflakes.messages
import pyflakes.reporter

from autoflake8.multiline import _filter_imports
from autoflake8.multiline import FilterMultilineImport
from autoflake8.pending_fix import get_line_ending
from autoflake8.pending_fix import PendingFix


ATOMS = frozenset([tokenize.NAME, tokenize.NUMBER, tokenize.STRING])


class Regex:
    BASE_MODULE = re.compile(rb"\bfrom\s+([^ ]+)")
    DEL = re.compile(rb"\bdel\b")
    DUNDER_ALL = re.compile(rb"\b__all__\b")
    EXCEPT = re.compile(rb"^\s*except [\s,()\w]+ as \w+:$")
    INDENTATION = re.compile(rb"^\s*")
    PYTHON_SHEBANG = re.compile(rb"^#!.*\bpython3?\b\s*$")
    STAR = re.compile(rb"\*")
    IMPORT = re.compile(rb"\bimport\b\s*")
    CODING = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")


def detect_source_encoding(source: bytes) -> str:
    """
    Detects the encoding of a byte stream representing a Python source file
    following the rules defined in PEP-263:

    - only checks the first two lines
    - match each of the lines with a regular expression (the regexp is copied
      verbatim from the PEP)
    - if no encoding defined, assume it is utf-8
    """

    lines = source.splitlines()[:2]
    for line in lines:
        m = Regex.CODING.match(line)
        if m is not None:
            return m.group(1).decode()

    return "utf-8"


def unused_import_line_numbers(
    messages: Iterable[pyflakes.messages.Message],
) -> Iterator[int]:
    """Yield line numbers of unused imports."""
    for message in messages:
        if isinstance(message, pyflakes.messages.UnusedImport):
            yield message.lineno


def unused_import_module_name(
    messages: Iterable[pyflakes.messages.Message],
) -> Iterator[Tuple[int, bytes]]:
    """Yield line number and module name of unused imports."""
    regex = re.compile("'(.+?)'")
    for message in messages:
        if isinstance(message, pyflakes.messages.UnusedImport):
            module_name = regex.search(str(message))
            if module_name:
                module_name = module_name.group()[1:-1]
                yield (message.lineno, module_name.encode())


def star_import_used_line_numbers(
    messages: Iterable[pyflakes.messages.Message],
) -> Iterator[int]:
    """Yield line number of star import usage."""
    for message in messages:
        if isinstance(message, pyflakes.messages.ImportStarUsed):
            yield message.lineno


def star_import_usage_undefined_name(
    messages: Iterable[pyflakes.messages.Message],
) -> Iterator[Tuple[int, bytes, bytes]]:
    """Yield line number, undefined name, and its possible origin module."""
    for message in messages:
        if isinstance(message, pyflakes.messages.ImportStarUsage):
            undefined_name = message.message_args[0]
            module_name = message.message_args[1]
            yield (message.lineno, undefined_name.encode(), module_name.encode())


def unused_variable_line_numbers(
    messages: Iterable[pyflakes.messages.Message],
) -> Iterator[int]:
    """Yield line numbers of unused variables."""
    for message in messages:
        if isinstance(message, pyflakes.messages.UnusedVariable):
            yield message.lineno


def duplicate_key_line_numbers(
    messages: Iterable[pyflakes.messages.Message],
    source: bytes,
) -> Iterator[int]:
    """Yield line numbers of duplicate keys."""
    target_messages = [
        message
        for message in messages
        if isinstance(message, pyflakes.messages.MultiValueRepeatedKeyLiteral)
    ]

    if messages:
        # Filter out complex cases. We don't want to bother trying to parse
        # this stuff and get it right. We can do it on a key-by-key basis.

        key_to_messages = create_key_to_messages_dict(target_messages)

        lines = source.split(b"\n")

        for (key, messages) in key_to_messages.items():
            good = True
            for message in messages:
                line = lines[message.lineno - 1]
                key = message.message_args[0]

                if not dict_entry_has_key(line, key):
                    good = False

            if good:
                for message in messages:
                    yield message.lineno


def create_key_to_messages_dict(
    messages: Iterable[pyflakes.messages.MultiValueRepeatedKeyLiteral],
) -> Mapping[str, List[pyflakes.messages.MultiValueRepeatedKeyLiteral]]:
    """Return dict mapping the key to list of messages."""
    dictionary = collections.defaultdict(lambda: [])
    for message in messages:
        dictionary[message.message_args[0]].append(message)
    return dictionary


def check(source: bytes) -> Iterable[pyflakes.messages.Message]:
    """Return messages from pyflakes."""
    reporter = ListReporter()
    try:
        pyflakes.api.check(source, filename="<string>", reporter=reporter)
    except (AttributeError, RecursionError, UnicodeDecodeError):
        pass
    return reporter.messages


class StubFile:
    """Stub out file for pyflakes."""

    def write(self, *_):
        """Stub out."""


class ListReporter(pyflakes.reporter.Reporter):
    """Accumulate messages in messages list."""

    def __init__(self) -> None:
        """Initialize.

        Ignore errors from Reporter.
        """
        ignore = StubFile()
        pyflakes.reporter.Reporter.__init__(self, ignore, ignore)
        self.messages: List[pyflakes.messages.Message] = []

    def flake(self, message: pyflakes.messages.Message) -> None:
        """Accumulate messages."""
        self.messages.append(message)


def is_multiline_import(line: bytes, previous_line: bytes = b"") -> bool:
    """Return True if import is spans multiples lines."""
    for symbol in b"()":
        if symbol in line:
            return True

    return is_multiline_statement(line, previous_line)


def is_multiline_statement(line: bytes, previous_line: bytes = b"") -> bool:
    """Return True if this is part of a multiline statement."""
    for symbol in b"\\:;":
        if symbol in line:
            return True

    sio = io.StringIO(line.decode())
    try:
        list(tokenize.generate_tokens(sio.readline))
        return previous_line.rstrip().endswith(b"\\")
    except (SyntaxError, tokenize.TokenError):
        return True


def filter_from_import(line: bytes, unused_module: Tuple[bytes, ...]) -> bytes:
    """
    Parse and filter ``from something import a, b, c``.

    Return line without unused import modules, or `pass` if all of the
    module in import is unused.
    """
    (indentation, imports) = re.split(pattern=rb"\bimport\b", string=line, maxsplit=1)
    base_module_match = Regex.BASE_MODULE.search(indentation)
    if base_module_match:
        base_module = base_module_match.group(1)
    else:
        base_module = None

    imports = re.split(pattern=rb"\s*,\s*", string=imports.strip())
    filtered_imports = _filter_imports(imports, base_module, unused_module)

    # All of the import in this statement is unused
    if not filtered_imports:
        return get_indentation(line) + b"pass" + get_line_ending(line)

    indentation += b"import "

    return indentation + b", ".join(sorted(filtered_imports)) + get_line_ending(line)


def break_up_import(line: bytes) -> bytes:
    """Return line with imports on separate lines."""
    assert b"\\" not in line
    assert b"(" not in line
    assert b")" not in line
    assert b";" not in line
    assert b"#" not in line
    assert not line.lstrip().startswith(b"from")

    newline = get_line_ending(line)
    if not newline:
        return line

    (indentation, imports) = re.split(pattern=rb"\bimport\b", string=line, maxsplit=1)

    indentation += b"import "
    assert newline

    return b"".join(
        [indentation + i.strip() + newline for i in sorted(imports.split(b","))],
    )


def filter_code(
    source: bytes,
    expand_star_imports: bool = False,
    remove_duplicate_keys: bool = False,
    remove_unused_variables: bool = False,
) -> Iterator[bytes]:
    """Yield code with unused imports removed."""
    messages = check(source)

    marked_import_line_numbers = frozenset(unused_import_line_numbers(messages))
    marked_unused_module: Dict[int, List[bytes]] = collections.defaultdict(lambda: [])
    for line_number, module_name in unused_import_module_name(messages):
        marked_unused_module[line_number].append(module_name)

    undefined_names = []
    if expand_star_imports and not (
        # See explanations in #18.
        Regex.DUNDER_ALL.search(source)
        or Regex.DEL.search(source)
    ):
        marked_star_import_line_numbers = frozenset(
            star_import_used_line_numbers(messages),
        )
        if len(marked_star_import_line_numbers) > 1:
            # Auto expanding only possible for single star import
            marked_star_import_line_numbers = frozenset()
        else:
            for _, undefined_name, _ in star_import_usage_undefined_name(
                messages,
            ):
                undefined_names.append(undefined_name)
            if not undefined_names:
                marked_star_import_line_numbers = frozenset()
    else:
        marked_star_import_line_numbers = frozenset()

    if remove_unused_variables:
        marked_variable_line_numbers = frozenset(unused_variable_line_numbers(messages))
    else:
        marked_variable_line_numbers = frozenset()

    if remove_duplicate_keys:
        marked_key_line_numbers = frozenset(
            duplicate_key_line_numbers(messages, source),
        )
    else:
        marked_key_line_numbers = frozenset()

    previous_line = b""
    result = None
    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        if isinstance(result, PendingFix):
            result = result(line)
        elif b"#" in line:
            result = line
        elif line_number in marked_import_line_numbers:
            result = filter_unused_import(
                line,
                unused_module=tuple(marked_unused_module[line_number]),
                previous_line=previous_line,
            )
        elif line_number in marked_variable_line_numbers:
            result = filter_unused_variable(line)
        elif line_number in marked_key_line_numbers:
            result = filter_duplicate_key(
                line,
                line_number,
                marked_key_line_numbers,
            )
        elif line_number in marked_star_import_line_numbers:
            result = filter_star_import(line, undefined_names)
        else:
            result = line

        if isinstance(result, bytes):
            yield result

        previous_line = line


def group_messages_by_line(
    messages: Iterable[pyflakes.messages.Message],
) -> Mapping[int, pyflakes.messages.Message]:
    """Return dictionary that maps line number to message."""
    line_messages = {}
    for message in messages:
        line_messages[message.lineno] = message
    return line_messages


def filter_star_import(
    line: bytes,
    marked_star_import_undefined_name: Iterable[bytes],
) -> bytes:
    """Return line with the star import expanded."""
    undefined_name = sorted(set(marked_star_import_undefined_name))
    return Regex.STAR.sub(b", ".join(undefined_name), line)


def filter_unused_import(
    line: bytes,
    unused_module: Tuple[bytes, ...],
    previous_line: bytes = b"",
) -> Union[bytes, PendingFix]:
    """Return line if used, otherwise return None."""
    # Ignore doctests.
    if line.lstrip().startswith(b">"):
        return line

    if is_multiline_import(line, previous_line):
        filt = FilterMultilineImport(
            line,
            unused_module,
            previous_line,
        )
        return filt()

    is_from_import = line.lstrip().startswith(b"from")

    if b"," in line and not is_from_import:
        return break_up_import(line)

    if b"," in line:
        assert is_from_import
        return filter_from_import(line, unused_module)
    else:
        # We need to replace import with "pass" in case the import is the
        # only line inside a block. For example,
        # "if True:\n    import os". In such cases, if the import is
        # removed, the block will be left hanging with no body.
        return get_indentation(line) + b"pass" + get_line_ending(line)


def filter_unused_variable(line: bytes, previous_line: bytes = b"") -> bytes:
    """Return line if used, otherwise return None."""
    if re.match(Regex.EXCEPT, line):
        return re.sub(rb" as \w+:$", b":", line, count=1)
    elif is_multiline_statement(line, previous_line):
        return line
    elif line.count(b"=") == 1:
        split_line = line.split(b"=")
        assert len(split_line) == 2
        value = split_line[1].lstrip()
        if b"," in split_line[0]:
            return line

        if is_literal_or_name(value):
            # Rather than removing the line, replace with it "pass" to avoid
            # a possible hanging block with no body.
            value = b"pass" + get_line_ending(line)

        return get_indentation(line) + value
    else:
        return line


def filter_duplicate_key(
    line: bytes,
    line_number: int,
    marked_line_numbers: Iterable[int],
) -> bytes:
    """Return '' if first occurrence of the key otherwise return `line`."""
    if marked_line_numbers and line_number == sorted(marked_line_numbers)[0]:
        return b""

    return line


def dict_entry_has_key(line: bytes, key: str) -> bool:
    """
    Return True if `line` is a dict entry that uses `key`.

    Return False for multiline cases where the line should not be removed by
    itself.

    """
    if b"#" in line:
        return False

    result = re.match(rb"\s*(.*)\s*:\s*(.*),\s*$", line)
    if not result:
        return False

    try:
        candidate_key = ast.literal_eval(result.group(1).decode())
    except (SyntaxError, ValueError):
        return False

    if is_multiline_statement(result.group(2)):
        return False

    return candidate_key == key


def is_literal_or_name(value: bytes) -> bool:
    """Return True if value is a literal or a name."""
    try:
        ast.literal_eval(value.decode())
        return True
    except (SyntaxError, ValueError):
        pass

    if value.strip() in [b"dict()", b"list()", b"set()"]:
        return True

    # Support removal of variables on the right side. But make sure
    # there are no dots, which could mean an access of a property.
    return re.match(rb"^\w+\s*$", value) is not None


def useless_pass_line_numbers(source: bytes) -> Iterator[int]:
    """Yield line numbers of unneeded "pass" statements."""
    sio = io.StringIO(source.decode(encoding=detect_source_encoding(source)))
    previous_token_type = None
    last_pass_row = None
    last_pass_indentation = None
    previous_line = b""
    for token in tokenize.generate_tokens(sio.readline):
        token_type = token[0]
        start_row = token[2][0]
        line = token[4].encode()

        is_pass = token_type == tokenize.NAME and line.strip() == b"pass"

        # Leading "pass".
        if (
            start_row - 1 == last_pass_row
            and get_indentation(line) == last_pass_indentation
            and token_type in ATOMS
            and not is_pass
        ):
            yield start_row - 1

        if is_pass:
            last_pass_row = start_row
            last_pass_indentation = get_indentation(line)

        # Trailing "pass".
        if (
            is_pass
            and previous_token_type != tokenize.INDENT
            and not previous_line.rstrip().endswith(b"\\")
        ):
            yield start_row

        previous_token_type = token_type
        previous_line = line


def filter_useless_pass(source: bytes) -> Iterator[bytes]:
    """Yield code with useless "pass" lines removed."""
    try:
        marked_lines = frozenset(useless_pass_line_numbers(source))
    except (SyntaxError, tokenize.TokenError):
        marked_lines = frozenset()

    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        if line_number not in marked_lines:
            yield line


def get_indentation(line: bytes) -> bytes:
    """Return leading whitespace."""
    if line.strip():
        non_whitespace_index = len(line) - len(line.lstrip())
        return line[:non_whitespace_index]
    else:
        return b""


def fix_code(
    source: bytes,
    expand_star_imports: bool = False,
    remove_duplicate_keys: bool = False,
    remove_unused_variables: bool = False,
) -> bytes:
    """Return code with all filtering run on it."""
    if not source:
        return source

    # pyflakes does not handle "nonlocal" correctly.
    if b"nonlocal" in source:
        remove_unused_variables = False

    filtered_source = None
    while True:
        filtered_source = b"".join(
            filter_useless_pass(
                b"".join(
                    filter_code(
                        source,
                        expand_star_imports=expand_star_imports,
                        remove_duplicate_keys=remove_duplicate_keys,
                        remove_unused_variables=remove_unused_variables,
                    ),
                ),
            ),
        )

        if filtered_source == source:
            break
        source = filtered_source

    return filtered_source


def fix_file(
    *,
    filename: str,
    args: argparse.Namespace,
    stdout: IO[bytes],
    logger: logging.Logger,
) -> int:
    """Run fix_code() on a file."""
    with open(filename, "rb+") as input_file:
        return _fix_file(
            input_file,
            filename,
            args,
            args.write_to_stdout,
            stdout,
            logger=logger,
        )


def fix_stdin(
    *,
    stdin: IO[bytes],
    stdout: IO[bytes],
    args: argparse.Namespace,
    logger: logging.Logger,
) -> int:
    return _fix_file(stdin, "<stdin>", args, True, stdout, logger)


def _fix_file(
    input_file: IO[bytes],
    filename: str,
    args: argparse.Namespace,
    write_to_stdout: bool,
    stdout: IO[bytes],
    logger: logging.Logger,
) -> int:
    source = input_file.read()
    original_source = source

    filtered_source = fix_code(
        source,
        expand_star_imports=args.expand_star_imports,
        remove_duplicate_keys=args.remove_duplicate_keys,
        remove_unused_variables=args.remove_unused_variables,
    )

    if original_source != filtered_source:
        if args.check:
            stdout.write(
                f"{filename}: Unused imports/variables detected".encode(),
            )
            return 1

        if write_to_stdout:
            stdout.write(filtered_source)
        elif args.in_place:
            with tempfile.NamedTemporaryFile(
                delete=False,
                dir=os.path.dirname(filename),
            ) as output_file:
                output_file.write(filtered_source)

            # close the input file before replacing it, this is required on
            # Windows.
            input_file.close()

            os.replace(output_file.name, filename)
            logger.info(f"Fixed {filename}")
        else:
            encoding = detect_source_encoding(original_source)
            diff = get_diff_text(
                [
                    line.decode(encoding=encoding)
                    for line in original_source.splitlines(keepends=True)
                ],
                [
                    line.decode(encoding=encoding)
                    for line in filtered_source.splitlines(keepends=True)
                ],
                filename,
            )
            stdout.write(diff.encode())

        return 0 if args.exit_zero_even_if_changed else 1
    elif write_to_stdout:
        stdout.write(filtered_source)
    else:
        if args.check:
            logger.info(b"No issues detected!\n")
        else:
            logger.debug("Clean %s: nothing to fix", filename)

    return 0


def get_diff_text(old: Sequence[str], new: Sequence[str], filename: str) -> str:
    """Return text of unified diff between old and new."""
    newline = "\n"
    diff = difflib.unified_diff(
        old,
        new,
        "original/" + filename,
        "fixed/" + filename,
        lineterm=newline,
    )

    text = ""
    for line in diff:
        text += line

        # Work around missing newline (http://bugs.python.org/issue2142).
        if not line.endswith(newline):
            text += newline + r"\ No newline at end of file" + newline

    return text


def is_python_file(filename: str) -> bool:
    """Return True if filename is Python file."""
    if filename.endswith(".py"):
        return True

    max_python_file_detection_bytes = 1024
    try:
        with open(filename, "rb") as f:
            text = f.read(max_python_file_detection_bytes)
            if not text:
                return False
            first_line = text.splitlines()[0]
    except (OSError, IndexError):
        return False

    if not Regex.PYTHON_SHEBANG.match(first_line):
        return False

    return True


def is_exclude_file(filename: str, exclude: Iterable[str]) -> bool:
    """Return True if file matches exclude pattern."""
    base_name = os.path.basename(filename)

    if base_name.startswith("."):
        return True

    for pattern in exclude:
        if fnmatch.fnmatch(base_name, pattern):
            return True

        if fnmatch.fnmatch(filename, pattern):
            return True

    return False


def match_file(filename: str, exclude: Iterable[str], logger: logging.Logger) -> bool:
    """Return True if file is okay for modifying/recursing."""
    if is_exclude_file(filename, exclude):
        logger.debug("Skipped %s: matched to exclude pattern", filename)
        return False

    if not os.path.isdir(filename) and not is_python_file(filename):
        return False

    return True


def find_files(
    filenames: List[str],
    recursive: bool,
    exclude: Iterable[str],
    logger: logging.Logger,
) -> Iterator[str]:
    """Yield filenames."""
    while filenames:
        name = filenames.pop(0)
        if recursive and os.path.isdir(name):
            for root, directories, children in os.walk(name):
                filenames += [
                    os.path.join(root, f)
                    for f in children
                    if match_file(os.path.join(root, f), exclude, logger)
                ]
                directories[:] = [
                    d
                    for d in directories
                    if match_file(os.path.join(root, d), exclude, logger)
                ]
        else:
            if not is_exclude_file(name, exclude):
                yield name
            else:
                logger.debug("Skipped %s: matched to exclude pattern", name)
