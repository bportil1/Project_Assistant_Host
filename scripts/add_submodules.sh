#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <code-analyzer-url> <tech-documents-url> <reference-manager-url>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

git submodule add "$1" modules/code_analyzer
git submodule add "$2" modules/tech_documents
git submodule add "$3" modules/reference_manager

echo "Submodules added. Review .gitmodules, then commit it and the three module pointers."
