#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .gitmodules ]]; then
  git submodule update --init --recursive
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .

install_module() {
  local module="$1"
  if [[ ! -d "$module" ]]; then
    return 0
  fi
  if [[ -f "$module/pyproject.toml" || -f "$module/setup.py" ]]; then
    echo "Installing $module"
    python -m pip install -e "$module"
  elif [[ -n "$(find "$module" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    echo "WARNING: $module exists but is not an installable Python package (missing pyproject.toml/setup.py)." >&2
  fi
}

install_module modules/code_analyzer
install_module modules/tech_documents
install_module modules/reference_manager

echo
printf 'PAH ready. Start with:\n  source .venv/bin/activate\n  python run.py /path/to/project\n'
