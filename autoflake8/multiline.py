import re
import string
from typing import Iterable
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Union

from autoflake8.pending_fix import get_line_ending
from autoflake8.pending_fix import PendingFix

bytes_wsp = string.whitespace.encode()


class FilterMultilineImport(PendingFix):
    """Remove unused imports from multiline import statements.

    This class handles both the cases: "from imports" and "direct imports".

    Some limitations exist (e.g. imports with comments, lines joined by ``;``,
    etc). In these cases, the statement is left unchanged to avoid problems.
    """

    BASE_RE = re.compile(rb"\bfrom\s+([^ ]+)")
    IDENTIFIER_RE = re.compile(rb"[^,\s]+")
    IMPORT_RE = re.compile(rb"\bimport\b\s*")
    INDENTATION_RE = re.compile(rb"^\s*")
    SEGMENT_RE = re.compile(rb"([^,\s]+(?:[\s\\]+as[\s\\]+[^,\s]+)?[,\s\\)]*)", re.M)

    def __init__(
        self,
        line: bytes,
        unused_module: Tuple[bytes, ...] = (),
        previous_line: bytes = b"",
    ):
        """Receive the same parameters as ``filter_unused_import``."""
        self.remove = unused_module
        self.parenthesized = b"(" in line
        self.from_, imports = self.IMPORT_RE.split(line, maxsplit=1)
        match = self.BASE_RE.search(self.from_)
        self.base = match.group(1) if match else None
        self.give_up = False

        if b"\\" in previous_line:
            # Ignore tricky things like "try: \<new line> import" ...
            self.give_up = True

        self.analyze(line)

        PendingFix.__init__(self, imports)

    def is_over(self, line: Optional[bytes] = None) -> bool:
        """Return True if the multiline import statement is over."""
        line = line or self.accumulator[-1]

        if self.parenthesized:
            return _valid_char_in_line(b")", line)

        return not _valid_char_in_line(b"\\", line)

    def analyze(self, line: bytes) -> None:
        """Decide if the statement will be fixed or left unchanged."""
        if any(ch in line for ch in b";:#"):
            self.give_up = True

    def fix(self, accumulated: Iterable[bytes]) -> bytes:
        """Given a collection of accumulated lines, fix the entire import."""
        old_imports = b"".join(accumulated)
        ending = get_line_ending(old_imports)
        # Split imports into segments that contain the module name +
        # comma + whitespace and eventual <newline> \ ( ) chars
        segments = [x for x in self.SEGMENT_RE.findall(old_imports) if x]
        modules = [_segment_module(x) for x in segments]
        keep = _filter_imports(modules, self.base, self.remove)

        # Short-circuit if no import was discarded
        if len(keep) == len(segments):
            return self.from_ + b"import " + b"".join(accumulated)

        fixed = b""
        if keep:
            # Since it is very difficult to deal with all the line breaks and
            # continuations, let's use the code layout that already exists and
            # just replace the module identifiers inside the first N-1 segments
            # + the last segment
            templates = list(zip(modules, segments))
            templates = templates[: len(keep) - 1] + templates[-1:]
            # It is important to keep the last segment, since it might contain
            # important chars like `)`
            fixed = b"".join(
                template.replace(module, keep[i])
                for i, (module, template) in enumerate(templates)
            )

            # Fix the edge case: inline parenthesis + just one surviving import
            if self.parenthesized and any(ch not in fixed for ch in b"()"):
                fixed = fixed.strip(bytes_wsp + b"()") + ending

        # Replace empty imports with a "pass" statement
        empty = len(fixed.strip(bytes_wsp + b"\\(),")) < 1
        if empty:
            indentation_match = self.INDENTATION_RE.search(self.from_)
            if indentation_match:
                indentation = indentation_match.group(0)
                return indentation + b"pass" + ending

        return self.from_ + b"import " + fixed

    def __call__(
        self,
        line: Optional[bytes] = None,
    ) -> Union[bytes, "FilterMultilineImport"]:
        """Accumulate all the lines in the import and then trigger the fix."""
        if line:
            self.accumulator.append(line)
            self.analyze(line)
        if not self.is_over(line):
            return self
        if self.give_up:
            return self.from_ + b"import " + b"".join(self.accumulator)

        return self.fix(self.accumulator)


def _valid_char_in_line(char: bytes, line: bytes) -> bool:
    """Return True if a char appears in the line and is not commented."""
    comment_index = line.find(b"#")
    char_index = line.find(char)
    valid_char_in_line = char_index >= 0 and (
        comment_index > char_index or comment_index < 0
    )
    return valid_char_in_line


def _segment_module(segment: bytes) -> bytes:
    """Extract the module identifier inside the segment.

    It might be the case the segment does not have a module (e.g. is composed
    just by a parenthesis or line continuation and whitespace). In this
    scenario we just keep the segment... These characters are not valid in
    identifiers, so they will never be contained in the list of unused modules
    anyway.
    """
    return segment.strip(bytes_wsp + b",\\()") or segment


def _filter_imports(
    imports: Iterable[bytes],
    parent: Optional[bytes] = None,
    unused_module: Tuple[bytes, ...] = (),
) -> Sequence[bytes]:
    # We compare full module name (``a.module`` not `module`) to
    # guarantee the exact same module as detected from pyflakes.
    sep = b"" if parent and parent.endswith(b".") else b"."

    def full_name(name: bytes):
        return name if parent is None else parent + sep + name

    return [x for x in imports if full_name(x) not in unused_module]
