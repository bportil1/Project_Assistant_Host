from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO


class OverleafImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class OverleafProjectSummary:
    root: Path
    likely_main: str | None
    tex_files: tuple[str, ...]
    bib_files: tuple[str, ...]
    figure_files: tuple[str, ...]
    support_files: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "root": str(self.root),
            "likely_main": self.likely_main,
            "tex_files": list(self.tex_files),
            "bib_files": list(self.bib_files),
            "figure_files": list(self.figure_files),
            "support_files": list(self.support_files),
            "counts": {
                "tex": len(self.tex_files),
                "bib": len(self.bib_files),
                "figures": len(self.figure_files),
                "support": len(self.support_files),
            },
        }


class OverleafImportService:
    """Local Overleaf-source import helpers.

    The ZIP path is intentionally Git-agnostic and network-free. Git-backed
    acquisition is coordinated by PAH's existing Git service; this class only
    inspects the resulting local project so both acquisition paths return the
    same document-oriented summary.
    """

    _FIGURE_EXTENSIONS = {
        ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".eps", ".ps",
        ".tif", ".tiff", ".webp",
    }
    _SUPPORT_EXTENSIONS = {".cls", ".sty", ".bst", ".bbx", ".cbx", ".def"}
    _IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
    _MAX_ARCHIVE_FILES = 20_000
    _MAX_UNCOMPRESSED_BYTES = 1_073_741_824  # 1 GiB safety ceiling.
    _MAX_TEX_INSPECTION_BYTES = 1_048_576

    def __init__(self) -> None:
        self._sync_events: dict[tuple[str, str], dict[str, str]] = {}

    @staticmethod
    def is_overleaf_remote(remote: dict) -> bool:
        name = str(remote.get("name") or "").strip().lower()
        urls = [str(remote.get("fetch_url") or ""), str(remote.get("push_url") or "")]
        return name == "overleaf" or any("overleaf.com" in url.lower() for url in urls)

    def recognized_remotes(self, remotes: list[dict]) -> list[dict]:
        return [dict(remote) for remote in remotes if self.is_overleaf_remote(remote)]

    def select_remote(self, remotes: list[dict], requested: str | None = None) -> str | None:
        candidates = self.recognized_remotes(remotes)
        known = {str(item.get("name")) for item in candidates}
        requested_name = str(requested or "").strip()
        if requested_name:
            if requested_name not in known:
                raise OverleafImportError(f"Git remote is not recognized as an Overleaf remote: {requested_name}")
            return requested_name
        if len(candidates) == 1:
            return str(candidates[0].get("name"))
        if "overleaf" in known:
            return "overleaf"
        return None

    def record_sync_event(self, root: str | Path, remote: str, action: str) -> str:
        key = (str(Path(root).resolve()), str(remote))
        stamp = datetime.now(timezone.utc).isoformat()
        row = self._sync_events.setdefault(key, {})
        row[str(action)] = stamp
        if action in {"fetch", "pull"}:
            row["fetch"] = stamp
        return stamp

    def sync_events(self, root: str | Path, remote: str | None) -> dict[str, str | None]:
        if not remote:
            return {"last_fetch_at": None, "last_pull_at": None, "last_push_at": None}
        row = self._sync_events.get((str(Path(root).resolve()), str(remote)), {})
        return {
            "last_fetch_at": row.get("fetch"),
            "last_pull_at": row.get("pull"),
            "last_push_at": row.get("push"),
        }

    def import_zip(self, stream: BinaryIO, destination: str | Path, *, filename: str = "project.zip") -> dict:
        dest = self._validate_destination(destination)
        name = str(filename or "").strip()
        if name and not name.lower().endswith(".zip"):
            raise OverleafImportError("Overleaf source import expects a .zip archive.")

        staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}.pah-overleaf-", dir=str(dest.parent)))
        try:
            try:
                with zipfile.ZipFile(stream) as archive:
                    members = self._validated_members(archive)
                    self._extract_members(archive, members, staging)
            except zipfile.BadZipFile as exc:
                raise OverleafImportError("The selected file is not a valid ZIP archive.") from exc

            if not any(staging.iterdir()):
                raise OverleafImportError("The ZIP archive does not contain any project files.")

            if dest.exists():
                # _validate_destination only permits an existing empty directory.
                dest.rmdir()
            os.replace(staging, dest)
            staging = None
            return {
                "acquisition_mode": "zip",
                "source_name": name or "project.zip",
                "destination": str(dest),
                "project": self.inspect_project(dest),
            }
        finally:
            if staging is not None and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def inspect_project(self, root: str | Path) -> dict:
        project_root = Path(root).expanduser().resolve()
        if not project_root.exists() or not project_root.is_dir():
            raise OverleafImportError(f"Imported project directory does not exist: {project_root}")

        tex: list[str] = []
        bib: list[str] = []
        figures: list[str] = []
        support: list[str] = []
        for item in sorted(project_root.rglob("*")):
            if not item.is_file():
                continue
            relative_path = item.relative_to(project_root)
            if any(part in self._IGNORED_DIRS for part in relative_path.parts[:-1]):
                continue
            rel = relative_path.as_posix()
            suffix = item.suffix.lower()
            if suffix == ".tex":
                tex.append(rel)
            elif suffix == ".bib":
                bib.append(rel)
            elif suffix in self._FIGURE_EXTENSIONS:
                figures.append(rel)
            elif suffix in self._SUPPORT_EXTENSIONS:
                support.append(rel)

        summary = OverleafProjectSummary(
            root=project_root,
            likely_main=self._likely_main(project_root, tex),
            tex_files=tuple(tex),
            bib_files=tuple(bib),
            figure_files=tuple(figures),
            support_files=tuple(support),
        )
        return summary.as_dict()

    def _validate_destination(self, destination: str | Path) -> Path:
        raw = str(destination).strip()
        if not raw:
            raise OverleafImportError("Choose a destination directory for the imported project.")
        dest = Path(raw).expanduser().resolve()
        if not dest.parent.exists() or not dest.parent.is_dir():
            raise OverleafImportError(f"Import destination parent does not exist: {dest.parent}")
        if dest.exists():
            if not dest.is_dir():
                raise OverleafImportError("Import destination exists and is not a directory.")
            if any(dest.iterdir()):
                raise OverleafImportError("Import destination already exists and is not empty.")
        return dest

    def _validated_members(self, archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
        infos = archive.infolist()
        if len(infos) > self._MAX_ARCHIVE_FILES:
            raise OverleafImportError("The ZIP archive contains too many entries to import safely.")
        total_size = sum(max(0, int(info.file_size)) for info in infos)
        if total_size > self._MAX_UNCOMPRESSED_BYTES:
            raise OverleafImportError("The ZIP archive expands beyond PAH's 1 GiB import safety limit.")

        validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info in infos:
            raw = str(info.filename or "").replace("\\", "/")
            if not raw:
                continue
            path = PurePosixPath(raw)
            parts = tuple(part for part in path.parts if part not in {"", "."})
            if not parts:
                continue
            if path.is_absolute() or ".." in parts or (parts and ":" in parts[0]):
                raise OverleafImportError(f"Unsafe path in ZIP archive: {raw}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise OverleafImportError(f"Symbolic links are not imported from ZIP archives: {raw}")
            validated.append((info, PurePosixPath(*parts)))
        return validated

    def _extract_members(
        self,
        archive: zipfile.ZipFile,
        members: list[tuple[zipfile.ZipInfo, PurePosixPath]],
        staging: Path,
    ) -> None:
        root = staging.resolve()
        for info, relative in members:
            target = (staging / Path(*relative.parts)).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise OverleafImportError(f"Unsafe path in ZIP archive: {info.filename}") from exc
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    def _likely_main(self, root: Path, tex_files: list[str]) -> str | None:
        if not tex_files:
            return None
        scored: list[tuple[int, str]] = []
        for relative in tex_files:
            path = root / relative
            score = 0
            name = path.name.lower()
            stem = path.stem.lower()
            if name == "main.tex":
                score += 120
            if stem in {"thesis", "paper", "manuscript", "article", "report"}:
                score += 30
            try:
                with path.open("rb") as handle:
                    text = handle.read(self._MAX_TEX_INSPECTION_BYTES).decode("utf-8", errors="ignore")
            except OSError:
                text = ""
            if "\\documentclass" in text:
                score += 80
            if "\\begin{document}" in text:
                score += 40
            if "\\bibliography" in text or "\\addbibresource" in text:
                score += 8
            # Prefer a shallower entry point when otherwise equally plausible.
            score -= relative.count("/")
            scored.append((score, relative))
        scored.sort(key=lambda item: (-item[0], item[1].lower()))
        return scored[0][1]
