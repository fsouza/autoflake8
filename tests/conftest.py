import contextlib
import os
import pathlib
import shutil
import sys
import tempfile
from contextlib import _GeneratorContextManager
from typing import Callable
from typing import IO
from typing import Iterator
from typing import List

import pytest


@pytest.fixture
def temporary_file() -> Callable[[str, str, str, str], _GeneratorContextManager[str]]:
    @contextlib.contextmanager
    def _fn(
        contents: str,
        directory: str = ".",
        suffix: str = ".py",
        prefix: str = "",
    ) -> Iterator[str]:
        f = tempfile.NamedTemporaryFile(
            suffix=suffix,
            prefix=prefix,
            dir=directory,
            delete=False,
        )
        try:
            f.write(contents.encode())
            f.close()
            yield f.name
        finally:
            os.remove(f.name)

    return _fn


@pytest.fixture
def temporary_directory() -> Callable[[str, str], _GeneratorContextManager[str]]:
    @contextlib.contextmanager
    def _fn(
        directory=".",
        prefix="tmp.",
    ) -> Iterator[str]:
        dir_name = tempfile.mkdtemp(prefix=prefix, dir=directory)
        try:
            yield dir_name
        finally:
            shutil.rmtree(dir_name)

    return _fn


@pytest.fixture
def root_dir() -> pathlib.Path:
    return pathlib.Path(__file__).parent.parent


@pytest.fixture
def autoflake8_command(root_dir: pathlib.Path) -> List[str]:
    return [sys.executable, str(root_dir / "autoflake.py")]


@pytest.fixture
def devnull() -> Iterator[IO[str]]:
    with open(os.devnull, "r+") as f:
        yield f
