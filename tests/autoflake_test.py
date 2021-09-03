"""Test suite for autoflake."""
import os
import pathlib
import re
import subprocess
from contextlib import _GeneratorContextManager
from typing import Callable
from typing import Iterable
from typing import List

import pytest

import autoflake


def test_unused_import_line_numbers() -> None:
    assert (
        list(
            autoflake.unused_import_line_numbers(autoflake.check("import os\n")),
        )
        == [1]
    )


def test_unused_import_line_numbers_with_from() -> None:
    assert (
        list(
            autoflake.unused_import_line_numbers(
                autoflake.check("from os import path\n"),
            ),
        )
        == [1]
    )


def test_unused_import_line_numbers_with_dot() -> None:
    assert (
        list(
            autoflake.unused_import_line_numbers(
                autoflake.check("import os.path\n"),
            ),
        )
        == [1]
    )


def test_extract_package_name() -> None:
    assert autoflake.extract_package_name("import os") == "os"
    assert autoflake.extract_package_name("from os import path") == "os"
    assert autoflake.extract_package_name("import os.path") == "os"


def test_extract_package_name_should_ignore_doctest_for_now() -> None:
    assert autoflake.extract_package_name(">>> import os") is None


def test_standard_package_names() -> None:
    assert "os" in autoflake.standard_package_names()
    assert "subprocess" in autoflake.standard_package_names()
    assert "urllib" in autoflake.standard_package_names()

    assert "autoflake" not in autoflake.standard_package_names()
    assert "pep8" not in autoflake.standard_package_names()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("\n", "\n"),
        ("abc\n", "\n"),
        ("abc\t  \t\n", "\t  \t\n"),
        ("abc", ""),
        ("", ""),
    ],
)
def test_get_line_ending(source: str, expected: str) -> None:
    assert autoflake.get_line_ending(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", ""),
        ("    abc", "    "),
        ("    abc  \n\t", "    "),
        ("\tabc  \n\t", "\t"),
        (" \t abc  \n\t", " \t "),
        ("    ", ""),
    ],
)
def test_get_indentation(source: str, expected: str) -> None:
    assert autoflake.get_indentation(source) == expected


def test_filter_star_import() -> None:
    assert (
        autoflake.filter_star_import("from math import *", ["cos"])
        == "from math import cos"
    )

    assert (
        autoflake.filter_star_import("from math import *", ["sin", "cos"])
        == "from math import cos, sin"
    )


def test_filter_unused_variable() -> None:
    assert autoflake.filter_unused_variable("x = foo()") == "foo()"

    assert autoflake.filter_unused_variable("    x = foo()") == "    foo()"


def test_filter_unused_variable_with_literal_or_name() -> None:
    assert autoflake.filter_unused_variable("x = 1") == "pass"
    assert autoflake.filter_unused_variable("x = y") == "pass"
    assert autoflake.filter_unused_variable("x = {}") == "pass"


def test_filter_unused_variable_with_basic_data_structures() -> None:
    assert autoflake.filter_unused_variable("x = dict()") == "pass"
    assert autoflake.filter_unused_variable("x = list()") == "pass"
    assert autoflake.filter_unused_variable("x = set()") == "pass"


def test_filter_unused_variable_should_ignore_multiline() -> None:
    assert autoflake.filter_unused_variable("x = foo()\\") == "x = foo()\\"


def test_filter_unused_variable_should_multiple_assignments() -> None:
    assert autoflake.filter_unused_variable("x = y = foo()") == "x = y = foo()"


def test_filter_unused_variable_with_exception() -> None:
    assert (
        autoflake.filter_unused_variable("except Exception as exception:")
        == "except Exception:"
    )

    assert (
        autoflake.filter_unused_variable(
            "except (ImportError, ValueError) as foo:",
        )
        == "except (ImportError, ValueError):"
    )


def test_filter_code() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
import os
import re
os.foo()
""",
        ),
    )

    expected = """\
import os
pass
os.foo()
"""

    assert result == expected


def test_filter_code_with_indented_import() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
import os
if True:
    import re
os.foo()
""",
        ),
    )

    expected = """\
import os
if True:
    pass
os.foo()
"""

    assert result == expected


def test_filter_code_with_from() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from os import path
x = 1
""",
        ),
    )

    expected = """\
pass
x = 1
"""

    assert result == expected


def test_filter_code_with_not_from() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
import frommer
x = 1
""",
        ),
    )

    expected = """\
pass
x = 1
"""

    assert result == expected


