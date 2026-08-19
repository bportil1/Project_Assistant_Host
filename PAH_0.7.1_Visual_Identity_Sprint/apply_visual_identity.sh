#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"
ROOT="$(cd "$ROOT" && pwd)"

repos=(
  "$ROOT"
  "$ROOT/modules/code_analyzer"
  "$ROOT/modules/tech_documents"
  "$ROOT/modules/reference_manager"
  "$ROOT/modules/reference_manager/modules/paper_searcher"
)
patches=(
  "$BUNDLE_DIR/patches/01-host.patch"
  "$BUNDLE_DIR/patches/02-code-analyzer.patch"
  "$BUNDLE_DIR/patches/03-document-workbench.patch"
  "$BUNDLE_DIR/patches/04-reference-manager.patch"
  "$BUNDLE_DIR/patches/05-research-search.patch"
)
labels=(
  "PAH host"
  "Code Analyzer"
  "Document Workbench"
  "Reference Manager"
  "Research Search"
)

for i in "${!repos[@]}"; do
  if [[ ! -e "${repos[$i]}/.git" ]]; then
    echo "Missing Git repository for ${labels[$i]}: ${repos[$i]}" >&2
    exit 1
  fi
  echo "Checking ${labels[$i]}..."
  git -C "${repos[$i]}" apply --check "${patches[$i]}"
done

echo "All checks passed. Applying visual identity sprint..."
for i in "${!repos[@]}"; do
  git -C "${repos[$i]}" apply "${patches[$i]}"
  echo "Applied ${labels[$i]}"
done

echo
echo "PAH 0.7.1 visual identity changes applied."
echo "Run: python3 -m pytest -q"
echo "Then inspect git status separately in the host and each modified submodule before committing."
