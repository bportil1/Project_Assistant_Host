#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON:-python3}"
exec "$PYTHON_BIN" -m pah.lifecycle --root "$ROOT" setup "$@"
