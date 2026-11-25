"""Local-first, source-aware installation of the standalone PAH_Shared package.

Compatible version metadata is not sufficient: static assets may have changed
without a version bump. PAH setup/update prefers a local checkout and installs
it into the PAH venv. No network access is performed by this module.
"""
from __future__ import annotations

from importlib import metadata
import os
import json
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
    """Read PAH and checked-out module constraints without importing packages.

    Installed optional module extras must agree before any pip command is run.
    Code Analyzer's standalone requirements.txt is also a supported input.
    """
    constraints: list[str] = []
    projects = ("pypique", "code_analyzer", "ml_lab", "hsqa_dbn",
                "tech_documents", "reference_manager")
    paths = [root / "pyproject.toml"]
    paths += [root / "modules" / name / "pyproject.toml" for name in projects]
    paths.append(root / "modules" / "code_analyzer" / "requirements.txt")
    for path in paths:
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
        # PAH_Shared is a standalone sibling, not a pinned PAH Git submodule.
        # Prefer that tracked checkout over an older modules/ copy.
        root.parent / "PAH_Shared",
        root / "modules" / "pah_shared",
        root / "modules" / "PAH_Shared",
        root / "PAH_Shared",
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



# These two assets are the SU-02 interactive graph-view contract required by
# ML_Lab and pyPIQUE consumers of pah-shared 0.4.x. A version-only check could
# silently accept an old wheel without either file.
_GRAPH_ASSETS = ("interactive_graph_view.mjs", "interactive_graph_view.css")


def _graph_assets_required(version: str) -> bool:
    return _numbers(version) >= _numbers("0.4.0")


def _source_missing_graph_assets(source: Path) -> tuple[str, ...]:
    static = source / "src" / "pah_shared" / "static"
    return tuple(name for name in _GRAPH_ASSETS if not (static / name).is_file())


def _installed_missing_graph_assets(python: Path, root: Path) -> tuple[str, ...]:
    """Inspect the *target interpreter* import location, not the setup interpreter.

    Return every missing asset. An import error must not be mistaken for a
    complete install. No module-side functions are called.
    """
    snippet = (
        "import importlib.util,json,pathlib; "
        "spec=importlib.util.find_spec('pah_shared'); "
        "path=pathlib.Path(spec.origin).resolve().parent/'static' if spec and spec.origin else None; "
        "print(json.dumps([name for name in " + repr(_GRAPH_ASSETS) +
        " if path is None or not (path/name).is_file()]))"
    )
    result = subprocess.run([str(python), "-c", snippet], cwd=root,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SharedBootstrapError(
            "Cannot inspect PAH_Shared static assets in the PAH environment: " + result.stderr.strip()
        )
    try:
        missing = json.loads(result.stdout)
        if not isinstance(missing, list) or any(item not in _GRAPH_ASSETS for item in missing):
            raise ValueError("invalid static asset probe")
    except (ValueError, TypeError) as exc:
        raise SharedBootstrapError("Invalid PAH_Shared static asset probe output") from exc
    return tuple(missing)

def bootstrap_pah_shared(
    root: Path,
    python: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> str | None:
    """Reconcile PAH_Shared with checked-out source, or validate installed wheel.

    PAH does not fetch private repositories here. Source sync is a separate
    explicit update action. Reinstalling a local editable checkout on each
    setup/update is intentional: a package can gain browser files with NO
    change to its Python distribution version, and pip's old wheel may be stale.
    """
    constraints = declared_constraints(root)
    if not constraints:
        return None
    installed = _installed_version(python, root)
    candidates: list[str] = []
    for source in _sources(root):
        version = _source_version(source)
        if version is None:
            continue
        candidates.append(f"{source} ({version})")
        if not satisfies_all(version, constraints):
            continue
        if _graph_assets_required(version):
            missing = _source_missing_graph_assets(source)
            if missing:
                raise SharedBootstrapError(
                    f"Compatible PAH_Shared checkout {source} is incomplete: missing "
                    f"{', '.join(missing)}. Apply the SU-02 source update or pull "
                    "the completed PAH_Shared commit, then rerun setup/update."
                )
        print(f"Reconciling PAH_Shared {version} from local source: {source}")
        run(
            [python, "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", "-e", source],
            cwd=root,
        )
        installed = _installed_version(python, root)
        if installed is None or not satisfies_all(installed, constraints):
            raise SharedBootstrapError(
                "PAH_Shared installation did not satisfy the declared requirements: "
                f"{', '.join(constraints)}; found {installed or 'none'}."
            )
        if _graph_assets_required(installed):
            missing = _installed_missing_graph_assets(python, root)
            if missing:
                raise SharedBootstrapError(
                    f"PAH environment still lacks shared graph assets: {', '.join(missing)}. "
                    "Check the installed pah_shared import path and rebuild the local distribution."
                )
        return installed

    # An explicit override is authoritative: do not silently accept a wheel
    # when the user selected an incompatible or missing checkout.
    if os.environ.get("PAH_SHARED_SOURCE"):
        raise SharedBootstrapError(
            "no compatible local source at PAH_SHARED_SOURCE; "
            f"expected {', '.join(constraints)}, checked {', '.join(candidates) or 'none'}."
        )

    # An installed wheel is a valid offline fallback ONLY when no compatible
    # checked-out source exists and its required browser assets are present.
    if installed is not None and satisfies_all(installed, constraints):
        missing = _installed_missing_graph_assets(python, root) if _graph_assets_required(installed) else ()
        if missing:
            raise SharedBootstrapError(
                f"Installed PAH_Shared {installed} lacks {', '.join(missing)} and no compatible "
                "local checkout exists. Pull/update PAH_Shared or set PAH_SHARED_SOURCE."
            )
        print(f"✓ PAH_Shared {installed} installed (no compatible local source found)")
        return installed

    available = ", ".join(candidates) if candidates else "no installable local source found"
    raise SharedBootstrapError(
        "PAH_Shared has no compatible local source satisfying PAH/pyPIQUE requirements. "
        f"Constraints: {', '.join(constraints)}. Available: {available}; "
        f"installed: {installed or 'none'}. "
        "Pull a compatible sibling checkout or point PAH_SHARED_SOURCE to one. "
        "The vendored 0.3 snapshot cannot satisfy the 0.4 graph-view contract."
    )
