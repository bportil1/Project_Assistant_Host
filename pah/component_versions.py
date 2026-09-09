"""PAH-managed component revision status and safe update operations.

This service is deliberately host-owned.  Modules remain ordinary standalone Git
repositories/submodules; PAH only reports and coordinates their revision state.
Remote access is never implicit in a status read: callers must explicitly ask to
fetch or update.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import threading
from typing import Iterable, Sequence

from .components import GIT_COMPONENTS, PYTHON_COMPONENTS, GitComponent, PythonComponent
from .lifecycle import (
    LifecycleError,
    _component_present,
    _git_output,
    _is_git_repo,
    _run,
    _venv_python,
    advance_latest_modules,
    ensure_compatibility_test_dependencies,
    git_component_snapshot,
)


class ComponentVersionError(RuntimeError):
    """Raised when a component-version action cannot be completed safely."""


_STATUS_LABELS = {
    "current": "Current",
    "update_available": "Update available",
    "ahead_local": "Ahead locally",
    "modified_worktree": "Modified working tree",
    "pinned_mismatch": "Pinned mismatch",
    "not_initialized": "Not initialized",
    "missing": "Missing",
    "conflict": "Conflict",
    "diverged": "Diverged",
    "remote_unknown": "Remote status unknown",
    "unmanaged": "Not pinned by parent",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_top_level(path: Path) -> Path | None:
    if not path.exists():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def _gitlink_at_head(owner: Path, relative_path: str) -> str | None:
    result = subprocess.run(
        ["git", "ls-tree", "HEAD", "--", relative_path],
        cwd=owner,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if not line:
        return None
    # Gitlink line: 160000 commit <sha>\t<path>
    left = line.split("\t", 1)[0].split()
    if len(left) >= 3 and left[0] == "160000" and left[1] == "commit":
        return left[2]
    return None


def _component_owner(root: Path, component: GitComponent) -> tuple[Path | None, str | None, str | None]:
    """Return (parent repo, path in parent, pinned commit) for a submodule.

    Looking at the component repository's parent directory correctly handles both
    PAH's direct submodules and nested repositories such as Research Search.
    """
    repo = (root / component.path).resolve()
    owner = _repo_top_level(repo.parent)
    if owner is None or owner == repo:
        return None, None, None
    try:
        relative = repo.relative_to(owner).as_posix()
    except ValueError:
        return None, None, None
    pinned = _gitlink_at_head(owner, relative)
    return owner, relative, pinned


def _remote_head(repo: Path, component: GitComponent) -> str | None:
    ref = f"refs/remotes/{component.remote}/{component.default_branch}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _ahead_behind(repo: Path, head: str, remote_head: str) -> tuple[int, int]:
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"{head}...{remote_head}"],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return 0, 0
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def _short(sha: str | None) -> str | None:
    return sha[:10] if sha else None


def _status_for(
    *,
    snapshot: dict,
    pinned: str | None,
    remote_head: str | None,
    ahead: int,
    behind: int,
) -> str:
    if snapshot.get("conflicts"):
        return "conflict"
    if snapshot.get("dirty"):
        return "modified_worktree"
    if not snapshot.get("ok"):
        return "missing"
    head = snapshot.get("head")
    if not pinned:
        return "unmanaged" if remote_head else "remote_unknown"
    if head != pinned:
        if remote_head and head == remote_head:
            return "pinned_mismatch"
        if ahead > 0 and behind == 0:
            return "ahead_local"
        if ahead > 0 and behind > 0:
            return "diverged"
        return "pinned_mismatch"
    if remote_head is None:
        return "remote_unknown"
    if behind > 0 and ahead == 0:
        return "update_available"
    if ahead > 0 and behind == 0:
        return "ahead_local"
    if ahead > 0 and behind > 0:
        return "diverged"
    return "current"


def component_version_snapshot(root: Path, component: GitComponent) -> dict:
    root = root.resolve()
    repo = (root / component.path).resolve()
    if not repo.exists():
        return {
            "key": component.key,
            "label": component.label,
            "path": component.path,
            "required": component.required,
            "status": "missing",
            "status_label": _STATUS_LABELS["missing"],
            "ok": False,
            "checked_out": None,
            "pinned": None,
            "remote_head": None,
            "remote_known": False,
            "dirty": False,
            "conflicts": [],
            "recordable": False,
            "restorable": False,
        }
    base = git_component_snapshot(root, component)
    if not base.get("ok"):
        state = "not_initialized" if repo.is_dir() else "missing"
        return {
            **base,
            "required": component.required,
            "status": state,
            "status_label": _STATUS_LABELS[state],
            "checked_out": None,
            "pinned": None,
            "remote_head": None,
            "remote_known": False,
            "recordable": False,
            "restorable": False,
        }

    owner, owner_relative, pinned = _component_owner(root, component)
    remote_head = _remote_head(repo, component)
    head = base.get("head") or ""
    ahead, behind = (0, 0)
    if head and remote_head:
        ahead, behind = _ahead_behind(repo, head, remote_head)
    status = _status_for(
        snapshot=base,
        pinned=pinned,
        remote_head=remote_head,
        ahead=ahead,
        behind=behind,
    )
    return {
        **base,
        "required": component.required,
        "checked_out": head or None,
        "checked_out_short": _short(head),
        "pinned": pinned,
        "pinned_short": _short(pinned),
        "remote_head": remote_head,
        "remote_head_short": _short(remote_head),
        "remote_known": remote_head is not None,
        "ahead": ahead,
        "behind": behind,
        "owner_repo": str(owner) if owner else None,
        "owner_relative_path": owner_relative,
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "recordable": bool(pinned and head and head != pinned and not base.get("dirty") and not base.get("conflicts")),
        "restorable": bool(pinned and head and head != pinned and not base.get("dirty") and not base.get("conflicts")),
    }


def _selected_components(keys: Iterable[str] | None) -> tuple[GitComponent, ...]:
    registry = {item.key: item for item in GIT_COMPONENTS}
    if keys is None:
        return tuple(GIT_COMPONENTS)
    normalized = []
    seen: set[str] = set()
    for raw in keys:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        component = registry.get(key)
        if component is None:
            raise ComponentVersionError(f"Unknown managed component {key!r}.")
        seen.add(key)
        normalized.append(component)
    if not normalized:
        raise ComponentVersionError("Select at least one managed component.")
    return tuple(normalized)


def _python_components_for(keys: set[str]) -> tuple[PythonComponent, ...]:
    return tuple(item for item in PYTHON_COMPONENTS if item.key in keys and item.key != "pah")


def _install_selected(root: Path, components: Sequence[GitComponent]) -> list[dict]:
    keys = {item.key for item in components}
    selected_python = _python_components_for(keys)
    if not selected_python:
        return []
    python = _venv_python(root)
    if not python.is_file():
        raise ComponentVersionError("PAH .venv is missing. Run ./scripts/setup.sh first.")
    results: list[dict] = []
    for component in selected_python:
        if not _component_present(root, component):
            if component.required:
                raise ComponentVersionError(f"{component.label} is not installable at {component.path}.")
            results.append({"key": component.key, "status": "skipped", "reason": "source unavailable"})
            continue
        result = _run(
            [python, "-m", "pip", "install", "-e", component.install_spec],
            cwd=root,
            check=False,
            capture=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "pip install failed").strip()
            raise ComponentVersionError(f"Failed to reinstall {component.label}: {detail}")
        results.append({"key": component.key, "status": "installed"})
    return results


def _test_targets(root: Path, components: Sequence[GitComponent]) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = [("PAH host", root)]
    python_by_key = {item.key: item for item in PYTHON_COMPONENTS}
    for component in components:
        python_component = python_by_key.get(component.key)
        if python_component is None:
            continue
        repo = root / python_component.path
        if any(existing.resolve() == repo.resolve() for _, existing in targets):
            continue
        targets.append((python_component.label, repo))
    return targets


def run_selected_compatibility_tests(root: Path, components: Sequence[GitComponent]) -> dict:
    python = _venv_python(root)
    if not python.is_file():
        raise ComponentVersionError("PAH .venv is missing. Run ./scripts/setup.sh first.")
    try:
        ensure_compatibility_test_dependencies(root, python)
    except LifecycleError as exc:
        raise ComponentVersionError(str(exc)) from exc

    results: list[dict] = []
    overall = True
    for label, repo in _test_targets(root, components):
        if not (repo / "tests").is_dir():
            results.append({"label": label, "status": "skipped", "reason": "no tests directory"})
            continue
        result = _run([python, "-m", "pytest", "-q"], cwd=repo, check=False, capture=True)
        passed = result.returncode == 0
        overall = overall and passed
        results.append({
            "label": label,
            "status": "passed" if passed else "failed",
            "returncode": result.returncode,
            "stdout": (result.stdout or "")[-8000:],
            "stderr": (result.stderr or "")[-4000:],
        })
    return {"ok": overall, "results": results, "checked_at": _utc_now()}


def _changed_paths(repo: Path) -> set[str]:
    tracked = set(_git_output(repo, ["diff", "--name-only"], check=False).splitlines())
    staged = set(_git_output(repo, ["diff", "--cached", "--name-only"], check=False).splitlines())
    untracked = set(_git_output(repo, ["ls-files", "--others", "--exclude-standard"], check=False).splitlines())
    return {path.strip() for path in tracked | staged | untracked if path.strip()}


def _allowed_nested_pointer_changes(root: Path, components: Sequence[GitComponent]) -> dict[Path, set[str]]:
    allowed: dict[Path, set[str]] = {}
    for component in components:
        owner, relative, _ = _component_owner(root, component)
        if owner is not None and relative:
            allowed.setdefault(owner.resolve(), set()).add(relative)
    return allowed


def _ensure_safe_component_trees(
    root: Path,
    components: Sequence[GitComponent],
    *,
    allow_selected_nested_pointers: bool = False,
) -> None:
    allowed = _allowed_nested_pointer_changes(root, components) if allow_selected_nested_pointers else {}
    repos: dict[Path, str] = {}
    for component in components:
        repo = (root / component.path).resolve()
        repos[repo] = component.label
        owner, _, _ = _component_owner(root, component)
        if owner is not None and owner != root:
            repos.setdefault(owner.resolve(), str(owner))

    problems: list[str] = []
    for repo, label in repos.items():
        if not _is_git_repo(repo):
            problems.append(f"{label}: not a Git repository")
            continue
        conflicts = _git_output(repo, ["diff", "--name-only", "--diff-filter=U"], check=False).splitlines()
        if conflicts:
            problems.append(f"{label}: unresolved conflicts")
            continue
        changes = _changed_paths(repo)
        unexpected = changes - allowed.get(repo, set())
        if unexpected:
            preview = "; ".join(sorted(unexpected)[:4])
            problems.append(f"{label}: working tree has unrelated changes ({preview})")
    if problems:
        raise ComponentVersionError("Cannot change/record component revisions:\n  - " + "\n  - ".join(problems))


def _fetch_components(root: Path, components: Sequence[GitComponent]) -> list[dict]:
    results: list[dict] = []
    for component in components:
        repo = (root / component.path).resolve()
        snap = git_component_snapshot(root, component)
        if not snap.get("ok"):
            if component.required:
                raise ComponentVersionError(f"{component.label} is not a Git repository at {component.path}.")
            results.append({"key": component.key, "status": "skipped", "reason": "repository unavailable"})
            continue
        if not snap.get("remote_url"):
            raise ComponentVersionError(f"{component.label} has no {component.remote!r} remote.")
        result = _run(
            ["git", "fetch", "--prune", component.remote, component.default_branch],
            cwd=repo,
            check=False,
            capture=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "git fetch failed").strip()
            raise ComponentVersionError(f"Failed to fetch {component.label}: {detail}")
        results.append({"key": component.key, "status": "fetched"})
    return results


def _staged_paths(repo: Path) -> set[str]:
    output = _git_output(repo, ["diff", "--cached", "--name-only"], check=False)
    return {line.strip() for line in output.splitlines() if line.strip()}


def _commit_gitlinks(repo: Path, paths: Sequence[str], message: str) -> str | None:
    allowed = {path for path in paths if path}
    if not allowed:
        return None
    pre_staged = _staged_paths(repo)
    unexpected = pre_staged - allowed
    if unexpected:
        raise ComponentVersionError(
            f"Refusing to record component versions in {repo}: unrelated staged changes exist: "
            + ", ".join(sorted(unexpected))
        )
    for path in sorted(allowed):
        _run(["git", "add", "--", path], cwd=repo)
    staged = _staged_paths(repo) & allowed
    if not staged:
        return None
    result = _run(["git", "commit", "-m", message], cwd=repo, check=False, capture=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git commit failed").strip()
        raise ComponentVersionError(f"Unable to record component versions in {repo}: {detail}")
    return _git_output(repo, ["rev-parse", "HEAD"], check=False)


class ComponentVersionManager:
    """Stateful coordinator used by the PAH version/dependency panel."""

    def __init__(self, root: str | Path, components: Sequence[GitComponent] = GIT_COMPONENTS):
        self.root = Path(root).resolve()
        self.components = tuple(components)
        self._by_key = {item.key: item for item in self.components}
        self._lock = threading.RLock()
        self._last_fetch_at: str | None = None
        self._compatibility: dict = {"status": "unknown", "checked_at": None, "results": []}

    def _select(self, keys: Iterable[str] | None) -> tuple[GitComponent, ...]:
        if keys is None:
            return self.components
        normalized: list[GitComponent] = []
        seen: set[str] = set()
        for raw in keys:
            key = str(raw).strip()
            if not key or key in seen:
                continue
            component = self._by_key.get(key)
            if component is None:
                raise ComponentVersionError(f"Unknown managed component {key!r}.")
            seen.add(key)
            normalized.append(component)
        if not normalized:
            raise ComponentVersionError("Select at least one managed component.")
        return tuple(normalized)

    def _expand_update_ancestors(self, components: Sequence[GitComponent]) -> tuple[GitComponent, ...]:
        """Include managed parent repositories required to advance nested modules safely."""
        selected = {item.key: item for item in components}
        changed = True
        while changed:
            changed = False
            for component in tuple(selected.values()):
                owner, _, _ = _component_owner(self.root, component)
                if owner is None or owner == self.root:
                    continue
                for candidate in self.components:
                    if (self.root / candidate.path).resolve() == owner.resolve() and candidate.key not in selected:
                        selected[candidate.key] = candidate
                        changed = True
                        break
        order = {item.key: index for index, item in enumerate(self.components)}
        return tuple(sorted(selected.values(), key=lambda item: order.get(item.key, 9999)))

    def snapshot(self) -> dict:
        with self._lock:
            items = [component_version_snapshot(self.root, component) for component in self.components]
            counts: dict[str, int] = {}
            for item in items:
                counts[item["status"]] = counts.get(item["status"], 0) + 1
            actionable = sum(
                1 for item in items if item["status"] in {"update_available", "pinned_mismatch", "ahead_local", "diverged", "modified_worktree", "conflict"}
            )
            return {
                "root": str(self.root),
                "git_available": bool(_is_git_repo(self.root)),
                "components": items,
                "summary": {
                    "total": len(items),
                    "actionable": actionable,
                    "counts": counts,
                },
                "last_fetch_at": self._last_fetch_at,
                "compatibility": dict(self._compatibility),
            }

    def fetch(self, keys: Iterable[str] | None = None) -> dict:
        with self._lock:
            selected = self._select(keys)
            fetched = _fetch_components(self.root, selected)
            self._last_fetch_at = _utc_now()
            return {"fetched": fetched, **self.snapshot()}

    def update(self, keys: Iterable[str], *, run_tests: bool = True) -> dict:
        with self._lock:
            requested = self._select(keys)
            selected = self._expand_update_ancestors(requested)
            available: list[GitComponent] = []
            skipped: list[dict] = []
            for component in selected:
                snap = git_component_snapshot(self.root, component)
                if snap.get("ok"):
                    available.append(component)
                elif component.required:
                    raise ComponentVersionError(f"{component.label} is not a Git repository at {component.path}.")
                else:
                    skipped.append({"key": component.key, "label": component.label, "reason": "repository unavailable"})
            if not available:
                raise ComponentVersionError("None of the selected components are available Git repositories.")
            try:
                report = advance_latest_modules(self.root, tuple(available))
            except LifecycleError as exc:
                raise ComponentVersionError(str(exc)) from exc
            if skipped:
                report["skipped"] = skipped
            installs = _install_selected(self.root, tuple(available))
            compatibility = None
            if run_tests:
                compatibility = run_selected_compatibility_tests(self.root, tuple(available))
                self._compatibility = {
                    "status": "passed" if compatibility["ok"] else "failed",
                    "checked_at": compatibility["checked_at"],
                    "results": compatibility["results"],
                }
            else:
                self._compatibility = {"status": "unknown", "checked_at": None, "results": []}
            self._last_fetch_at = _utc_now()
            return {
                "updated": report,
                "requested_keys": [item.key for item in requested],
                "expanded_keys": [item.key for item in selected],
                "installs": installs,
                "compatibility_run": compatibility,
                **self.snapshot(),
            }

    def restore_pinned(self, keys: Iterable[str]) -> dict:
        with self._lock:
            selected = self._select(keys)
            _ensure_safe_component_trees(self.root, selected, allow_selected_nested_pointers=True)
            restored: list[dict] = []
            available: list[GitComponent] = []
            for component in sorted(selected, key=lambda item: item.path.count("/"), reverse=True):
                item = component_version_snapshot(self.root, component)
                if not item.get("ok"):
                    if component.required:
                        raise ComponentVersionError(f"{component.label} is not a Git repository at {component.path}.")
                    restored.append({"key": component.key, "changed": False, "status": "skipped"})
                    continue
                pinned = item.get("pinned")
                if not pinned:
                    raise ComponentVersionError(
                        f"{component.label} has no parent gitlink recorded at HEAD; there is no pinned revision to restore."
                    )
                repo = (self.root / component.path).resolve()
                before = item.get("checked_out")
                if before != pinned:
                    result = _run(["git", "checkout", "--detach", pinned], cwd=repo, check=False, capture=True)
                    if result.returncode != 0:
                        detail = (result.stderr or result.stdout or "git checkout failed").strip()
                        raise ComponentVersionError(f"Unable to restore {component.label}: {detail}")
                restored.append({"key": component.key, "old": before, "new": pinned, "changed": before != pinned})
                available.append(component)
            installs = _install_selected(self.root, tuple(available))
            self._compatibility = {"status": "unknown", "checked_at": None, "results": []}
            return {"restored": restored, "installs": installs, **self.snapshot()}

    def test(self, keys: Iterable[str] | None = None) -> dict:
        with self._lock:
            selected = self._select(keys)
            report = run_selected_compatibility_tests(self.root, selected)
            self._compatibility = {
                "status": "passed" if report["ok"] else "failed",
                "checked_at": report["checked_at"],
                "results": report["results"],
            }
            return {"compatibility_run": report, **self.snapshot()}

    def record(self, keys: Iterable[str], *, message: str | None = None) -> dict:
        """Create local parent commits that record selected submodule gitlinks.

        No push is performed.  Nested component pointers are committed in their
        immediate parent first, then the resulting parent revision is recorded
        in PAH.  Existing unrelated staged changes cause a hard refusal.
        """
        with self._lock:
            selected = self._select(keys)
            _ensure_safe_component_trees(self.root, selected, allow_selected_nested_pointers=True)
            message = (message or "Record PAH component versions").strip()
            if not message:
                raise ComponentVersionError("A commit message is required to record component versions.")

            commits: list[dict] = []

            # Record deepest selected gitlinks in their immediate parent repos.
            owner_paths: dict[Path, set[str]] = {}
            owner_labels: dict[Path, set[str]] = {}
            for component in sorted(selected, key=lambda item: item.path.count("/"), reverse=True):
                item = component_version_snapshot(self.root, component)
                if not item.get("ok"):
                    if component.required:
                        raise ComponentVersionError(f"{component.label} is not a Git repository at {component.path}.")
                    continue
                owner_raw = item.get("owner_repo")
                relative = item.get("owner_relative_path")
                if not owner_raw or not relative:
                    raise ComponentVersionError(f"{component.label} is not recorded as a submodule gitlink by a parent repository.")
                if item.get("checked_out") == item.get("pinned"):
                    continue
                owner = Path(owner_raw).resolve()
                owner_paths.setdefault(owner, set()).add(relative)
                owner_labels.setdefault(owner, set()).add(component.label)

            # A nested commit changes the owning managed repository's HEAD.  By
            # committing deepest owners first, the root gitlink can then record
            # that new parent revision in the same action.
            non_root_owners = sorted(
                (owner for owner in owner_paths if owner != self.root),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            for owner in non_root_owners:
                paths = sorted(owner_paths[owner])
                sha = _commit_gitlinks(owner, paths, message)
                if sha:
                    commits.append({
                        "repo": str(owner),
                        "commit": sha,
                        "paths": paths,
                        "labels": sorted(owner_labels.get(owner, set())),
                    })

            # Determine which direct PAH gitlinks should be recorded.  This
            # includes direct selections plus managed parent repos changed by a
            # nested commit above.
            root_paths: set[str] = set(owner_paths.get(self.root, set()))
            for component in self.components:
                item = component_version_snapshot(self.root, component)
                if item.get("owner_repo") == str(self.root) and item.get("checked_out") != item.get("pinned"):
                    repo_path = (self.root / component.path).resolve()
                    if any(Path(entry["repo"]).resolve() == repo_path for entry in commits):
                        if item.get("owner_relative_path"):
                            root_paths.add(item["owner_relative_path"])

            root_sha = _commit_gitlinks(self.root, sorted(root_paths), message)
            if root_sha:
                commits.append({"repo": str(self.root), "commit": root_sha, "paths": sorted(root_paths), "labels": ["PAH host"]})

            if not commits:
                raise ComponentVersionError("No selected component pointer differs from its recorded parent revision.")
            return {"commits": commits, **self.snapshot()}
