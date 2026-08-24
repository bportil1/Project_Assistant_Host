#!/usr/bin/env python3
"""Provision every browser dependency used by PAH and its installed modules."""
from __future__ import annotations

import sys

from pah.lifecycle import main


if __name__ == "__main__":
    raise SystemExit(main(["assets", *sys.argv[1:]]))
