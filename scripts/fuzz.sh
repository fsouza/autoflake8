#!/usr/bin/env bash

set -eu

ROOT_DIR=$(cd "$(dirname "${0}")/.." && pwd -P)

poetry run python -c 'import sys; [print(p, end="\0") for p in sys.path]' | xargs -0 -I @ bash -c 'dir="@"; if [ -z "${dir}" ]; then dir=.; fi; find "${dir}" -name \*.py -type f 2>/dev/null' | poetry run python "${ROOT_DIR}"/scripts/test_fuzz.py --num-workers "$(nproc)" "${@}"
