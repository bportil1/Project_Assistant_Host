"""Unified setup, update, asset provisioning, and readiness diagnostics for PAH."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence
import urllib.error
import urllib.request

from .components import (
    BROWSER_ASSETS,
    GIT_COMPONENTS,
    PYTHON_COMPONENTS,
    SYSTEM_TOOLS,
    BrowserAsset,
    GitComponent,
    PythonComponent,
)

MIN_PYTHON = (3, 10)
ROOT = Path(__file__).resolve().parents[1]


class LifecycleError(RuntimeError):
    pass


def _run(
    args: Iterable[str | os.PathLike[str]],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [str(value) for value in args]
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
        env=env,
    )


def _python_ok() -> bool:
    return sys.version_info >= MIN_PYTHON


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _installable(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() or (path / "setup.py").is_file()


def _component_present(root: Path, component: PythonComponent) -> bool:
    path = (root / component.path).resolve()
    return path.is_dir() and _installable(path)


def _asset_present(root: Path, asset: BrowserAsset) -> bool:
    return all((root / marker).is_file() for marker in asset.markers)


def _submodule_state(root: Path) -> dict[str, str]:
    if not (root / ".git").exists() or not (root / ".gitmodules").is_file() or shutil.which("git") is None:
        return {}
    result = _run(["git", "submodule", "status", "--recursive"], cwd=root, check=False, capture=True)
    if result.returncode != 0:
        return {}
    states: dict[str, str] = {}
    for raw in result.stdout.splitlines():
        if not raw.strip():
            continue
        prefix = raw[0]
        body = raw[1:].strip() if prefix in "-+ U" else raw.strip()
        parts = body.split()
        if len(parts) < 2:
            continue
        path = parts[1]
        states[path] = {
            "-": "uninitialized",
            "+": "different_commit",
            "U": "conflict",
            " ": "recorded_commit",
        }.get(prefix, "recorded_commit")
    return states


def ensure_submodules(root: Path) -> None:
    if not (root / ".gitmodules").is_file():
        return
    if not (root / ".git").exists():
        print("\n== Modules / submodules ==")
        print("Source archive detected; using bundled module directories instead of Git submodule commands.")
        return
    if shutil.which("git") is None:
        raise LifecycleError("Git is required to initialize PAH modules and submodules.")
    print("\n== Modules / submodules ==")
    _run(["git", "submodule", "sync", "--recursive"], cwd=root)
    _run(["git", "submodule", "update", "--init", "--recursive"], cwd=root)


def ensure_venv(root: Path, *, python_executable: str = sys.executable) -> Path:
    python = _venv_python(root)
    if python.is_file():
        print(f"\n== Python environment ==\nUsing existing {python.relative_to(root)}")
        return python
    print("\n== Python environment ==")
    print("Creating .venv")
    _run([python_executable, "-m", "venv", ".venv"], cwd=root)
    if not python.is_file():
        raise LifecycleError("Virtual environment creation completed but its Python executable is missing.")
    return python


def install_python_components(root: Path, python: Path) -> None:
    print("\n== Python components ==")
    _run([python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=root)
    for component in PYTHON_COMPONENTS:
        if not _component_present(root, component):
            if component.required:
                raise LifecycleError(
                    f"{component.label} is missing or not installable at {component.path}. "
                    "Run git submodule update --init --recursive."
                )
            continue
        print(f"Installing {component.label}: {component.install_spec}")
        _run([python, "-m", "pip", "install", "-e", component.install_spec], cwd=root)


def provision_assets(root: Path, python: Path, *, force: bool = False) -> list[str]:
    print("\n== Browser assets ==")
    failures: list[str] = []
    for asset in BROWSER_ASSETS:
        if _asset_present(root, asset) and not force:
            print(f"✓ {asset.owner}: {asset.label}")
            continue
        script = root / asset.script
        if not script.is_file():
            message = f"{asset.owner}: provisioning script missing: {asset.script}"
            failures.append(message)
            print(f"✗ {message}")
            continue
        print(f"Provisioning {asset.owner}: {asset.label}")
        result = _run([python, script], cwd=root, check=False)
        if result.returncode != 0 or not _asset_present(root, asset):
            message = f"{asset.owner}: failed to provision {asset.label}"
            failures.append(message)
            print(f"✗ {message}")
        else:
            print(f"✓ {asset.owner}: {asset.label}")
    return failures


QUARTO_RELEASE_API = "https://api.github.com/repos/quarto-dev/quarto-cli/releases/latest"


def _package_manager() -> str | None:
    for key, command in (("apt", "apt-get"), ("dnf", "dnf"), ("pacman", "pacman"), ("brew", "brew")):
        if shutil.which(command):
            return key
    return None


def _privileged(command: Sequence[str]) -> list[str]:
    if os.name == "nt":
        raise LifecycleError("Automatic system-tool installation is not implemented for Windows.")
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() == 0:
        return list(command)
    sudo = shutil.which("sudo")
    if sudo:
        return [sudo, *command]
    raise LifecycleError("System package installation requires root privileges or sudo.")


def _install_package(package: str, *, manager: str, cwd: Path, apt_update: bool = False) -> None:
    if manager == "apt":
        if apt_update:
            _run(_privileged(["apt-get", "update"]), cwd=cwd)
        _run(_privileged(["apt-get", "install", "-y", package]), cwd=cwd)
        return
    if manager == "dnf":
        _run(_privileged(["dnf", "install", "-y", package]), cwd=cwd)
        return
    if manager == "pacman":
        _run(_privileged(["pacman", "-S", "--needed", "--noconfirm", package]), cwd=cwd)
        return
    if manager == "brew":
        _run(["brew", "install", package], cwd=cwd)
        return
    raise LifecycleError(f"No supported package manager is available to install {package}.")


def _quarto_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise LifecycleError(f"Automatic Quarto installation does not support architecture {machine!r}.")


def _select_quarto_asset(release: dict, *, manager: str, arch: str) -> dict:
    extension = {"apt": ".deb", "dnf": ".rpm"}.get(manager)
    if extension is None:
        raise LifecycleError(f"Automatic Quarto release-package installation is not supported with {manager}.")
    needle = f"linux-{arch}{extension}"
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if name.endswith(needle) and asset.get("browser_download_url"):
            return asset
    raise LifecycleError(f"Latest Quarto release does not contain a {needle} package.")


def _latest_quarto_asset(*, manager: str) -> dict:
    request = urllib.request.Request(
        QUARTO_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PAH-component-lifecycle",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            release = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"Unable to query the latest Quarto release: {exc}") from exc
    return _select_quarto_asset(release, manager=manager, arch=_quarto_arch())


def _download_release_asset(asset: dict, destination: Path) -> None:
    url = str(asset.get("browser_download_url") or "")
    if not url.startswith("https://"):
        raise LifecycleError("Quarto release asset URL was missing or not HTTPS.")
    request = urllib.request.Request(url, headers={"User-Agent": "PAH-component-lifecycle"})
    try:
        with urllib.request.urlopen(request, timeout=120.0) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (OSError, urllib.error.URLError) as exc:
        raise LifecycleError(f"Unable to download Quarto release asset: {exc}") from exc

    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        expected = digest.split(":", 1)[1].lower()
        hasher = hashlib.sha256()
        with destination.open("rb") as downloaded:
            for chunk in iter(lambda: downloaded.read(1024 * 1024), b""):
                hasher.update(chunk)
        actual = hasher.hexdigest().lower()
        if actual != expected:
            destination.unlink(missing_ok=True)
            raise LifecycleError("Downloaded Quarto package failed its published SHA-256 digest check.")


def _install_quarto(*, manager: str, cwd: Path) -> None:
    if manager == "brew":
        _run(["brew", "install", "--cask", "quarto"], cwd=cwd)
        return
    if manager not in {"apt", "dnf"}:
        raise LifecycleError(
            f"Automatic Quarto installation is not available for package manager {manager!r}."
        )
    asset = _latest_quarto_asset(manager=manager)
    name = str(asset.get("name") or ("quarto.deb" if manager == "apt" else "quarto.rpm"))
    with tempfile.TemporaryDirectory(prefix="pah-quarto-") as temp_dir:
        package = Path(temp_dir) / name
        print(f"Downloading Quarto package: {name}")
        _download_release_asset(asset, package)
        if manager == "apt":
            _run(_privileged(["apt-get", "install", "-y", str(package)]), cwd=cwd)
        else:
            _run(_privileged(["dnf", "install", "-y", str(package)]), cwd=cwd)


def provision_system_tools(root: Path) -> list[str]:
    """Best-effort installation for optional tools PAH can provision safely."""
    print("\n== Optional feature tools ==")
    manager = _package_manager()
    failures: list[str] = []
    apt_updated = False
    for tool in SYSTEM_TOOLS:
        if not tool.auto_install:
            continue
        if shutil.which(tool.command):
            print(f"✓ {tool.label}")
            continue
        print(f"Installing {tool.label} ({tool.affects})")
        try:
            if tool.installer == "package" and tool.package_name:
                if manager is None:
                    raise LifecycleError("no supported package manager found")
                _install_package(
                    tool.package_name,
                    manager=manager,
                    cwd=root,
                    apt_update=(manager == "apt" and not apt_updated),
                )
                if manager == "apt":
                    apt_updated = True
            elif tool.installer == "quarto_release":
                if manager is None:
                    raise LifecycleError("no supported package manager found")
                _install_quarto(manager=manager, cwd=root)
            else:
                raise LifecycleError("no automatic installer is registered")
        except (LifecycleError, subprocess.CalledProcessError) as exc:
            message = f"{tool.label}: {exc}"
            failures.append(message)
            print(f"! {message}")
            continue
        if shutil.which(tool.command):
            print(f"✓ {tool.label}")
        else:
            message = f"{tool.label}: installer completed but {tool.command!r} is still unavailable on PATH"
            failures.append(message)
            print(f"! {message}")
    if failures:
        print("Optional tool installation had problems; PAH required components can still be used.")
    return failures


def _import_status(python: Path, imports: tuple[str, ...], *, root: Path) -> tuple[bool, list[str]]:
    payload = json.dumps(imports)
    code = (
        "import importlib.util,json,sys; "
        f"names=json.loads({payload!r}); "
        "missing=[name for name in names if importlib.util.find_spec(name) is None]; "
        "print(json.dumps(missing)); sys.exit(1 if missing else 0)"
    )
    result = _run([python, "-c", code], cwd=root, check=False, capture=True)
    try:
        missing = json.loads((result.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError:
        missing = list(imports)
    return result.returncode == 0, [str(value) for value in missing]


def _entry_point_status(
    python: Path,
    requirements: tuple[tuple[str, str], ...],
    *,
    root: Path,
) -> tuple[bool, list[str]]:
    if not requirements:
        return True, []
    payload = json.dumps(requirements)
    code = (
        "import importlib.metadata,json,sys\n"
        f"requirements=json.loads({payload!r})\n"
        "eps=importlib.metadata.entry_points()\n"
        "missing=[]\n"
        "for group,name in requirements:\n"
        "    matches=list(eps.select(group=group,name=name)) if hasattr(eps,'select') else [ep for ep in eps.get(group,[]) if ep.name==name]\n"
        "    if not matches:\n"
        "        missing.append(f'{group}:{name}')\n"
        "        continue\n"
        "    try:\n"
        "        matches[0].load()\n"
        "    except Exception as exc:\n"
        "        missing.append(f'{group}:{name} (load failed: {type(exc).__name__}: {exc})')\n"
        "print(json.dumps(missing))\n"
        "sys.exit(1 if missing else 0)"
    )
    result = _run([python, "-c", code], cwd=root, check=False, capture=True)
    try:
        missing = json.loads((result.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError:
        missing = [f"{group}:{name}" for group, name in requirements]
    return result.returncode == 0, [str(value) for value in missing]


def doctor_report(root: Path) -> dict:
    venv_python = _venv_python(root)
    submodules = _submodule_state(root)
    report: dict = {
        "root": str(root),
        "ok": True,
        "python": {
            "ok": _python_ok(),
            "version": ".".join(str(value) for value in sys.version_info[:3]),
            "minimum": ".".join(str(value) for value in MIN_PYTHON),
        },
        "venv": {
            "ok": venv_python.is_file(),
            "path": str(venv_python.relative_to(root)) if venv_python.is_file() else ".venv",
        },
        "components": [],
        "assets": [],
        "tools": [],
    }
    if not report["python"]["ok"] or not report["venv"]["ok"]:
        report["ok"] = False

    for component in PYTHON_COMPONENTS:
        present = _component_present(root, component)
        item = {
            "key": component.key,
            "label": component.label,
            "path": component.path,
            "required": component.required,
            "source_present": present,
            "submodule_state": submodules.get(component.path),
            "python_ok": False,
            "missing_imports": [],
            "entry_points_ok": not component.pah_entry_points,
            "missing_entry_points": [],
        }
        if present and venv_python.is_file():
            item["python_ok"], item["missing_imports"] = _import_status(
                venv_python, component.imports, root=root
            )
            item["entry_points_ok"], item["missing_entry_points"] = _entry_point_status(
                venv_python, component.pah_entry_points, root=root
            )
        item["ok"] = bool(present and item["python_ok"] and item["entry_points_ok"])
        if component.required and not item["ok"]:
            report["ok"] = False
        report["components"].append(item)

    for asset in BROWSER_ASSETS:
        script_present = (root / asset.script).is_file()
        present = _asset_present(root, asset)
        item = {
            "key": asset.key,
            "label": asset.label,
            "owner": asset.owner,
            "required": asset.required,
            "ok": present,
            "script_present": script_present,
            "script": asset.script,
            "missing": [marker for marker in asset.markers if not (root / marker).is_file()],
        }
        if asset.required and not present:
            report["ok"] = False
        report["assets"].append(item)

    for tool in SYSTEM_TOOLS:
        path = shutil.which(tool.command)
        item = {
            "key": tool.key,
            "label": tool.label,
            "required": tool.required,
            "ok": path is not None,
            "path": path,
            "affects": tool.affects,
            "auto_install": tool.auto_install,
        }
        if tool.required and path is None:
            report["ok"] = False
        report["tools"].append(item)
    return report


def _status_mark(ok: bool, *, optional: bool = False) -> str:
    if ok:
        return "✓"
    return "!" if optional else "✗"


def print_doctor(report: dict) -> None:
    print("PAH Component Doctor")
    print("=" * 72)
    python = report["python"]
    print("\nHOST")
    print(f"{_status_mark(python['ok'])} Python {python['version']} (requires >= {python['minimum']})")
    print(f"{_status_mark(report['venv']['ok'])} Virtual environment: {report['venv']['path']}")

    print("\nCOMPONENTS")
    for item in report["components"]:
        mark = _status_mark(item["ok"], optional=not item["required"])
        detail: list[str] = []
        if not item["source_present"]:
            detail.append(f"source missing at {item['path']}")
        elif not report["venv"]["ok"]:
            detail.append("virtual environment not ready")
        elif not item["python_ok"]:
            detail.append("missing Python: " + ", ".join(item["missing_imports"]))
        if not item.get("entry_points_ok", True):
            detail.append("PAH discovery: " + ", ".join(item["missing_entry_points"]))
        if item.get("submodule_state") in {"uninitialized", "conflict", "different_commit"}:
            detail.append(f"submodule={item['submodule_state']}")
        suffix = f" — {'; '.join(detail)}" if detail else ""
        print(f"{mark} {item['label']}{suffix}")

    print("\nBROWSER ASSETS")
    for item in report["assets"]:
        mark = _status_mark(item["ok"], optional=not item["required"])
        if item["ok"]:
            print(f"{mark} {item['owner']}: {item['label']}")
        elif not item["script_present"]:
            print(f"{mark} {item['owner']}: {item['label']} — provisioning script missing ({item['script']})")
        else:
            print(f"{mark} {item['owner']}: {item['label']} — missing local asset")

    print("\nOPTIONAL / SYSTEM TOOLS")
    for item in report["tools"]:
        mark = _status_mark(item["ok"], optional=not item["required"])
        suffix = item["path"] if item["ok"] else f"not installed; affects {item['affects']}"
        if not item["ok"] and item.get("auto_install"):
            suffix += "; setup can install this automatically"
        print(f"{mark} {item['label']} — {suffix}")

    if report["ok"]:
        print("\n✓ PAH required components are ready.")
    else:
        print("\n✗ PAH has missing required components.")
        print("  Repair: ./scripts/setup.sh")
        print("  Submodules only: git submodule update --init --recursive")
        print("  Browser assets only: python3 scripts/vendor_assets.py")


# ---------------------------------------------------------------------------
# Developer Git lifecycle
# ---------------------------------------------------------------------------

def _git_output(repo: Path, args: Sequence[str], *, check: bool = True) -> str:
    result = _run(["git", *args], cwd=repo, check=check, capture=True)
    return (result.stdout or "").strip()


def _is_git_repo(repo: Path) -> bool:
    if not repo.is_dir() or shutil.which("git") is None:
        return False
    result = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo, check=False, capture=True)
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_component_snapshot(root: Path, component: GitComponent) -> dict:
    repo = (root / component.path).resolve()
    if not _is_git_repo(repo):
        return {
            "key": component.key,
            "label": component.label,
            "path": component.path,
            "ok": False,
            "reason": "not a Git repository",
        }
    porcelain = _git_output(repo, ["status", "--porcelain=v1", "--untracked-files=all"], check=False)
    conflicts = _git_output(repo, ["diff", "--name-only", "--diff-filter=U"], check=False).splitlines()
    branch_result = _run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=repo, check=False, capture=True)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    head = _git_output(repo, ["rev-parse", "HEAD"], check=False)
    remote_result = _run(["git", "remote", "get-url", component.remote], cwd=repo, check=False, capture=True)
    remote_url = remote_result.stdout.strip() if remote_result.returncode == 0 else None
    upstream_result = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=repo,
        check=False,
        capture=True,
    )
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else None
    return {
        "key": component.key,
        "label": component.label,
        "path": component.path,
        "ok": True,
        "repo": str(repo),
        "head": head,
        "branch": branch,
        "detached": branch is None,
        "dirty": bool(porcelain),
        "changes": porcelain.splitlines() if porcelain else [],
        "conflicts": [line for line in conflicts if line],
        "remote": component.remote,
        "remote_url": remote_url,
        "expected_remote_url": component.repository_url,
        "upstream": upstream,
        "target_branch": component.default_branch,
    }


def preflight_latest_modules(
    root: Path,
    components: Sequence[GitComponent] = GIT_COMPONENTS,
) -> list[dict]:
    """Validate every managed module before the first repository is changed."""
    problems: list[str] = []
    snapshots: list[dict] = []
    for component in components:
        snap = git_component_snapshot(root, component)
        snapshots.append(snap)
        if not snap["ok"]:
            if component.required:
                problems.append(f"{component.label}: {snap['reason']} at {component.path}")
            continue
        if snap["conflicts"]:
            problems.append(f"{component.label}: unresolved conflicts: {', '.join(snap['conflicts'])}")
        if snap["dirty"]:
            preview = "; ".join(snap["changes"][:4])
            problems.append(f"{component.label}: working tree is dirty ({preview})")
        if snap["remote_url"] is None:
            problems.append(f"{component.label}: remote '{component.remote}' is not configured")
        elif component.repository_url and snap["remote_url"] != component.repository_url:
            problems.append(
                f"{component.label}: remote '{component.remote}' points to {snap['remote_url']!r}; "
                f"expected {component.repository_url!r}"
            )
        if snap["branch"] not in {None, component.default_branch}:
            problems.append(
                f"{component.label}: currently on branch '{snap['branch']}', expected "
                f"'{component.default_branch}' or a detached pinned submodule commit"
            )
    if problems:
        joined = "\n  - ".join(problems)
        raise LifecycleError(
            "Latest-module update preflight failed. No module branches were changed:\n  - " + joined
        )
    return snapshots


def _checkout_development_branch(repo: Path, component: GitComponent) -> None:
    branch = component.default_branch
    remote_ref = f"{component.remote}/{branch}"
    local_exists = _run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
        check=False,
    ).returncode == 0
    if local_exists:
        _run(["git", "checkout", branch], cwd=repo)
    else:
        _run(["git", "checkout", "-b", branch, "--track", remote_ref], cwd=repo)


def _advance_one_git_component(root: Path, component: GitComponent) -> dict:
    repo = (root / component.path).resolve()
    before = _git_output(repo, ["rev-parse", "HEAD"])
    target = component.default_branch
    remote_ref = f"{component.remote}/{target}"
    print(f"\n-- {component.label} --")
    print(f"Path: {component.path}")
    print(f"Fetching {component.remote}/{target}")
    _run(["git", "fetch", "--prune", component.remote, target], cwd=repo)

    branch_result = _run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=repo, check=False, capture=True)
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    if current_branch is None:
        print(f"Switching detached submodule checkout to {target}")
        _checkout_development_branch(repo, component)
    elif current_branch != target:
        raise LifecycleError(
            f"{component.label} changed branches after preflight ({current_branch}); refusing to continue."
        )

    _run(["git", "merge", "--ff-only", remote_ref], cwd=repo)
    after = _git_output(repo, ["rev-parse", "HEAD"])
    upstream_result = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=repo,
        check=False,
        capture=True,
    )
    if upstream_result.returncode != 0:
        _run(["git", "branch", "--set-upstream-to", remote_ref, target], cwd=repo)
    return {
        "key": component.key,
        "label": component.label,
        "path": component.path,
        "branch": target,
        "old": before,
        "new": after,
        "changed": before != after,
    }


def _pointer_change_lines(repo: Path) -> list[str]:
    if not _is_git_repo(repo):
        return []
    output = _git_output(repo, ["status", "--short"], check=False)
    return [line for line in output.splitlines() if line.strip()]


def advance_latest_modules(
    root: Path,
    components: Sequence[GitComponent] = GIT_COMPONENTS,
) -> dict:
    """Advance managed module development branches without committing pointers."""
    preflight_latest_modules(root, components)
    print("\n== Latest managed modules ==")
    print("All managed repositories passed local-state preflight.")
    results: list[dict] = []
    for component in sorted(components, key=lambda item: item.path.count("/")):
        results.append(_advance_one_git_component(root, component))

    parent_changes: dict[str, list[str]] = {}
    root_changes = _pointer_change_lines(root)
    if root_changes:
        parent_changes["PAH host"] = root_changes
    reference_root = root / "modules" / "reference_manager"
    reference_changes = _pointer_change_lines(reference_root)
    if reference_changes:
        parent_changes["Reference Manager"] = reference_changes

    print("\n== Module revision summary ==")
    for item in results:
        old = item["old"][:10]
        new = item["new"][:10]
        marker = "updated" if item["changed"] else "already current"
        print(f"{item['label']:<22} {old} -> {new}  {marker}")
    if parent_changes:
        print("\nSubmodule pointer changes are intentionally left uncommitted for review:")
        for parent, lines in parent_changes.items():
            print(f"  {parent}")
            for line in lines:
                print(f"    {line}")
    else:
        print("\nNo parent submodule pointer changes were produced.")
    return {"components": results, "parent_changes": parent_changes}


def ensure_compatibility_test_dependencies(root: Path, python: Path) -> None:
    """Ensure the developer-only test runner exists before compatibility checks.

    Normal PAH setup installs runtime dependencies only. ``--latest-modules`` is
    explicitly a developer workflow, so it may install the host ``dev`` extra on
    demand rather than making pytest a runtime requirement for every PAH user.
    """
    probe = _run([python, "-c", "import pytest"], cwd=root, check=False, capture=True)
    if probe.returncode == 0:
        return
    print("\n== Compatibility test dependencies ==")
    print("pytest is not installed in the PAH environment; installing the host dev extra.")
    result = _run([python, "-m", "pip", "install", "-e", ".[dev]"], cwd=root, check=False)
    if result.returncode != 0:
        raise LifecycleError(
            "Unable to install compatibility-test dependencies. "
            "Run .venv/bin/python -m pip install -e '.[dev]' and retry."
        )
    verify = _run([python, "-c", "import pytest"], cwd=root, check=False, capture=True)
    if verify.returncode != 0:
        raise LifecycleError("pytest is still unavailable after installing the host dev extra.")


def run_component_tests(root: Path, python: Path) -> dict:
    """Run the test suites that are present in the host and managed modules."""
    ensure_compatibility_test_dependencies(root, python)
    print("\n== Compatibility tests ==")
    targets = [("PAH host", root, ("tests",))] + [
        (component.label, root / component.path, component.compatibility_tests)
        for component in PYTHON_COMPONENTS
        if component.key != "pah"
    ]
    results: list[dict] = []
    ok = True
    for label, repo, configured_targets in targets:
        test_targets = [repo / target for target in configured_targets if (repo / target).exists()]
        if not test_targets:
            results.append({"label": label, "status": "skipped", "reason": "no compatibility tests present"})
            print(f"- {label}: skipped (no compatibility tests present)")
            continue
        display_targets = " ".join(str(target.relative_to(repo)) for target in test_targets)
        print(f"- {label}: pytest -q {display_targets}")
        result = _run(
            [python, "-m", "pytest", "-q", *(str(target.relative_to(repo)) for target in test_targets)],
            cwd=repo,
            check=False,
        )
        passed = result.returncode == 0
        ok = ok and passed
        results.append({
            "label": label,
            "status": "passed" if passed else "failed",
            "returncode": result.returncode,
            "targets": [str(target.relative_to(repo)) for target in test_targets],
        })
        print(f"  {'✓ passed' if passed else '✗ failed'}")
    return {"ok": ok, "results": results}


def _host_dirty(root: Path) -> list[str]:
    if not _is_git_repo(root):
        return []
    # Untracked files (for example a downloaded .patch next to the checkout) do
    # not affect submodule gitlinks and are left untouched. Tracked host edits or
    # already-modified submodule pointers still block the developer update.
    output = _git_output(root, ["status", "--porcelain=v1", "--untracked-files=no"], check=False)
    return output.splitlines() if output else []


def _host_untracked(root: Path) -> list[str]:
    if not _is_git_repo(root):
        return []
    output = _git_output(
        root,
        ["ls-files", "--others", "--exclude-standard"],
        check=False,
    )
    return output.splitlines() if output else []


def setup(
    root: Path,
    *,
    skip_submodules: bool = False,
    skip_assets: bool = False,
    force_assets: bool = False,
    skip_system_tools: bool = False,
) -> int:
    if not _python_ok():
        raise LifecycleError(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required; found {sys.version.split()[0]}."
        )
    print(f"PAH setup: {root}")
    if not skip_submodules:
        ensure_submodules(root)
    python = ensure_venv(root)
    install_python_components(root, python)
    if not skip_assets:
        failures = provision_assets(root, python, force=force_assets)
        if failures:
            print("\nAsset provisioning reported problems; doctor will identify the missing pieces.")
    if not skip_system_tools:
        provision_system_tools(root)
    print("\n== Readiness ==")
    report = doctor_report(root)
    print_doctor(report)
    if report["ok"]:
        print("\nStart PAH with:")
        print("  source .venv/bin/activate")
        print("  python run.py /path/to/project")
        return 0
    return 1


def _reenter_update(
    root: Path,
    *,
    latest_modules: bool,
    skip_assets: bool,
    skip_tests: bool,
    skip_system_tools: bool,
) -> int:
    command = [
        sys.executable,
        "-m",
        "pah.lifecycle",
        "--root",
        str(root),
        "update",
        "--no-pull",
    ]
    if latest_modules:
        command.append("--latest-modules")
    if skip_assets:
        command.append("--skip-assets")
    if skip_tests:
        command.append("--skip-tests")
    if skip_system_tools:
        command.append("--skip-system-tools")
    return _run(command, cwd=root, check=False).returncode


def update(
    root: Path,
    *,
    no_pull: bool = False,
    skip_assets: bool = False,
    latest_modules: bool = False,
    skip_tests: bool = False,
    skip_system_tools: bool = False,
) -> int:
    if shutil.which("git") is None:
        raise LifecycleError("Git is required for PAH update.")
    if not (root / ".git").exists():
        raise LifecycleError("PAH update must be run from a Git checkout.")

    print(f"PAH compatible update: {root}")
    if not no_pull:
        if latest_modules:
            dirty = _host_dirty(root)
            if dirty:
                preview = "; ".join(dirty[:6])
                raise LifecycleError(
                    "--latest-modules requires clean tracked PAH host state before updating "
                    f"({preview}). Commit or stash host changes first."
                )
            untracked = _host_untracked(root)
            if untracked:
                preview = ", ".join(untracked[:6])
                print(f"Untracked host files will be left untouched: {preview}")
        print("\n== Host repository ==")
        _run(["git", "pull", "--ff-only"], cwd=root)
        # Re-enter after pulling so newly updated lifecycle code is used.
        return _reenter_update(
            root,
            latest_modules=latest_modules,
            skip_assets=skip_assets,
            skip_tests=skip_tests,
            skip_system_tools=skip_system_tools,
        )

    ensure_submodules(root)
    if latest_modules:
        advance_latest_modules(root)

    setup_command = [
        sys.executable,
        "-m",
        "pah.lifecycle",
        "--root",
        str(root),
        "setup",
        "--skip-submodules",
    ]
    if skip_assets:
        setup_command.append("--skip-assets")
    if skip_system_tools:
        setup_command.append("--skip-system-tools")
    setup_result = _run(setup_command, cwd=root, check=False)
    if setup_result.returncode != 0:
        return setup_result.returncode

    if latest_modules and not skip_tests:
        python = _venv_python(root)
        test_report = run_component_tests(root, python)
        if not test_report["ok"]:
            print("\n✗ One or more compatibility test suites failed. Review before committing submodule pointers.")
            return 1
        print("\n✓ Compatibility tests passed. Review and commit the new submodule pointers when ready.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PAH component lifecycle")
    parser.add_argument("--root", type=Path, default=ROOT, help="PAH repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    setup_parser = sub.add_parser("setup", help="Initialize modules, Python dependencies, assets, and readiness")
    setup_parser.add_argument("--skip-submodules", action="store_true")
    setup_parser.add_argument("--skip-assets", action="store_true")
    setup_parser.add_argument("--force-assets", action="store_true")
    setup_parser.add_argument(
        "--skip-system-tools",
        action="store_true",
        help="Do not attempt automatic installation of recommended Graphviz/Quarto tools",
    )

    update_parser = sub.add_parser("update", help="Fast-forward PAH, restore pinned modules, or explicitly advance development branches")
    update_parser.add_argument("--no-pull", action="store_true", help="Do not contact the PAH remote; reconcile the current checkout only")
    update_parser.add_argument("--skip-assets", action="store_true")
    update_parser.add_argument(
        "--latest-modules",
        action="store_true",
        help="Explicit developer mode: advance managed module main branches and leave pointer changes for review",
    )
    update_parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="With --latest-modules, skip host/module compatibility test suites",
    )
    update_parser.add_argument(
        "--skip-system-tools",
        action="store_true",
        help="Do not attempt recommended system-tool installation while reconciling setup",
    )

    assets_parser = sub.add_parser("assets", help="Provision all missing local browser assets")
    assets_parser.add_argument("--force", action="store_true")

    sub.add_parser("system-tools", help="Attempt installation of recommended Graphviz and Quarto tools")

    test_parser = sub.add_parser("test", help="Run host and available module compatibility tests")
    test_parser.add_argument("--json", action="store_true", dest="json_output")

    doctor_parser = sub.add_parser("doctor", help="Report missing modules, Python packages, browser assets, and optional tools")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        if args.command == "setup":
            return setup(
                root,
                skip_submodules=args.skip_submodules,
                skip_assets=args.skip_assets,
                force_assets=args.force_assets,
                skip_system_tools=args.skip_system_tools,
            )
        if args.command == "update":
            return update(
                root,
                no_pull=args.no_pull,
                skip_assets=args.skip_assets,
                latest_modules=args.latest_modules,
                skip_tests=args.skip_tests,
                skip_system_tools=args.skip_system_tools,
            )
        if args.command == "assets":
            python = _venv_python(root)
            if not python.is_file():
                python = Path(sys.executable)
            failures = provision_assets(root, python, force=args.force)
            return 1 if failures else 0
        if args.command == "system-tools":
            failures = provision_system_tools(root)
            return 1 if failures else 0
        if args.command == "test":
            python = _venv_python(root)
            if not python.is_file():
                raise LifecycleError("Run ./scripts/setup.sh before lifecycle tests so .venv is available.")
            report = run_component_tests(root, python)
            if args.json_output:
                print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["ok"] else 1
        if args.command == "doctor":
            report = doctor_report(root)
            if args.json_output:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print_doctor(report)
            return 0 if report["ok"] else 1
    except (LifecycleError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
