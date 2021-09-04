import pytest

from autoflake8.pending_fix import get_line_ending


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (b"\n", b"\n"),
        (b"abc\n", b"\n"),
        (b"abc\t  \t\n", b"\t  \t\n"),
        (b"abc", b""),
        (b"", b""),
    ],
)
def test_get_line_ending(source: bytes, expected: bytes) -> None:
    assert get_line_ending(source) == expected