def test_filter_code_with_used_from() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
import frommer
print(frommer)
""",
        ),
    )

    expected = """\
import frommer
print(frommer)
"""

    assert result == expected


def test_filter_code_with_ambiguous_from() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from frommer import abc, frommer, xyz
""",
        ),
    )

    expected = """\
pass
"""

    assert result == expected


def test_filter_code_should_avoid_inline_except() -> None:
    line = """\
try: from zap import foo
except: from zap import bar
"""
    assert (
        "".join(
            autoflake.filter_code(line),
        )
        == line
    )


def test_filter_code_should_avoid_escaped_newlines() -> None:
    line = """\
try:\\
from zap import foo
except:\\
from zap import bar
"""
    assert "".join(autoflake.filter_code(line)) == line


def test_filter_code_with_remove_all_unused_imports() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
import foo
import zap
x = 1
""",
        ),
    )

    expected = """\
pass
pass
x = 1
"""

    assert result == expected


def test_filter_code_should_ignore_imports_with_inline_comment() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from os import path  # foo
from os import path
from fake_foo import z  # foo, foo, zap
x = 1
""",
        ),
    )

    expected = """\
from os import path  # foo
pass
from fake_foo import z  # foo, foo, zap
x = 1
"""

    assert result == expected


def test_filter_code_should_respect_noqa() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from os import path
import re  # noqa
from subprocess import Popen  # NOQA
import sys # noqa: F401
x = 1
""",
        ),
    )

    expected = """\
pass
import re  # noqa
from subprocess import Popen  # NOQA
import sys # noqa: F401
x = 1
"""

    assert result == expected


def test_filter_code_expand_star_imports__one_function() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from math import *
sin(1)
""",
            expand_star_imports=True,
        ),
    )

    expected = """\
from math import sin
sin(1)
"""

    assert result == expected


def test_filter_code_expand_star_imports__two_functions() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from math import *
sin(1)
cos(1)
""",
            expand_star_imports=True,
        ),
    )

    expected = """\
from math import cos, sin
sin(1)
cos(1)
"""

    assert result == expected


def test_filter_code_ignore_multiple_star_import() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
from math import *
from re import *
sin(1)
cos(1)
""",
            expand_star_imports=True,
        ),
    )

    expected = """\
from math import *
from re import *
sin(1)
cos(1)
"""

    assert result == expected


def test_filter_code_with_special_re_symbols_in_key() -> None:
    result = "".join(
        autoflake.filter_code(
            """\
a = {
'????': 3,
'????': 2,
}
print(a)
""",
            remove_duplicate_keys=True,
        ),
    )

    expected = """\
a = {
'????': 2,
}
print(a)
"""

    assert result == expected


@pytest.mark.parametrize(
    ("line", "previous_line", "expected"),
    [
        pytest.param(
            r"""\
import os, \
math, subprocess
""",
            "",
            True,
            id="backslash",
        ),
        pytest.param(
            """\
import os, math, subprocess
""",
            "",
            False,
            id="multiple imports in a single line",
        ),
        pytest.param(
            """\
import os, math, subprocess
""",
            "if: \\\n",
            True,
            id="multiple imports in a single line, but with previous_line",
        ),
        pytest.param(
            "from os import (path, sep)" "",
            "",
            True,
            id="parens",
        ),
    ],
)
def test_is_multiline_import(line: str, previous_line: str, expected: bool) -> None:
    assert autoflake.is_multiline_import(line, previous_line=previous_line) is expected


@pytest.mark.parametrize(
    ("line", "previous_line", "expected"),
    [
        pytest.param("x = foo()", "", False, id="simple assignment"),
        pytest.param("x = 1;", "", True, id="assignment with semicolon"),
        pytest.param("import os; \\", "", True, id="continuation (backslash)"),
        pytest.param("foo(", "", True, id="unclosed parens"),
        pytest.param("1", "x = \\", True, id="simple value, with previous_line"),
    ],
)
def test_multiline_statement(line: str, previous_line: str, expected: bool) -> None:
    assert (
        autoflake.is_multiline_statement(line, previous_line=previous_line) is expected
    )


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(
            "import abc, subprocess, math\n",
            "import abc\nimport math\nimport subprocess\n",
            id="basic case",
        ),
        pytest.param(
            "    import abc, subprocess, math\n",
            "    import abc\n    import math\n    import subprocess\n",
            id="with indentation",
        ),
        pytest.param(
            "import abc, subprocess, math",
            "import abc, subprocess, math",
            id="do nothing on line ending",
        ),
    ],
)
def test_break_up_import(line: str, expected: str) -> None:
    assert autoflake.break_up_import(line) == expected


