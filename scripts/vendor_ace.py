#!/usr/bin/env python3
"""Vendor a pinned Ace build for PAH's fully local workspace editor.

This is an explicit install/development step. PAH never downloads editor assets at
runtime. Release archives should include pah/web/static/vendor/ace so end users do
not need network access.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ACE_VERSION = "1.44.0"
ACE_ARCHIVE_URL = f"https://github.com/ajaxorg/ace-builds/archive/refs/tags/v{ACE_VERSION}.zip"

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "pah" / "web" / "static" / "vendor" / "ace"


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"Unsafe path in Ace archive: {name}")
    return path


def install(*, force: bool = False) -> Path:
    if (DESTINATION / "ace.js").exists() and not force:
        print(f"Ace {ACE_VERSION} already appears to be vendored at {DESTINATION}")
        return DESTINATION

    with tempfile.TemporaryDirectory(prefix="pah-ace-") as temp_dir:
        archive_path = Path(temp_dir) / f"ace-builds-{ACE_VERSION}.zip"
        request = urllib.request.Request(
            ACE_ARCHIVE_URL,
            headers={"User-Agent": "Project-Assistant-Host/Ace-Vendor"},
        )
        print(f"Downloading Ace {ACE_VERSION} from the official ace-builds repository...")
        with urllib.request.urlopen(request, timeout=60) as response, archive_path.open("wb") as target:
            shutil.copyfileobj(response, target)

        staging = Path(temp_dir) / "ace"
        staging.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            ace_entries = [name for name in names if name.endswith("/src-min-noconflict/ace.js")]
            if len(ace_entries) != 1:
                raise RuntimeError("Pinned Ace archive does not contain one src-min-noconflict/ace.js")
            source_prefix = ace_entries[0][:-len("ace.js")]
            archive_prefix = source_prefix[:-len("src-min-noconflict/")]
            for info in archive.infolist():
                path = _safe_member_path(info.filename)
                name = path.as_posix()
                if not name.startswith(source_prefix) or info.is_dir():
                    continue
                relative = PurePosixPath(name[len(source_prefix):])
                if not relative.parts:
                    continue
                output = staging.joinpath(*relative.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target)

            license_name = archive_prefix + "LICENSE"
            if license_name in names:
                with archive.open(license_name) as source, (staging / "LICENSE").open("wb") as target:
                    shutil.copyfileobj(source, target)

        (staging / "PAH_VENDOR_VERSION.txt").write_text(
            f"Ace build: {ACE_VERSION}\nSource: {ACE_ARCHIVE_URL}\nDistribution: src-min-noconflict\n",
            encoding="utf-8",
        )
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, DESTINATION)

    print(f"Vendored Ace {ACE_VERSION} into {DESTINATION}")
    print("PAH can now run the workspace editor without contacting a CDN or package registry.")
    return DESTINATION


def main() -> None:
    parser = argparse.ArgumentParser(description="Vendor the pinned Ace editor build used by PAH")
    parser.add_argument("--force", action="store_true", help="Replace an existing vendored Ace directory")
    args = parser.parse_args()
    install(force=args.force)


if __name__ == "__main__":
    main()
