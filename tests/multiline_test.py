from __future__ import annotations

import functools
from typing import Sequence

from autoflake8.multiline import FilterMultilineImport


def test_is_over_parens() -> None:
    filt = FilterMultilineImport(b"from . import (\n")

    assert filt.is_over(b"module)\n") is True
    assert filt.is_over(b"  )\n") is True
    assert filt.is_over(b"  )  # comment\n") is True
    assert filt.is_over(b"from module import (a, b)\n") is True
    assert filt.is_over(b"#  )") is False
    assert filt.is_over(b"module\n") is False
    assert filt.is_over(b"module, \\\n") is False
    assert filt.is_over(b"\n") is False


def test_is_over_backslash() -> None:
    filt = FilterMultilineImport(b"from . import module, \\\n")
    assert filt.is_over(b"module\n") is True
    assert filt.is_over(b"\n") is True
    assert filt.is_over(b"m1, m2  # comment with \\\n") is True
    assert filt.is_over(b"m1, m2 \\\n") is False
    assert filt.is_over(b"m1, m2 \\  #\n") is False
    assert filt.is_over(b"m1, m2 \\  # comment with \\\n") is False
    assert filt.is_over(b"\\\n") is False


def test_is_over_multi_on_single_physical_line() -> None:
    filt = FilterMultilineImport(b"import os; import math, subprocess")
    assert filt.is_over() is True


def assert_fix(
    lines: Sequence[bytes],
    result: bytes,
    unused: tuple[bytes, ...] = (),
) -> None:
    fixer = FilterMultilineImport(
        lines[0],
        unused_module=unused,
    )
    fixed = functools.reduce(
        lambda acc, x: acc(x) if isinstance(acc, FilterMultilineImport) else acc,
        lines[1:],
        fixer(),
    )
    assert fixed == result


def test_fix() -> None:
    unused = tuple(b"third_party.lib" + x for x in (b"1", b"3", b"4"))

    # Example m0 (isort)
    assert_fix(
        [
            b"from third_party import (lib1, lib2, lib3,\n",
            b"                         lib4, lib5, lib6)\n",
        ],
        b"from third_party import (lib2, lib5, lib6)\n",
        unused=unused,
    )

    # Example m1(isort)
    assert_fix(
        [
            b"from third_party import (lib1,\n",
            b"                         lib2,\n",
            b"                         lib3,\n",
            b"                         lib4,\n",
            b"                         lib5,\n",
            b"                         lib6)\n",
        ],
        b"from third_party import (lib2,\n"
        b"                         lib5,\n"
        b"                         lib6)\n",
        unused=unused,
    )

    # Variation m1(isort)
    assert_fix(
        [
            b"from third_party import (lib1\n",
            b"                        ,lib2\n",
            b"                        ,lib3\n",
            b"                        ,lib4\n",
            b"                        ,lib5\n",
            b"                        ,lib6)\n",
        ],
        b"from third_party import (lib2\n"
        b"                        ,lib5\n"
        b"                        ,lib6)\n",
        unused=unused,
    )

    # Example m2 (isort)
    assert_fix(
        [
            b"from third_party import \\\n",
            b"    lib1, lib2, lib3, \\\n",
            b"    lib4, lib5, lib6\n",
        ],
        b"from third_party import \\\n    lib2, lib5, lib6\n",
        unused=unused,
    )

    # Example m3 (isort)
    assert_fix(
        [
            b"from third_party import (\n",
            b"    lib1,\n",
            b"    lib2,\n",
            b"    lib3,\n",
            b"    lib4,\n",
            b"    lib5\n",
            b")\n",
        ],
        b"from third_party import (\n    lib2,\n    lib5\n)\n",
        unused=unused,
    )

    # Example m4 (isort)
    assert_fix(
        [
            b"from third_party import (\n",
            b"    lib1, lib2, lib3, lib4,\n",
            b"    lib5, lib6)\n",
        ],
        b"from third_party import (\n    lib2, lib5, lib6)\n",
        unused=unused,
    )

    # Example m5 (isort)
    assert_fix(
        [
            b"from third_party import (\n",
            b"    lib1, lib2, lib3, lib4,\n",
            b"    lib5, lib6\n",
            b")\n",
        ],
        b"from third_party import (\n    lib2, lib5, lib6\n)\n",
        unused=unused,
    )

    # Some Deviations
    assert_fix(
        [
            b"from third_party import (\n",
            b"    lib1\\\n",  # only unused + line continuation
            b"    ,lib2, \n",
            b"    libA\n",  # used import with no commas
            b"    ,lib3, \n",  # leading and trailing commas with unused import
            b"    libB, \n",
            b"    \\\n",  # empty line with continuation
            b"    lib4,\n",  # unused import with comment
            b")\n",
        ],
        b"from third_party import (\n"
        b"    lib2\\\n"
        b"    ,libA, \n"
        b"    libB,\n"
        b")\n",
        unused=unused,
    )

    assert_fix(
        [
            b"from third_party import (\n",
            b"    lib1\n",
            b",\n",
            b"    lib2\n",
            b",\n",
            b"    lib3\n",
            b",\n",
            b"    lib4\n",
            b",\n",
            b"    lib5\n",
            b")\n",
        ],
        b"from third_party import (\n    lib2\n,\n    lib5\n)\n",
        unused=unused,
    )

    assert_fix(
        [
            b"from third_party import (\n",
            b"    lib1 \\\n",
            b", \\\n",
            b"    lib2 \\\n",
            b",\\\n",
            b"    lib3\n",
            b",\n",
            b"    lib4\n",
            b",\n",
            b"    lib5 \\\n",
            b")\n",
        ],
        b"from third_party import (\n    lib2 \\\n, \\\n    lib5 \\\n)\n",
        unused=unused,
    )


