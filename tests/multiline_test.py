import functools
from typing import Optional
from typing import Sequence
from typing import Tuple

import autoflake


def test_is_over_parens() -> None:
    filt = autoflake.FilterMultilineImport("from . import (\n")

    assert filt.is_over("module)\n") is True
    assert filt.is_over("  )\n") is True
    assert filt.is_over("  )  # comment\n") is True
    assert filt.is_over("from module import (a, b)\n") is True
    assert filt.is_over("#  )") is False
    assert filt.is_over("module\n") is False
    assert filt.is_over("module, \\\n") is False
    assert filt.is_over("\n") is False


def test_is_over_backslash() -> None:
    filt = autoflake.FilterMultilineImport("from . import module, \\\n")
    assert filt.is_over("module\n") is True
    assert filt.is_over("\n") is True
    assert filt.is_over("m1, m2  # comment with \\\n") is True
    assert filt.is_over("m1, m2 \\\n") is False
    assert filt.is_over("m1, m2 \\  #\n") is False
    assert filt.is_over("m1, m2 \\  # comment with \\\n") is False
    assert filt.is_over("\\\n") is False


def test_is_over_multi_on_single_physical_line() -> None:
    filt = autoflake.FilterMultilineImport("import os; " "import math, subprocess")
    assert filt.is_over() is True


def assert_fix(
    lines: Sequence[str],
    result: str,
    unused: Optional[Tuple[str, ...]] = None,
    remove_all: bool = True,
) -> None:
    fixer = autoflake.FilterMultilineImport(
        lines[0],
        remove_all_unused_imports=remove_all,
        unused_module=unused or (),
    )
    fixed = functools.reduce(
        lambda acc, x: acc(x)
        if isinstance(acc, autoflake.FilterMultilineImport)
        else acc,
        lines[1:],
        fixer(),
    )
    assert fixed == result


def test_fix() -> None:
    unused = tuple(["third_party.lib" + x for x in ("1", "3", "4")])

    # Example m0 (isort)
    assert_fix(
        [
            "from third_party import (lib1, lib2, lib3,\n",
            "                         lib4, lib5, lib6)\n",
        ],
        "from third_party import (lib2, lib5, lib6)\n",
        unused=unused,
    )

    # Example m1(isort)
    assert_fix(
        [
            "from third_party import (lib1,\n",
            "                         lib2,\n",
            "                         lib3,\n",
            "                         lib4,\n",
            "                         lib5,\n",
            "                         lib6)\n",
        ],
        "from third_party import (lib2,\n"
        "                         lib5,\n"
        "                         lib6)\n",
        unused=unused,
    )

    # Variation m1(isort)
    assert_fix(
        [
            "from third_party import (lib1\n",
            "                        ,lib2\n",
            "                        ,lib3\n",
            "                        ,lib4\n",
            "                        ,lib5\n",
            "                        ,lib6)\n",
        ],
        "from third_party import (lib2\n"
        "                        ,lib5\n"
        "                        ,lib6)\n",
        unused=unused,
    )

    # Example m2 (isort)
    assert_fix(
        [
            "from third_party import \\\n",
            "    lib1, lib2, lib3, \\\n",
            "    lib4, lib5, lib6\n",
        ],
        "from third_party import \\\n" "    lib2, lib5, lib6\n",
        unused=unused,
    )

    # Example m3 (isort)
    assert_fix(
        [
            "from third_party import (\n",
            "    lib1,\n",
            "    lib2,\n",
            "    lib3,\n",
            "    lib4,\n",
            "    lib5\n",
            ")\n",
        ],
        "from third_party import (\n" "    lib2,\n" "    lib5\n" ")\n",
        unused=unused,
    )

    # Example m4 (isort)
    assert_fix(
        [
            "from third_party import (\n",
            "    lib1, lib2, lib3, lib4,\n",
            "    lib5, lib6)\n",
        ],
        "from third_party import (\n" "    lib2, lib5, lib6)\n",
        unused=unused,
    )

    # Example m5 (isort)
    assert_fix(
        [
            "from third_party import (\n",
            "    lib1, lib2, lib3, lib4,\n",
            "    lib5, lib6\n",
            ")\n",
        ],
        "from third_party import (\n" "    lib2, lib5, lib6\n" ")\n",
        unused=unused,
    )

    # Some Deviations
    assert_fix(
        [
            "from third_party import (\n",
            "    lib1\\\n",  # only unused + line continuation
            "    ,lib2, \n",
            "    libA\n",  # used import with no commas
            "    ,lib3, \n",  # leading and trailing commas with unused import
            "    libB, \n",
            "    \\\n",  # empty line with continuation
            "    lib4,\n",  # unused import with comment
            ")\n",
        ],
        "from third_party import (\n"
        "    lib2\\\n"
        "    ,libA, \n"
        "    libB,\n"
        ")\n",
        unused=unused,
    )

    assert_fix(
        [
            "from third_party import (\n",
            "    lib1\n",
            ",\n",
            "    lib2\n",
            ",\n",
            "    lib3\n",
            ",\n",
            "    lib4\n",
            ",\n",
            "    lib5\n",
            ")\n",
        ],
        "from third_party import (\n" "    lib2\n" ",\n" "    lib5\n" ")\n",
        unused=unused,
    )

    assert_fix(
        [
            "from third_party import (\n",
            "    lib1 \\\n",
            ", \\\n",
            "    lib2 \\\n",
            ",\\\n",
            "    lib3\n",
            ",\n",
            "    lib4\n",
            ",\n",
            "    lib5 \\\n",
            ")\n",
        ],
        "from third_party import (\n" "    lib2 \\\n" ", \\\n" "    lib5 \\\n" ")\n",
        unused=unused,
    )


