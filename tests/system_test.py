import io
import subprocess
from contextlib import _GeneratorContextManager
from typing import Callable
from typing import List
from unittest import mock

import pytest

import autoflake


def test_diff(temporary_file: Callable[..., _GeneratorContextManager[str]]) -> None:
    with temporary_file(
        """\
import re
import os
import my_own_module
x = 1
""",
    ) as filename:
        output_file = io.StringIO()
        autoflake._main(
            argv=["my_fake_program", filename],
            standard_out=output_file,
            standard_error=None,
        )

        expected = """\
-import re
-import os
 import my_own_module
 x = 1
"""
        assert "\n".join(output_file.getvalue().split("\n")[3:]) == expected


def test_diff_with_nonexistent_file() -> None:
    output_file = io.StringIO()
    autoflake._main(
        argv=["my_fake_program", "nonexistent_file"],
        standard_out=output_file,
        standard_error=output_file,
    )

    assert "no such file" in output_file.getvalue().lower()


def test_diff_with_encoding_declaration(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
# coding: iso-8859-1
import re
import os
import my_own_module
x = 1
""",
    ) as filename:
        output_file = io.StringIO()
        autoflake._main(
            argv=["my_fake_program", filename],
            standard_out=output_file,
            standard_error=None,
        )
        expected = """\
 # coding: iso-8859-1
-import re
-import os
 import my_own_module
 x = 1
"""

        assert "\n".join(output_file.getvalue().split("\n")[3:]) == expected


def test_in_place(temporary_file: Callable[..., _GeneratorContextManager[str]]) -> None:
    with temporary_file(
        """\
import foo
x = foo
import subprocess
x()

try:
    import os
except ImportError:
    import os
""",
    ) as filename:
        output_file = io.StringIO()
        autoflake._main(
            argv=["my_fake_program", "--in-place", filename],
            standard_out=output_file,
            standard_error=None,
        )
        with open(filename) as f:
            expected = """\
import foo
x = foo
x()

try:
    pass
except ImportError:
    pass
"""

            assert f.read() == expected


def test_check_with_empty_file(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file("") as filename:
        output_file = io.StringIO()

        autoflake._main(
            argv=["my_fake_program", "--check", filename],
            standard_out=output_file,
            standard_error=None,
        )

        assert output_file.getvalue() == "No issues detected!\n"


def test_check_correct_file(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
import foo
x = foo.bar
print(x)
""",
    ) as filename:
        output_file = io.StringIO()

        autoflake._main(
            argv=["my_fake_program", "--check", filename],
            standard_out=output_file,
            standard_error=None,
        )

        assert output_file.getvalue() == "No issues detected!\n"


def test_check_useless_pass(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
import foo
x = foo
import subprocess
x()

try:
    pass
    import os
except ImportError:
    pass
    import os
    import sys
""",
    ) as filename:
        output_file = io.StringIO()

        with pytest.raises(SystemExit) as excinfo:
            autoflake._main(
                argv=["my_fake_program", "--check", filename],
                standard_out=output_file,
                standard_error=None,
            )

        assert excinfo.value.code == 1
        assert (
            output_file.getvalue() == f"{filename}: Unused imports/variables detected"
        )


def test_in_place_with_empty_file(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file("") as filename:
        output_file = io.StringIO()
        autoflake._main(
            argv=["my_fake_program", "--in-place", filename],
            standard_out=output_file,
            standard_error=None,
        )
        with open(filename) as f:
            assert f.read() == ""


def test_in_place_with_with_useless_pass(
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
import foo
x = foo
import subprocess
x()

try:
    pass
    import os
except ImportError:
    pass
    import os
    import sys
""",
    ) as filename:
        output_file = io.StringIO()
        autoflake._main(
            argv=["my_fake_program", "--in-place", filename],
            standard_out=output_file,
            standard_error=None,
        )
        with open(filename) as f:
            expected = """\
import foo
x = foo
x()

try:
    pass
except ImportError:
    pass
"""

            assert f.read() == expected


def test_with_missing_file() -> None:
    output_file = mock.Mock()
    ignore = mock.Mock()

    autoflake._main(
        argv=["my_fake_program", "--in-place", ".fake"],
        standard_out=output_file,
        standard_error=ignore,
    )

    output_file.write.assert_not_called()