def test_filter_from_import_no_remove() -> None:
    result = autoflake.filter_from_import(
        "    from foo import abc, subprocess, math\n",
        unused_module=(),
    )

    expected = """\
    from foo import abc, math, subprocess\n"""

    assert result == expected


def test_filter_from_import_remove_module() -> None:
    result = autoflake.filter_from_import(
        "    from foo import abc, subprocess, math\n",
        unused_module=("foo.abc",),
    )

    expected = """\
    from foo import math, subprocess\n"""

    assert result == expected


def test_filter_from_import() -> None:
    result = autoflake.filter_from_import(
        "    from foo import abc, subprocess, math\n",
        unused_module=("foo.abc", "foo.subprocess", "foo.math"),
    )

    expected = "    pass\n"

    assert result == expected


def test_filter_code_multiline_imports() -> None:
    result = "".join(
        autoflake.filter_code(
            r"""\
import os
import re
import os, \
    math, subprocess
os.foo()
""",
        ),
    )

    expected = r"""\
import os
pass
import os
os.foo()
"""

    assert result == expected


def test_filter_code_multiline_from_imports() -> None:
    result = "".join(
        autoflake.filter_code(
            r"""\
import os
import re
from os.path import (
    exists,
    join,
)
join('a', 'b')
from os.path import \
abspath, basename, \
commonpath
os.foo()
from os.path import \
    isfile \
    , isdir
isdir('42')
""",
        ),
    )

    expected = r"""\
import os
pass
from os.path import (
    join,
)
join('a', 'b')
pass
os.foo()
from os.path import \
    isdir
isdir('42')
"""

    assert result == expected


def test_filter_code_should_ignore_semicolons() -> None:
    result = "".join(
        autoflake.filter_code(
            r"""\
import os
import re
import os; import math, subprocess
os.foo()
""",
        ),
    )

    expected = r"""\
import os
pass
import os; import math, subprocess
os.foo()
"""

    assert result == expected


def test_filter_code_should_ignore_docstring() -> None:
    line = """
def foo():
'''
>>> import math
'''
"""

    assert "".join(autoflake.filter_code(line)) == line


def test_fix_code() -> None:
    result = autoflake.fix_code(
        """\
import os
import re
import abc, math, subprocess
from sys import exit, version
os.foo()
math.pi
x = version
""",
    )

    expected = """\
import os
import math
from sys import version
os.foo()
math.pi
x = version
"""

    assert result == expected


def test_fix_code_with_from_and_as__mixed() -> None:
    result = autoflake.fix_code(
        """\
from collections import defaultdict, namedtuple as xyz
xyz
""",
    )

    expected = """\
from collections import namedtuple as xyz
xyz
"""

    assert result == expected


def test_fix_code_with_from_and_as__multiple() -> None:
    result = autoflake.fix_code(
        """\
from collections import defaultdict as abc, namedtuple as xyz
xyz
""",
    )

    expected = """\
from collections import namedtuple as xyz
xyz
"""

    assert result == expected


def test_fix_code_with_from_and_as__unused_as() -> None:
    result = autoflake.fix_code(
        """\
from collections import defaultdict as abc, namedtuple
namedtuple
""",
    )

    expected = """\
from collections import namedtuple
namedtuple
"""

    assert result == expected


def test_fix_code_with_from_and_as__all_unused() -> None:
    result = autoflake.fix_code(
        """\
from collections import defaultdict as abc, namedtuple as xyz
""",
    )

    assert result == ""


def test_fix_code_with_from_and_as__custom_modules() -> None:
    code = """\
from x import a as b, c as d
"""

    assert autoflake.fix_code(code) == ""


def test_fix_code_with_from_and_depth_module() -> None:
    expected = """\
from distutils.version import StrictVersion
StrictVersion('1.0.0')
"""
    result = autoflake.fix_code(
        """\
from distutils.version import LooseVersion, StrictVersion
StrictVersion('1.0.0')
""",
    )

    assert result == expected


def test_fix_code_with_from_and_depth_module__aliasing() -> None:
    result = autoflake.fix_code(
        """\
from distutils.version import LooseVersion, StrictVersion as version
version('1.0.0')
""",
    )

    expected = """\
from distutils.version import StrictVersion as version
version('1.0.0')
"""

    assert result == expected