def test_indentation() -> None:
    unused = tuple(["third_party.lib" + x for x in ("1", "3", "4")])

    assert_fix(
        [
            "    from third_party import (\n",
            "            lib1, lib2, lib3, lib4,\n",
            "    lib5, lib6\n",
            ")\n",
        ],
        "    from third_party import (\n" "            lib2, lib5, lib6\n" ")\n",
        unused=unused,
    )

    assert_fix(
        [
            "\tfrom third_party import \\\n",
            "\t\tlib1, lib2, lib3, \\\n",
            "\t\tlib4, lib5, lib6\n",
        ],
        "\tfrom third_party import \\\n" "\t\tlib2, lib5, lib6\n",
        unused=unused,
    )


def test_fix_relative() -> None:
    assert_fix(
        [
            "from . import (lib1, lib2, lib3,\n",
            "               lib4, lib5, lib6)\n",
        ],
        "from . import (lib2, lib5, lib6)\n",
        unused=tuple([".lib" + x for x in ("1", "3", "4")]),
    )

    # Example m1(isort)
    assert_fix(
        [
            "from .. import (lib1,\n",
            "                lib2,\n",
            "                lib3,\n",
            "                lib4,\n",
            "                lib5,\n",
            "                lib6)\n",
        ],
        "from .. import (lib2,\n" "                lib5,\n" "                lib6)\n",
        unused=tuple(["..lib" + x for x in ("1", "3", "4")]),
    )

    # Example m2 (isort)
    assert_fix(
        [
            "from ... import \\\n",
            "    lib1, lib2, lib3, \\\n",
            "    lib4, lib5, lib6\n",
        ],
        "from ... import \\\n" "    lib2, lib5, lib6\n",
        unused=tuple(["...lib" + str(x) for x in (1, 3, 4)]),
    )

    # Example m3 (isort)
    assert_fix(
        [
            "from .parent import (\n",
            "    lib1,\n",
            "    lib2,\n",
            "    lib3,\n",
            "    lib4,\n",
            "    lib5\n",
            ")\n",
        ],
        "from .parent import (\n" "    lib2,\n" "    lib5\n" ")\n",
        unused=tuple([".parent.lib" + x for x in ("1", "3", "4")]),
    )


def test_fix_without_from() -> None:
    unused = tuple(["lib" + str(x) for x in (1, 3, 4)])

    # Multiline but not "from"
    assert_fix(
        ["import \\\n", "    lib1, lib2, lib3 \\\n", "    ,lib4, lib5, lib6\n"],
        "import \\\n" "    lib2, lib5, lib6\n",
        unused=unused,
    )

    assert_fix(
        ["import lib1, lib2, lib3, \\\n", "       lib4, lib5, lib6\n"],
        "import lib2, lib5, lib6\n",
        unused=unused,
    )

    # Problematic example without "from"
    assert_fix(
        [
            "import \\\n",
            "    lib1,\\\n",
            "    lib2, \\\n",
            "    libA\\\n",  # used import with no commas
            "    ,lib3, \\\n",  # leading and trailing commas with unused
            "    libB, \\\n",
            "    \\  \n",  # empty line with continuation
            "    lib4\\\n",  # unused import with comment
            "\n",
        ],
        "import \\\n" "    lib2,\\\n" "    libA, \\\n" "    libB\\\n" "\n",
        unused=unused,
    )

    assert_fix(
        [
            "import \\\n",
            "    lib1.x.y.z \\",
            "    , \\\n",
            "    lib2.x.y.z \\\n",
            "    , \\\n",
            "    lib3.x.y.z \\\n",
            "    , \\\n",
            "    lib4.x.y.z \\\n",
            "    , \\\n",
            "    lib5.x.y.z\n",
        ],
        "import \\\n" "    lib2.x.y.z \\" "    , \\\n" "    lib5.x.y.z\n",
        unused=tuple([f"lib{x}.x.y.z" for x in (1, 3, 4)]),
    )