def test_ignore_hidden_directories(
    temporary_directory: Callable[..., _GeneratorContextManager[str]],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_directory() as directory:
        with temporary_directory(
            prefix=".",
            directory=directory,
        ) as inner_directory:

            with temporary_file(
                """\
import re
import os
""",
                directory=inner_directory,
            ):

                output_file = io.StringIO()

                autoflake._main(
                    argv=["my_fake_program", "--recursive", directory],
                    standard_out=output_file,
                    standard_error=None,
                )

                assert output_file.getvalue().strip() == ""


def test_redundant_options() -> None:
    output_file = io.StringIO()
    autoflake._main(
        argv=["my_fake_program", "--remove-all", "--imports=blah", __file__],
        standard_out=output_file,
        standard_error=output_file,
    )

    assert "redundant" in output_file.getvalue()


def test_in_place_and_stdout() -> None:
    output_file = io.StringIO()
    with pytest.raises(SystemExit):
        autoflake._main(
            argv=["my_fake_program", "--in-place", "--stdout", __file__],
            standard_out=output_file,
            standard_error=output_file,
        )


def test_end_to_end(
    autoflake8_command: List[str],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
import fake_fake, fake_foo, fake_bar, fake_zoo
import re, os
x = os.sep
print(x)
""",
    ) as filename:
        process = subprocess.Popen(
            autoflake8_command + ["--imports=fake_foo,fake_bar", filename],
            stdout=subprocess.PIPE,
        )

        expected = """\
-import fake_fake, fake_foo, fake_bar, fake_zoo
-import re, os
+import fake_fake
+import fake_zoo
+import os
 x = os.sep
 print(x)
"""
        assert "\n".join(process.communicate()[0].decode().split("\n")[3:]) == expected


def test_end_to_end_with_remove_all_unused_imports(
    autoflake8_command: List[str],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
import fake_fake, fake_foo, fake_bar, fake_zoo
import re, os
x = os.sep
print(x)
""",
    ) as filename:
        process = subprocess.Popen(
            autoflake8_command + ["--remove-all", filename],
            stdout=subprocess.PIPE,
        )
        expected = """\
-import fake_fake, fake_foo, fake_bar, fake_zoo
-import re, os
+import os
 x = os.sep
 print(x)
"""

        assert "\n".join(process.communicate()[0].decode().split("\n")[3:]) == expected


def test_end_to_end_with_remove_duplicate_keys_multiple_lines(
    autoflake8_command: List[str],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
a = {
    'b': 456,
    'a': 123,
    'b': 7834,
    'a': 'wow',
    'b': 456,
    'c': 'hello',
    'c': 'hello2',
    'b': 'hiya',
}
print(a)
""",
    ) as filename:
        process = subprocess.Popen(
            autoflake8_command + ["--remove-duplicate-keys", filename],
            stdout=subprocess.PIPE,
        )
        expected = """\
 a = {
-    'b': 456,
-    'a': 123,
-    'b': 7834,
     'a': 'wow',
-    'b': 456,
-    'c': 'hello',
     'c': 'hello2',
     'b': 'hiya',
 }
"""

        assert "\n".join(process.communicate()[0].decode().split("\n")[3:]) == expected


def test_end_to_end_with_remove_duplicate_keys_and_other_errors(
    autoflake8_command: List[str],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
from math import *
print(sin(4))
a = { # Hello
    'b': 456,
    'a': 123,
    'b': 7834,
    'a': 'wow',
    'b': 456,
    'c': 'hello',
    'c': 'hello2',
    'b': 'hiya',
}
print(a)
""",
    ) as filename:
        process = subprocess.Popen(
            autoflake8_command + ["--remove-duplicate-keys", filename],
            stdout=subprocess.PIPE,
        )
        expected = """\
 from math import *
 print(sin(4))
 a = { # Hello
-    'b': 456,
-    'a': 123,
-    'b': 7834,
     'a': 'wow',
-    'b': 456,
-    'c': 'hello',
     'c': 'hello2',
     'b': 'hiya',
 }
"""

        assert "\n".join(process.communicate()[0].decode().split("\n")[3:]) == expected


def test_end_to_end_with_remove_duplicate_keys_tuple(
    autoflake8_command: List[str],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
) -> None:
    with temporary_file(
        """\
a = {
    (0,1): 1,
    (0, 1): 'two',
    (0,1): 3,
}
print(a)
""",
    ) as filename:
        process = subprocess.Popen(
            autoflake8_command + ["--remove-duplicate-keys", filename],
            stdout=subprocess.PIPE,
        )

        result = "\n".join(process.communicate()[0].decode().split("\n")[3:])
        expected = """\
 a = {
-    (0,1): 1,
-    (0, 1): 'two',
     (0,1): 3,
 }
 print(a)
"""

        assert result == expected


def test_end_to_end_with_error(
    autoflake8_command: List[str],
    temporary_file: Callable[..., _GeneratorContextManager[str]],
):
    with temporary_file(
        """\
import fake_fake, fake_foo, fake_bar, fake_zoo
import re, os
x = os.sep
print(x)
""",
    ) as filename:
        process = subprocess.Popen(
            autoflake8_command
            + ["--imports=fake_foo,fake_bar", "--remove-all", filename],
            stderr=subprocess.PIPE,
        )

        _, stderr = process.communicate()
        assert "redundant" in stderr.decode()


def test_end_to_end_from_stdin(
    autoflake8_command: List[str],
):
    stdin_data = b"""\
import fake_fake, fake_foo, fake_bar, fake_zoo
import re, os
x = os.sep
print(x)
"""
    process = subprocess.Popen(
        autoflake8_command + ["--remove-all", "-"],
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
    )

    stdout, _ = process.communicate(stdin_data)
    expected = """\
import os
x = os.sep
print(x)
"""

    assert stdout.decode() == expected


def test_end_to_end_from_stdin_with_in_place(autoflake8_command: List[str]):
    stdin_data = b"""\
import fake_fake, fake_foo, fake_bar, fake_zoo
import re, os, sys
x = os.sep
print(x)
"""
    process = subprocess.Popen(
        autoflake8_command + ["--remove-all", "--in-place", "-"],
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
    )

    stdout, _ = process.communicate(stdin_data)
    expected = """\
import os
x = os.sep
print(x)
"""

    assert stdout.decode() == expected