def test_fix_code_with_indented_from() -> None:
    result = autoflake.fix_code(
        """\
def z():
    from ctypes import c_short, c_uint, c_int, c_long, pointer, POINTER, byref
    POINTER, byref
""",
    )

    expected = """\
def z():
    from ctypes import POINTER, byref
    POINTER, byref
"""

    assert result == expected


def test_fix_code_with_indented_from__all_unused() -> None:
    result = autoflake.fix_code(
        """\
def z():
    from ctypes import c_short, c_uint, c_int, c_long, pointer, POINTER, byref
""",
    )

    expected = """\
def z():
    pass
"""

    assert result == expected


def test_fix_code_with_empty_string() -> None:
    assert autoflake.fix_code("") == ""


def test_fix_code_with_from_and_as_and_escaped_newline() -> None:
    """Make sure stuff after escaped newline is not lost."""
    result = autoflake.fix_code(
        """\
from collections import defaultdict, namedtuple \\
as xyz
xyz
""",
    )
    # We currently leave lines with escaped newlines as is. But in the
    # future this we may parse them and remove unused import accordingly.
    # For now, we'll work around it here.
    result = re.sub(r" *\\\n *as ", " as ", result)

    expected = """\
from collections import namedtuple as xyz
xyz
"""

    assert autoflake.fix_code(result) == expected


def test_fix_code_with_unused_variables() -> None:
    result = autoflake.fix_code(
        """\
def main():
    x = 10
    y = 11
    print(y)
""",
        remove_unused_variables=True,
    )

    expected = """\
def main():
    y = 11
    print(y)
"""

    assert result == expected


def test_fix_code_with_unused_variables_should_skip_nonlocal() -> None:
    """pyflakes does not handle nonlocal correctly."""
    code = """\
def bar():
    x = 1

    def foo():
        nonlocal x
        x = 2
"""

    assert autoflake.fix_code(code, remove_unused_variables=True) == code


def test_fix_code_with_comma_on_right() -> None:
    result = autoflake.fix_code(
        """\
def main():
    x = (1, 2, 3)
""",
        remove_unused_variables=True,
    )

    expected = """\
def main():
    pass
"""

    assert result == expected


def test_fix_code_with_unused_variables_should_skip_multiple() -> None:
    code = """\
def main():
    (x, y, z) = (1, 2, 3)
    print(z)
"""

    assert autoflake.fix_code(code, remove_unused_variables=True) == code


def test_fix_code_should_handle_pyflakes_recursion_error_gracefully() -> None:
    code = "x = [{}]".format("+".join("abc" for _ in range(2000)))

    assert autoflake.fix_code(code) == code


def test_fix_code_with_duplicate_key() -> None:
    result = "".join(
        autoflake.fix_code(
            """\
a = {
    (0,1): 1,
    (0, 1): 'two',
    (0,1): 3,
}
print(a)
""",
            remove_duplicate_keys=True,
        ),
    )

    expected = """\
a = {
    (0,1): 3,
}
print(a)
"""

    assert result == expected


def test_fix_code_with_duplicate_key_longer() -> None:
    expected = """\
{
    'a': 0,
    'c': 2,
    'd': 3,
    'e': 4,
    'f': 5,
    'b': 6,
}
"""

    result = "".join(
        autoflake.fix_code(
            """\
{
    'a': 0,
    'b': 1,
    'c': 2,
    'd': 3,
    'e': 4,
    'f': 5,
    'b': 6,
}
""",
            remove_duplicate_keys=True,
        ),
    )

    assert result == expected


def test_fix_code_with_duplicate_key_with_many_braces() -> None:
    result = "".join(
        autoflake.fix_code(
            """\
a = None

{None: {None: None},
 }

{
    None: a.a,
    None: a.b,
}
""",
            remove_duplicate_keys=True,
        ),
    )

    expected = """\
a = None

{None: {None: None},
 }

{
    None: a.b,
}
"""

    assert result == expected


def test_fix_code_should_ignore_complex_case_of_duplicate_key() -> None:
    code = """\
a = {(0,1): 1, (0, 1): 'two',
    (0,1): 3,
}
print(a)
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code


def test_fix_code_should_ignore_complex_case_of_duplicate_key_comma() -> None:
    code = """\
{
    1: {0,
    },
    1: {2,
    },
}
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code


