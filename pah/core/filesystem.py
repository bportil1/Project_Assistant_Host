from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


class FileSystemError(ValueError):
    pass


_TEXT_EXTENSIONS = {
    ".py", ".pyi", ".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".csv", ".tsv", ".tex", ".bib", ".diagram",
    ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh",
    ".bash", ".zsh", ".fish", ".sql", ".xml", ".svg", ".rst", ".env", ".gitignore",
    ".dockerignore", ".gitattributes", ".properties", ".gradle", ".java", ".c", ".h",
    ".cpp", ".hpp", ".rs", ".go", ".ex", ".exs",
}


class FileSystemService:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise FileSystemError(f"Invalid workspace root: {self.root}")

    def resolve(self, relative: str | Path = ".", *, must_exist: bool = False) -> Path:
        raw = Path(relative)
        if raw.is_absolute():
            candidate = raw.resolve()
        else:
            candidate = (self.root / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise FileSystemError("Path escapes the workspace root.") from exc
        if must_exist and not candidate.exists():
            raise FileSystemError(f"Path does not exist: {relative}")
        return candidate

    def relative(self, path: Path) -> str:
        rel = path.resolve().relative_to(self.root)
        return "." if str(rel) == "." else rel.as_posix()

    def tree(self, *, max_entries: int = 6000) -> list[dict[str, Any]]:
        count = 0

        def walk(directory: Path) -> list[dict[str, Any]]:
            nonlocal count
            result: list[dict[str, Any]] = []
            try:
                children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                return result
            for child in children:
                if count >= max_entries:
                    break
                if child.name == ".git":
                    continue
                count += 1
                item = {
                    "name": child.name,
                    "path": self.relative(child),
                    "type": "dir" if child.is_dir() else "file",
                }
                if child.is_dir():
                    item["children"] = walk(child)
                else:
                    try:
                        item["size"] = child.stat().st_size
                    except OSError:
                        item["size"] = None
                result.append(item)
            return result

        return walk(self.root)

    def read_text(self, relative: str) -> dict[str, Any]:
        path = self.resolve(relative, must_exist=True)
        if not path.is_file():
            raise FileSystemError("Only files can be opened in the editor.")
        if path.stat().st_size > 5 * 1024 * 1024:
            raise FileSystemError("File is larger than the 5 MB editor limit.")
        try:
            data = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FileSystemError("This file is not UTF-8 text and cannot be opened in the lightweight editor.") from exc
        return {"path": self.relative(path), "content": data, "mtime_ns": path.stat().st_mtime_ns}

    def write_text(self, relative: str, content: str) -> dict[str, Any]:
        path = self.resolve(relative)
        if path.exists() and not path.is_file():
            raise FileSystemError("Cannot save text over a directory.")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.pah-tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
        return {"path": self.relative(path), "mtime_ns": path.stat().st_mtime_ns}

    def create(self, relative: str, kind: str) -> dict[str, str]:
        path = self.resolve(relative)
        if path.exists():
            raise FileSystemError("A file or directory already exists at that path.")
        if kind == "dir":
            path.mkdir(parents=True, exist_ok=False)
        elif kind == "file":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=False)
        else:
            raise FileSystemError("kind must be 'file' or 'dir'.")
        return {"path": self.relative(path), "type": kind}

    def rename(self, relative: str, new_name: str) -> dict[str, str]:
        if not new_name or new_name in {".", ".."} or "/" in new_name or "\\" in new_name:
            raise FileSystemError("New name must be a single valid file or directory name.")
        source = self.resolve(relative, must_exist=True)
        target = self.resolve(source.parent.relative_to(self.root) / new_name)
        if target.exists():
            raise FileSystemError("The destination already exists.")
        source.rename(target)
        return {"old_path": relative, "path": self.relative(target)}

    def move(self, relative: str, destination: str) -> dict[str, str]:
        source = self.resolve(relative, must_exist=True)
        target = self.resolve(destination)
        if target.exists() and target.is_dir():
            target = target / source.name
        target = self.resolve(target.relative_to(self.root) if target.is_absolute() else target)
        if target.exists():
            raise FileSystemError("The destination already exists.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return {"old_path": relative, "path": self.relative(target)}

    def delete(self, relative: str) -> None:
        target = self.resolve(relative, must_exist=True)
        if target == self.root:
            raise FileSystemError("The workspace root cannot be deleted.")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def language_for(self, relative: str) -> str:
        name = Path(relative).name.lower()
        suffix = Path(relative).suffix.lower()
        if suffix in {".py", ".pyi"}: return "python"
        if suffix in {".md", ".markdown"}: return "markdown"
        if suffix in {".json", ".jsonl"}: return "json"
        if suffix in {".yaml", ".yml"}: return "yaml"
        if suffix in {".tex", ".bib"}: return "latex"
        if suffix in {".sh", ".bash", ".zsh"}: return "shell"
        if suffix in {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"}: return "javascript"
        if suffix in {".html", ".htm", ".xml", ".svg"}: return "markup"
        if suffix == ".css": return "css"
        if suffix == ".toml": return "toml"
        if name in {"requirements.txt", "dockerfile", "makefile", ".gitignore", ".dockerignore"}: return "text"
        return "text"
