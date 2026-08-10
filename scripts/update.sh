#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
git pull
if [[ -f .gitmodules ]]; then
  git submodule update --init --recursive
fi
