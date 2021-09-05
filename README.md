# autoflake8

[![Build](https://github.com/fsouza/autoflake8/actions/workflows/main.yaml/badge.svg?branch=main)](https://github.com/fsouza/autoflake8/actions/workflows/main.yaml)

## Introduction

*autoflake8* removes unused imports and unused variables from Python code. It
makes use of [pyflakes](https://pypi.org/project/pyflakes/) to do this.

autoflake8 also removes useless ``pass`` statements.

It's a maintained fork of [autoflake](https://github.com/myint/autoflake).

## Example

Running autoflake8 on the below example::

```
$ autoflake8 --in-place --remove-unused-variables example.py
```

```python
import math
import re
import os
import random
import multiprocessing
import grp, pwd, platform
import subprocess, sys


def foo():
    from abc import ABCMeta, WeakSet
    try:
        import multiprocessing
        print(multiprocessing.cpu_count())
    except ImportError as exception:
        print(sys.version)
    return math.pi
```

Results in:

```python
import math
import sys


def foo():
    try:
        import multiprocessing
        print(multiprocessing.cpu_count())
    except ImportError:
        print(sys.version)
    return math.pi
```

## Installation

```
$ pip install --upgrade autoflake8
```

## Advanced usage

To remove unused variables, use the ``--remove-unused-variables`` option.

Below is the full listing of options::

```
％ poetry run autoflake8 --help
usage: autoflake [-h] [-c] [-r] [--exclude globs] [--expand-star-imports] [--remove-duplicate-keys] [--remove-unused-variables] [--version] [-v] [-i | -s] files [files ...]

positional arguments:
  files                 files to format

optional arguments:
  -h, --help            show this help message and exit
  -c, --check           return error code if changes are needed
  -r, --recursive       drill down directories recursively
  --exclude globs       exclude file/directory names that match these comma-separated globs
  --expand-star-imports
                        expand wildcard star imports with undefined names; this only triggers if there is only one star import in the file; this is skipped if there are any uses of `__all__` or `del` in the file
  --remove-duplicate-keys
                        remove all duplicate keys in objects
  --remove-unused-variables
                        remove unused variables
  --version             show program's version number and exit
  -v, --verbose         print more verbose logs (you can repeat `-v` to make it more verbose)
  -i, --in-place        make changes to files instead of printing diffs
  -s, --stdout          print changed text to stdout. defaults to true when formatting stdin, or to false otherwise
```


### Tests

To run the unit tests::

```
$ poetry run pytest
```

There is also a fuzz test, which runs against any collection of given Python
files. It tests autoflake8 against the files and checks how well it does by
running pyflakes on the file before and after. The test fails if the pyflakes
results change for the worse. (This is done in memory. The actual files are
left untouched.)::

```
$ poetry run scripts/test_fuzz.py
```

## Excluding specific lines

It might be the case that you have some imports for their side effects, even
if you are not using them directly in that file.

That is common, for example, in Flask based applications. In where you import
Python modules (files) that imported a main ``app``, to have them included in
the routes.

For example:

```python
from .endpoints import role, token, user, utils
```

To prevent that, without having to exclude the entire file, you can add a
``# noqa`` comment at the end of the line, like:

```python
from .endpoints import role, token, user, utils  # noqa
```

That line will instruct ``autoflake8`` to let that specific line as is.