def test_indentation() -> None:
    unused = tuple(b"third_party.lib" + x for x in (b"1", b"3", b"4"))

    assert_fix(
        [
            b"    from third_party import (\n",
            b"            lib1, lib2, lib3, lib4,\n",
            b"    lib5, lib6\n",
            b")\n",
        ],
        b"    from third_party import (\n            lib2, lib5, lib6\n)\n",
        unused=unused,
    )

    assert_fix(
        [
            b"\tfrom third_party import \\\n",
            b"\t\tlib1, lib2, lib3, \\\n",
            b"\t\tlib4, lib5, lib6\n",
        ],
        b"\tfrom third_party import \\\n\t\tlib2, lib5, lib6\n",
        unused=unused,
    )


def test_fix_relative() -> None:
    assert_fix(
        [
            b"from . import (lib1, lib2, lib3,\n",
            b"               lib4, lib5, lib6)\n",
        ],
        b"from . import (lib2, lib5, lib6)\n",
        unused=tuple(b".lib" + x for x in (b"1", b"3", b"4")),
    )

    # Example m1(isort)
    assert_fix(
        [
            b"from .. import (lib1,\n",
            b"                lib2,\n",
            b"                lib3,\n",
            b"                lib4,\n",
            b"                lib5,\n",
            b"                lib6)\n",
        ],
        b"from .. import (lib2,\n                lib5,\n                lib6)\n",
        unused=tuple(b"..lib" + x for x in (b"1", b"3", b"4")),
    )

    # Example m2 (isort)
    assert_fix(
        [
            b"from ... import \\\n",
            b"    lib1, lib2, lib3, \\\n",
            b"    lib4, lib5, lib6\n",
        ],
        b"from ... import \\\n    lib2, lib5, lib6\n",
        unused=tuple(b"...lib" + x for x in (b"1", b"3", b"4")),
    )

    # Example m3 (isort)
    assert_fix(
        [
            b"from .parent import (\n",
            b"    lib1,\n",
            b"    lib2,\n",
            b"    lib3,\n",
            b"    lib4,\n",
            b"    lib5\n",
            b")\n",
        ],
        b"from .parent import (\n    lib2,\n    lib5\n)\n",
        unused=tuple(b".parent.lib" + x for x in (b"1", b"3", b"4")),
    )


