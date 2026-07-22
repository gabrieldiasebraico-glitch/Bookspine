#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
PORT="${1:-8765}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python 3 was not found. Install Python from https://www.python.org/downloads/ and run this script again." >&2
  exit 1
fi

"$PYTHON" -m vocab_mapper.viewer --port "$PORT" --open-browser