def test_give_up() -> None:
    # Semicolon
    assert_fix(
        [
            "import \\\n",
            "    lib1, lib2, lib3, \\\n",
            "    lib4, lib5; import lib6\n",
        ],
        "import \\\n" "    lib1, lib2, lib3, \\\n" "    lib4, lib5; import lib6\n",
        unused=tuple(["lib" + str(x) for x in (1, 3, 4)]),
    )

    # Comments
    assert_fix(
        [
            "from . import ( # comment\n",
            "    lib1,\\\n",  # only unused + line continuation
            "    lib2, \n",
            "    libA\n",  # used import with no commas
            "    ,lib3, \n",  # leading and trailing commas with unused import
            "    libB, \n",
            "    \\  \n",  # empty line with continuation
            "    lib4,  # noqa \n",  # unused import with comment
            ") ; import sys\n",
        ],
        "from . import ( # comment\n"
        "    lib1,\\\n"
        "    lib2, \n"
        "    libA\n"
        "    ,lib3, \n"
        "    libB, \n"
        "    \\  \n"
        "    lib4,  # noqa \n"
        ") ; import sys\n",
        unused=tuple([".lib" + str(x) for x in (1, 3, 4)]),
    )


def test_just_one_import_used() -> None:
    unused = ("lib2",)

    assert_fix(
        ["import \\\n", "    lib1\n"],
        "import \\\n" "    lib1\n",
        unused=unused,
    )

    assert_fix(
        ["import \\\n", "    lib2\n"],
        "pass\n",
        unused=unused,
    )

    # Example from issue #8
    assert_fix(
        [
            "\tfrom re import (subn)\n",
        ],
        "\tpass\n",
        unused=("re.subn",),
    )


def test_just_one_import_left() -> None:
    # Examples from issue #8
    assert_fix(
        ["from math import (\n", "        sqrt,\n", "        log\n", "    )\n"],
        "from math import (\n" "        log\n" "    )\n",
        unused=("math.sqrt",),
    )

    assert_fix(
        [
            "from module import (a, b)\n",
        ],
        "from module import a\n",
        unused=("module.b",),
    )

    assert_fix(
        [
            "from module import (a,\n",
            "                    b)\n",
        ],
        "from module import a\n",
        unused=("module.b",),
    )

    assert_fix(
        [
            "from re import (subn)\n",
        ],
        "from re import (subn)\n",
    )


def test_no_empty_imports() -> None:
    assert_fix(
        ["import \\\n", "    lib1, lib3, \\\n", "    lib4 \n"],
        "pass \n",
        unused=tuple(["lib" + x for x in ("1", "3", "4")]),
    )

    # Indented parenthesized block
    assert_fix(
        [
            "\t\tfrom .parent import (\n",
            "    lib1,\n",
            "    lib3,\n",
            "    lib4,\n",
            ")\n",
        ],
        "\t\tpass\n",
        unused=tuple([".parent.lib" + x for x in ("1", "3", "4")]),
    )


def test_without_remove_all() -> None:
    unused = tuple(["lib" + x for x in ("1", "3", "4")])
    assert_fix(
        [
            "import \\\n",
            "    lib1,\\\n",
            "    lib3,\\\n",
            "    lib4\n",
        ],
        "import \\\n" "    lib1,\\\n" "    lib3,\\\n" "    lib4\n",
        remove_all=False,
        unused=unused,
    )

    unused += tuple(["os.path." + x for x in ("dirname", "isdir", "join")])
    assert_fix(
        [
            "from os.path import (\n",
            "    dirname,\n",
            "    isdir,\n",
            "    join,\n",
            ")\n",
        ],
        "pass\n",
        remove_all=False,
        unused=unused,
    )

    assert_fix(
        [
            "import \\\n",
            "    os.path.dirname, \\\n",
            "    lib1, \\\n",
            "    lib3\n",
        ],
        "import \\\n" "    lib1, \\\n" "    lib3\n",
        remove_all=False,
        unused=unused,
    )
