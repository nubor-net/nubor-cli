#!/usr/bin/env bash
# Builds the standalone binary into dist/ and smoke-tests it.
# Run from a venv that has the project and requirements-dev.txt installed.
set -euo pipefail
cd "$(dirname "$0")/.."

pyinstaller --clean nubor.spec

BIN=dist/nubor
[ -f dist/nubor.exe ] && BIN=dist/nubor.exe
"$BIN" --help >/dev/null
echo "$BIN built and smoke-tested."
