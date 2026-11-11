"""Local-first bootstrap for the standalone PAH_Shared distribution.

This intentionally does not fetch or fabricate a missing Python distribution.
A checked-in v0.3 source snapshot provides an offline fallback for older PAH
installations that require pah-shared>=0.3,<0.4 but have no sibling checkout.
"""
from __future__ import annotations

from importlib import metadata
import os
from pathlib import Path
import re
import subprocess
from typing import Callable


class SharedBootstrapError(RuntimeError):
    """An explicit PAH_Shared requirement cannot be satisfied locally."""


_REQUIREMENT = re.compile(r"pah[-_]shared\s*((?:(?:>=|<=|==|!=|~=|>|<)\s*[0-9.*]+\s*,?\s*)*)", re.I)
_CONSTRAINT = re.compile(r"^(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+){0,3})$")
_VERSION = re.compile(r"^\d+(?:\.\d+){0,3}$")


def declared_constraints(root: Path) -> tuple[str, ...]:
    """Read host and optional pyPIQUE constraints without importing either package."""
    constraints: list[str] = []
    for path in (root / "pyproject.toml", root / "modules" / "pypique" / "pyproject.toml"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for match in _REQUIREMENT.finditer(text):
            constraint = match.group(1).strip().rstrip(",")
            if constraint and constraint not in constraints:
                constraints.append(constraint)
    return tuple(constraints)


def _numbers(value: str) -> tuple[int, ...]:
    if not _VERSION.fullmatch(value):
        raise SharedBootstrapError(f"Unsupported PAH_Shared version {value!r}; expected a stable numeric version.")
    parts = [int(n) for n in value.split(".")]
    return tuple((parts + [0] * 4)[:4])


def satisfies_all(version: str, constraints: tuple[str, ...]) -> bool:
    """Evaluate the stable numeric version comparisons used by PAH packaging."""
    actual = _numbers(version)
    for spec in constraints:
        for item in spec.split(","):
            item = item.strip()
            if not item:
                continue
            match = _CONSTRAINT.fullmatch(item)
            if match is None:
                raise SharedBootstrapError(
                    f"Unsupported pah-shared requirement {spec!r}; refusing to guess a compatible version."
                )
            op, expected_str = match.groups()
            expected = _numbers(expected_str)
            matched = {
                ">=": actual >= expected,
                "<=": actual <= expected,
                "==": actual == expected,
                "!=": actual != expected,
                ">": actual > expected,
                "<": actual < expected,
            }[op]
            if not matched:
                return False
    return True


def _source_version(source: Path) -> str | None:
    project_file = source / "pyproject.toml"
    if not project_file.is_file():
        return None
    in_project = False
    name: str | None = None
    version: str | None = None
    for raw in project_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if not in_project:
            continue
        match = re.fullmatch(r"(name|version)\s*=\s*['\"]([^'\"]+)['\"](?:\s*#.*)?", line)
        if match:
            if match.group(1) == "name":
                name = match.group(2)
            else:
                version = match.group(2)
    if name is None or name.lower().replace("_", "-") != "pah-shared":
        return None
    return version


def _sources(root: Path) -> tuple[Path, ...]:
    override = os.environ.get("PAH_SHARED_SOURCE")
    if override:
        return (Path(override).expanduser().resolve(),)
    return (
        root / "modules" / "pah_shared",
        root / "modules" / "PAH_Shared",
        root / "PAH_Shared",
        root.parent / "PAH_Shared",
        root / "vendor" / "PAH_Shared",
    )


def _installed_version(python: Path, root: Path) -> str | None:
    # Use the target venv, never the Python interpreter executing this setup.
    result = subprocess.run(
        [str(python), "-c", "from importlib.metadata import version, PackageNotFoundError; "
         "\ntry: print(version('pah-shared'))\nexcept PackageNotFoundError: pass"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SharedBootstrapError(
            "Cannot inspect pah-shared in the PAH virtual environment: " + result.stderr.strip()
        )
    return result.stdout.strip() or None


def bootstrap_pah_shared(
    root: Path,
    python: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> str | None:
    """Install a compatible local pah-shared before host and pyPIQUE extras.

    Return the compatible version, or None if neither package requires it.
    """
    constraints = declared_constraints(root)
    if not constraints:
        return None
    installed = _installed_version(python, root)
    if installed is not None and satisfies_all(installed, constraints):
        print(f"✓ PAH_Shared {installed} already installed in {python}")
        return installed

    candidates: list[str] = []
    for source in _sources(root):
        version = _source_version(source)
        if version is None:
            continue
        candidates.append(f"{source} ({version})")
        if not satisfies_all(version, constraints):
            continue
        print(f"Bootstrapping PAH_Shared {version} from local source: {source}")
        run(
            [python, "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", "-e", source],
            cwd=root,
        )
        installed = _installed_version(python, root)
        if installed is None or not satisfies_all(installed, constraints):
            raise SharedBootstrapError(
                "PAH_Shared local install completed without a compatible distribution. "
                f"Expected {', '.join(constraints)}; found {installed or 'none'}."
            )
        return installed

    available = ", ".join(candidates) if candidates else "no installable local source found"
    raise SharedBootstrapError(
        "PAH_Shared is required before installing PAH/pyPIQUE, but no compatible local source exists. "
        f"Constraints: {', '.join(constraints)}. Available: {available}. "
        "Provide a compatible checkout via PAH_SHARED_SOURCE, or restore the vendored PAH_Shared directory."
    )