def test_fix_code_should_ignore_complex_case_of_duplicate_key_partially() -> None:
    """We only handle simple cases."""
    code = """\
a = {(0,1): 1, (0, 1): 'two',
    (0,1): 3,
    (2,3): 4,
    (2,3): 4,
    (2,3): 5,
}
print(a)
"""

    expected = """\
a = {(0,1): 1, (0, 1): 'two',
    (0,1): 3,
    (2,3): 5,
}
print(a)
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == expected


def test_fix_code_should_ignore_more_cases_of_duplicate_key() -> None:
    """We only handle simple cases."""
    code = """\
a = {
    (0,1):
    1,
    (0, 1): 'two',
  (0,1): 3,
}
print(a)
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code


def test_fix_code_should_ignore_duplicate_key_with_comments() -> None:
    """We only handle simple cases."""
    code = """\
a = {
    (0,1)  # : f
    :
    1,
    (0, 1): 'two',
    (0,1): 3,
}
print(a)
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code

    code = """\
{
    1: {0,
    },
    1: #{2,
    #},
    0
}
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code


def test_fix_code_should_ignore_duplicate_key_with_multiline_key() -> None:
    """We only handle simple cases."""
    code = """\
a = {
    (0,1
    ): 1,
    (0, 1): 'two',
    (0,1): 3,
}
print(a)
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code


def test_fix_code_should_ignore_duplicate_key_with_no_comma() -> None:
    """We don't want to delete the line and leave a lone comma."""
    code = """\
a = {
    (0,1) : 1
    ,
    (0, 1): 'two',
    (0,1): 3,
}
print(a)
"""

    assert "".join(autoflake.fix_code(code, remove_duplicate_keys=True)) == code


def test_useless_pass_line_numbers() -> None:
    assert list(autoflake.useless_pass_line_numbers("pass\n")) == [1]

    assert list(autoflake.useless_pass_line_numbers("if True:\n    pass\n")) == []


def test_useless_pass_line_numbers_with_escaped_newline() -> None:
    assert list(autoflake.useless_pass_line_numbers("if True:\\\n    pass\n")) == []


def test_useless_pass_line_numbers_with_more_complex() -> None:
    result = list(
        autoflake.useless_pass_line_numbers(
            """\
if True:
    pass
else:
    True
    x = 1
    pass
""",
        ),
    )

    assert result == [6]


def test_filter_useless_pass() -> None:
    result = "".join(
        autoflake.filter_useless_pass(
            """\
if True:
    pass
else:
    True
    x = 1
    pass
""",
        ),
    )

    expected = """\
if True:
    pass
else:
    True
    x = 1
"""

    assert result == expected


def test_filter_useless_pass_with_syntax_error() -> None:
    source = """\
if True:
if True:
            if True:
    if True:
if True:
    pass
else:
    True
    pass
    pass
    x = 1
"""

    assert "".join(autoflake.filter_useless_pass(source)) == source


def test_filter_useless_pass_more_complex() -> None:
    result = "".join(
        autoflake.filter_useless_pass(
            """\
if True:
    pass
else:
    def foo():
        pass
        # abc
    def bar():
        # abc
        pass
    def blah():
        123
        pass
        pass  # Nope.
        pass
    True
    x = 1
    pass
""",
        ),
    )

    expected = """\
if True:
    pass
else:
    def foo():
        pass
        # abc
    def bar():
        # abc
        pass
    def blah():
        123
        pass  # Nope.
    True
    x = 1
"""

    assert result == expected


def test_filter_useless_pass_with_try() -> None:
    result = "".join(
        autoflake.filter_useless_pass(
            """\
import os
os.foo()
try:
    pass
    pass
except ImportError:
    pass
""",
        ),
    )

    expected = """\
import os
os.foo()
try:
    pass
except ImportError:
    pass
"""

    assert result == expected


def test_filter_useless_pass_leading_pass() -> None:
    result = "".join(
        autoflake.filter_useless_pass(
            """\
if True:
    pass
    pass
    pass
    pass
else:
    pass
    True
    x = 1
    pass
""",
        ),
    )

    expected = """\
if True:
    pass
else:
    True
    x = 1
"""

    assert result == expected


def test_filter_useless_pass_leading_pass_with_number() -> None:
    result = "".join(
        autoflake.filter_useless_pass(
            """\
def func11():
    pass
    0, 11 / 2
    return 1
""",
        ),
    )

    expected = """\
def func11():
    0, 11 / 2
    return 1
"""

    assert result == expected