def test_fix_without_from() -> None:
    unused = tuple(b"lib" + x for x in (b"1", b"3", b"4"))

    # Multiline but not "from"
    assert_fix(
        [b"import \\\n", b"    lib1, lib2, lib3 \\\n", b"    ,lib4, lib5, lib6\n"],
        b"import \\\n    lib2, lib5, lib6\n",
        unused=unused,
    )

    assert_fix(
        [b"import lib1, lib2, lib3, \\\n", b"       lib4, lib5, lib6\n"],
        b"import lib2, lib5, lib6\n",
        unused=unused,
    )

    # Problematic example without "from"
    assert_fix(
        [
            b"import \\\n",
            b"    lib1,\\\n",
            b"    lib2, \\\n",
            b"    libA\\\n",  # used import with no commas
            b"    ,lib3, \\\n",  # leading and trailing commas with unused
            b"    libB, \\\n",
            b"    \\  \n",  # empty line with continuation
            b"    lib4\\\n",  # unused import with comment
            b"\n",
        ],
        b"import \\\n    lib2,\\\n    libA, \\\n    libB\\\n\n",
        unused=unused,
    )

    assert_fix(
        [
            b"import \\\n",
            b"    lib1.x.y.z \\",
            b"    , \\\n",
            b"    lib2.x.y.z \\\n",
            b"    , \\\n",
            b"    lib3.x.y.z \\\n",
            b"    , \\\n",
            b"    lib4.x.y.z \\\n",
            b"    , \\\n",
            b"    lib5.x.y.z\n",
        ],
        b"import \\\n    lib2.x.y.z \\    , \\\n    lib5.x.y.z\n",
        unused=tuple(f"lib{x}.x.y.z".encode() for x in (1, 3, 4)),
    )


def test_give_up() -> None:
    # Semicolon
    assert_fix(
        [
            b"import \\\n",
            b"    lib1, lib2, lib3, \\\n",
            b"    lib4, lib5; import lib6\n",
        ],
        b"import \\\n    lib1, lib2, lib3, \\\n    lib4, lib5; import lib6\n",
        unused=tuple(b"lib" + x for x in (b"1", b"3", b"4")),
    )

    # Comments
    assert_fix(
        [
            b"from . import ( # comment\n",
            b"    lib1,\\\n",  # only unused + line continuation
            b"    lib2, \n",
            b"    libA\n",  # used import with no commas
            b"    ,lib3, \n",  # leading and trailing commas with unused import
            b"    libB, \n",
            b"    \\  \n",  # empty line with continuation
            b"    lib4,  # noqa \n",  # unused import with comment
            b") ; import sys\n",
        ],
        b"from . import ( # comment\n"
        b"    lib1,\\\n"
        b"    lib2, \n"
        b"    libA\n"
        b"    ,lib3, \n"
        b"    libB, \n"
        b"    \\  \n"
        b"    lib4,  # noqa \n"
        b") ; import sys\n",
        unused=tuple(b".lib" + x for x in (b"1", b"3", b"4")),
    )


def test_just_one_import_used() -> None:
    unused = (b"lib2",)

    assert_fix(
        [b"import \\\n", b"    lib1\n"],
        b"import \\\n    lib1\n",
        unused=unused,
    )

    assert_fix(
        [b"import \\\n", b"    lib2\n"],
        b"pass\n",
        unused=unused,
    )

    # Example from issue #8
    assert_fix(
        [
            b"\tfrom re import (subn)\n",
        ],
        b"\tpass\n",
        unused=(b"re.subn",),
    )


def test_just_one_import_left() -> None:
    # Examples from issue #8
    assert_fix(
        [b"from math import (\n", b"        sqrt,\n", b"        log\n", b"    )\n"],
        b"from math import (\n        log\n    )\n",
        unused=(b"math.sqrt",),
    )

    assert_fix(
        [
            b"from module import (a, b)\n",
        ],
        b"from module import a\n",
        unused=(b"module.b",),
    )

    assert_fix(
        [
            b"from module import (a,\n",
            b"                    b)\n",
        ],
        b"from module import a\n",
        unused=(b"module.b",),
    )

    assert_fix(
        [
            b"from re import (subn)\n",
        ],
        b"from re import (subn)\n",
    )


def test_no_empty_imports() -> None:
    assert_fix(
        [b"import \\\n", b"    lib1, lib3, \\\n", b"    lib4 \n"],
        b"pass \n",
        unused=tuple(b"lib" + x for x in (b"1", b"3", b"4")),
    )

    # Indented parenthesized block
    assert_fix(
        [
            b"\t\tfrom .parent import (\n",
            b"    lib1,\n",
            b"    lib3,\n",
            b"    lib4,\n",
            b")\n",
        ],
        b"\t\tpass\n",
        unused=tuple(b".parent.lib" + x for x in (b"1", b"3", b"4")),
    )
