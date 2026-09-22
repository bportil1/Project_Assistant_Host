#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <ml-lab-git-url>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -e modules/ml_lab ]]; then
  echo "modules/ml_lab already exists; refusing to replace it." >&2
  exit 1
fi

git submodule add "$1" modules/ml_lab
echo "ML Lab submodule added. Run ./scripts/setup.sh, then review and commit .gitmodules plus the module pointer."