def test_filter_useless_pass_leading_pass_with_string() -> None:
    result = "".join(
        autoflake.filter_useless_pass(
            """\
def func11():
    pass
    'hello'
    return 1
""",
        ),
    )

    expected = """\
def func11():
    'hello'
    return 1
"""

    assert result == expected


def test_check() -> None:
    assert autoflake.check("import os")


def test_check_with_bad_syntax() -> None:
    assert autoflake.check("foo(") == []


def test_check_with_unicode() -> None:
    assert autoflake.check('print("∑")') == []

    assert autoflake.check("import os  # ∑")


def test_get_diff_text() -> None:
    result = "\n".join(
        autoflake.get_diff_text(["foo\n"], ["bar\n"], "").split("\n")[3:],
    )

    expected = """\
-foo
+bar
"""

    assert result == expected


def test_get_diff_text_without_newline() -> None:
    result = "\n".join(autoflake.get_diff_text(["foo"], ["foo\n"], "").split("\n")[3:])

    expected = """\
-foo
\\ No newline at end of file
+foo
"""

    assert result == expected


def test_is_literal_or_name() -> None:
    assert autoflake.is_literal_or_name("123") is True
    assert autoflake.is_literal_or_name("[1, 2, 3]") is True
    assert autoflake.is_literal_or_name("xyz") is True

    assert autoflake.is_literal_or_name("xyz.prop") is False
    assert autoflake.is_literal_or_name(" ") is False
    assert autoflake.is_literal_or_name(" 1") is False


def test_is_python_file(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
    root_dir: pathlib.Path,
) -> None:
    assert autoflake.is_python_file(str(root_dir / "autoflake.py")) is True

    with temporary_file("#!/usr/bin/env python", suffix="") as filename:
        assert autoflake.is_python_file(filename) is True

    with temporary_file("#!/usr/bin/python", suffix="") as filename:
        assert autoflake.is_python_file(filename) is True

    with temporary_file("#!/usr/bin/python3", suffix="") as filename:
        assert autoflake.is_python_file(filename) is True

    with temporary_file("#!/usr/bin/pythonic", suffix="") as filename:
        assert autoflake.is_python_file(filename) is False

    with temporary_file("###!/usr/bin/python", suffix="") as filename:
        assert autoflake.is_python_file(filename) is False

    assert autoflake.is_python_file(os.devnull) is False
    assert autoflake.is_python_file("/bin/bash") is False


@pytest.mark.parametrize(
    ("filename", "exclude", "expected"),
    [
        ("1.py", ["test*", "1*"], True),
        ("2.py", ["test*", "1*"], False),
        ("test/test.py", ["test/**.py"], True),
        ("test/auto_test.py", ["test/*_test.py"], True),
        ("test/auto_auto.py", ["test/*_test.py"], False),
    ],
)
def test_is_exclude_file(filename: str, exclude: Iterable[str], expected: bool) -> None:
    assert autoflake.is_exclude_file(filename, exclude) is expected


def test_match_file(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file("", suffix=".py", prefix=".") as filename:
        assert autoflake.match_file(filename, exclude=[]) is False

    assert autoflake.match_file(os.devnull, exclude=[]) is False

    with temporary_file("", suffix=".py", prefix="") as filename:
        assert autoflake.match_file(filename, exclude=[]) is True


def test_find_files(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "dir"
    target.mkdir(parents=True)

    (target / "a.py").write_text("")

    exclude = target / "ex"
    exclude.mkdir()
    (exclude / "b.py").write_text("")

    sub = exclude / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("")

    cwd = pathlib.Path.cwd()

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        files = list(
            autoflake.find_files(["dir"], True, [str(exclude)]),
        )
    finally:
        os.chdir(cwd)

    file_names = [os.path.basename(f) for f in files]
    assert "a.py" in file_names
    assert "b.py" in file_names
    assert "c.py" in file_names


def test_exclude(
    autoflake8_command: List[str],
    temporary_directory: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_directory(directory=".") as temp_directory:
        with open(os.path.join(temp_directory, "a.py"), "w") as output:
            output.write("import re\n")

        os.mkdir(os.path.join(temp_directory, "d"))
        with open(os.path.join(temp_directory, "d", "b.py"), "w") as output:
            output.write("import os\n")

        p = subprocess.Popen(
            autoflake8_command + [temp_directory, "--recursive", "--exclude=a*"],
            stdout=subprocess.PIPE,
        )
        stdout, _ = p.communicate()
        result = stdout.decode("utf-8")

        assert "import re" not in result
        assert "import os" in result
