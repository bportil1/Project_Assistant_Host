from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitCommandResult:
    stdout: str
    stderr: str
    returncode: int


class LocalGitService:
    """Local-first Git service for the active PAH workspace.

    Local repository operations are always available when Git is installed.
    Network-capable operations are guarded by an explicit in-memory
    ``manual_remote`` connectivity mode. Binding a different workspace resets
    that permission to ``local_only`` so remote access never carries into a
    newly opened project by accident.
    """

    CONNECTIVITY_LOCAL = "local_only"
    CONNECTIVITY_REMOTE = "manual_remote"
    _REMOTE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._connectivity_mode = self.CONNECTIVITY_LOCAL

    def bind(self, workspace_root: str | Path | None) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._connectivity_mode = self.CONNECTIVITY_LOCAL

    @property
    def git_available(self) -> bool:
        return shutil.which("git") is not None

    @property
    def connectivity_mode(self) -> str:
        return self._connectivity_mode

    def set_connectivity(self, mode: str) -> dict:
        normalized = str(mode).strip().lower()
        if normalized not in {self.CONNECTIVITY_LOCAL, self.CONNECTIVITY_REMOTE}:
            raise GitError("Git connectivity mode must be local_only or manual_remote.")
        self._connectivity_mode = normalized
        return self.connectivity()

    def connectivity(self) -> dict:
        return {
            "connectivity_mode": self._connectivity_mode,
            "local_only": self._connectivity_mode == self.CONNECTIVITY_LOCAL,
            "remote_enabled": self._connectivity_mode == self.CONNECTIVITY_REMOTE,
        }

    def _require_remote_enabled(self) -> None:
        if self._connectivity_mode != self.CONNECTIVITY_REMOTE:
            raise GitError("Remote Git is disabled. Switch connectivity to Manual Remote before contacting a remote.")

    def _require_workspace(self) -> Path:
        if self.workspace_root is None:
            raise GitError("Open a PAH workspace before using Git.")
        return self.workspace_root

    def _run(
        self,
        args: Iterable[str],
        *,
        check: bool = True,
        cwd: Path | None = None,
        timeout: float = 20.0,
    ) -> GitCommandResult:
        if not self.git_available:
            raise GitError("Git is not installed or is not available on PATH.")
        root = cwd or self._require_workspace()
        env = os.environ.copy()
        # PAH never captures credentials. Credential helpers/SSH agents may be
        # used, but an unavailable credential must fail instead of spawning an
        # interactive password prompt behind the web UI.
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            proc = subprocess.run(
                [
                    "git",
                    "-c", "core.hooksPath=/dev/null",
                    "-c", "core.fsmonitor=false",
                    "-c", "commit.gpgSign=false",
                    *list(args),
                ],
                cwd=str(root),
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"Git command timed out after {timeout:g} seconds.") from exc
        result = GitCommandResult(proc.stdout, proc.stderr, proc.returncode)
        if check and proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "Git command failed.").strip()
            raise GitError(message)
        return result

    def _repo_root(self) -> Path | None:
        if not self.git_available or self.workspace_root is None:
            return None
        result = self._run(["rev-parse", "--show-toplevel"], check=False)
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        return Path(text).resolve() if text else None

    def _require_repo(self) -> Path:
        repo_root = self._repo_root()
        if repo_root is None:
            raise GitError("The current workspace is not a Git repository.")
        return repo_root

    def _has_head(self, repo_root: Path) -> bool:
        return self._run(["rev-parse", "--verify", "HEAD"], check=False, cwd=repo_root).returncode == 0

    # ------------------------------------------------------------------
    # Local status / history / branches
    # ------------------------------------------------------------------
    def status(self) -> dict:
        workspace = self.workspace_root
        base = {
            "git_available": self.git_available,
            "workspace": str(workspace) if workspace else None,
            "is_repository": False,
            "repository_root": None,
            "branch": None,
            "detached": False,
            "head": None,
            "has_commits": False,
            "changes": [],
            "staged_count": 0,
            "unstaged_count": 0,
            "untracked_count": 0,
            "submodules": [],
            "remotes": [],
            "tracking": None,
            **self.connectivity(),
        }
        if not self.git_available or workspace is None:
            return base
        repo_root = self._repo_root()
        if repo_root is None:
            return base

        branch = self._run(["branch", "--show-current"], check=False, cwd=repo_root).stdout.strip()
        has_commits = self._has_head(repo_root)
        head = None
        if has_commits:
            head = self._run(["rev-parse", "--short", "HEAD"], check=False, cwd=repo_root).stdout.strip() or None
        changes = self._parse_status(repo_root)
        base.update(
            {
                "is_repository": True,
                "repository_root": str(repo_root),
                "branch": branch or None,
                "detached": not bool(branch) and has_commits,
                "head": head,
                "has_commits": has_commits,
                "changes": changes,
                "staged_count": sum(1 for item in changes if item["staged"]),
                "unstaged_count": sum(1 for item in changes if item["unstaged"]),
                "untracked_count": sum(1 for item in changes if item["untracked"]),
                "submodules": self.submodules(repo_root=repo_root),
                "remotes": self.remotes(repo_root=repo_root),
                "tracking": self.tracking(repo_root=repo_root),
            }
        )
        return base

    def _parse_status(self, repo_root: Path) -> list[dict]:
        result = self._run(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repo_root)
        records = result.stdout.split("\0")
        output: list[dict] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record or len(record) < 4:
                continue
            xy = record[:2]
            path = record[3:]
            original_path = None
            if xy[0] in {"R", "C"} and index < len(records):
                original_path = records[index]
                index += 1
            x, y = xy[0], xy[1]
            untracked = xy == "??"
            output.append(
                {
                    "path": path,
                    "original_path": original_path,
                    "status": xy,
                    "index_status": x,
                    "worktree_status": y,
                    "staged": (x not in {" ", "?"}),
                    "unstaged": (y not in {" ", "?"}),
                    "untracked": untracked,
                }
            )
        return output

    def init(self) -> dict:
        root = self._require_workspace()
        if self._repo_root() is not None:
            raise GitError("The current workspace is already inside a Git repository.")
        self._run(["init"], cwd=root)
        return self.status()

    def _repo_and_paths(self, paths: Iterable[str]) -> tuple[Path, list[str]]:
        repo_root = self._require_repo()
        cleaned = [str(path).strip() for path in paths if str(path).strip()]
        if not cleaned:
            raise GitError("Select at least one file.")
        return repo_root, cleaned

    def stage(self, paths: Iterable[str]) -> dict:
        repo_root, cleaned = self._repo_and_paths(paths)
        self._run(["add", "--", *cleaned], cwd=repo_root)
        return self.status()

    def unstage(self, paths: Iterable[str]) -> dict:
        repo_root, cleaned = self._repo_and_paths(paths)
        if self._has_head(repo_root):
            self._run(["reset", "--", *cleaned], cwd=repo_root)
        else:
            self._run(["rm", "--cached", "-r", "--ignore-unmatch", "--", *cleaned], cwd=repo_root)
        return self.status()

    def diff(self, *, path: str | None = None, staged: bool = False) -> dict:
        repo_root = self._require_repo()
        args = ["diff", "--no-ext-diff", "--no-color"]
        if staged:
            args.append("--cached")
        if path:
            args.extend(["--", path])
        result = self._run(args, cwd=repo_root)
        return {"path": path, "staged": staged, "diff": result.stdout}

    def commit(self, message: str) -> dict:
        repo_root = self._require_repo()
        text = str(message).strip()
        if not text:
            raise GitError("Commit message cannot be empty.")
        self._run(["commit", "-m", text], cwd=repo_root, timeout=60.0)
        return self.status()

    def history(self, *, limit: int = 40) -> list[dict]:
        repo_root = self._require_repo()
        if not self._has_head(repo_root):
            return []
        safe_limit = max(1, min(int(limit), 200))
        fmt = "%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1e"
        result = self._run(["log", f"-{safe_limit}", f"--pretty=format:{fmt}"], cwd=repo_root)
        rows = []
        for record in result.stdout.split("\x1e"):
            record = record.strip()
            if not record:
                continue
            parts = record.split("\x1f", 4)
            if len(parts) == 5:
                rows.append({"commit": parts[0], "short": parts[1], "author": parts[2], "date": parts[3], "subject": parts[4]})
        return rows

    def branches(self) -> dict:
        repo_root = self._require_repo()
        current = self._run(["branch", "--show-current"], check=False, cwd=repo_root).stdout.strip() or None
        result = self._run(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo_root)
        branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        remote_result = self._run(["for-each-ref", "--format=%(refname:short)", "refs/remotes"], cwd=repo_root)
        remote_branches = [line.strip() for line in remote_result.stdout.splitlines() if line.strip() and not line.endswith("/HEAD")]
        return {"current": current, "branches": branches, "remote_branches": remote_branches}

    def switch_branch(self, name: str) -> dict:
        repo_root = self._require_repo()
        target = str(name).strip()
        if not target:
            raise GitError("Branch name cannot be empty.")
        known = set(self.branches()["branches"])
        if target not in known:
            raise GitError("PAH only switches existing local branches from this view.")
        self._run(["switch", target], cwd=repo_root)
        return self.status()

    # ------------------------------------------------------------------
    # Remote configuration (local reads/writes only)
    # ------------------------------------------------------------------
    def remotes(self, *, repo_root: Path | None = None) -> list[dict]:
        root = repo_root or self._repo_root()
        if root is None:
            return []
        names = self._run(["remote"], cwd=root).stdout.splitlines()
        rows: list[dict] = []
        for name in [item.strip() for item in names if item.strip()]:
            fetch_url = self._run(["remote", "get-url", name], check=False, cwd=root).stdout.strip() or None
            push_url = self._run(["remote", "get-url", "--push", name], check=False, cwd=root).stdout.strip() or fetch_url
            rows.append({"name": name, "fetch_url": fetch_url, "push_url": push_url})
        return rows

    def _validate_remote_name(self, name: str) -> str:
        cleaned = str(name).strip()
        if not cleaned or not self._REMOTE_NAME.fullmatch(cleaned):
            raise GitError("Remote name may contain only letters, numbers, dot, underscore, and hyphen.")
        return cleaned

    def _validate_remote_url(self, url: str) -> str:
        cleaned = str(url).strip()
        if not cleaned:
            raise GitError("Remote URL/path cannot be empty.")
        if cleaned.startswith("-"):
            raise GitError("Remote URL/path cannot begin with '-'.")
        return cleaned

    def add_remote(self, name: str, url: str) -> dict:
        repo_root = self._require_repo()
        remote = self._validate_remote_name(name)
        target = self._validate_remote_url(url)
        if remote in {row["name"] for row in self.remotes(repo_root=repo_root)}:
            raise GitError(f"Remote already exists: {remote}")
        # Configures only .git/config; does not contact the target.
        self._run(["remote", "add", remote, target], cwd=repo_root)
        return self.status()

    def remove_remote(self, name: str) -> dict:
        repo_root = self._require_repo()
        remote = self._validate_remote_name(name)
        if remote not in {row["name"] for row in self.remotes(repo_root=repo_root)}:
            raise GitError(f"Unknown remote: {remote}")
        # Local config mutation only; does not contact the target.
        self._run(["remote", "remove", remote], cwd=repo_root)
        return self.status()

    def tracking(self, *, repo_root: Path | None = None) -> dict | None:
        root = repo_root or self._repo_root()
        if root is None or not self._has_head(root):
            return None
        upstream_result = self._run(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            check=False,
            cwd=root,
        )
        if upstream_result.returncode != 0:
            return None
        upstream = upstream_result.stdout.strip()
        if not upstream:
            return None
        remote = upstream.split("/", 1)[0] if "/" in upstream else None
        remote_branch = upstream.split("/", 1)[1] if "/" in upstream else upstream
        counts = self._run(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"], check=False, cwd=root)
        ahead = behind = None
        if counts.returncode == 0:
            parts = counts.stdout.strip().split()
            if len(parts) == 2:
                try:
                    ahead, behind = int(parts[0]), int(parts[1])
                except ValueError:
                    ahead = behind = None
        return {
            "upstream": upstream,
            "remote": remote,
            "remote_branch": remote_branch,
            "ahead": ahead,
            "behind": behind,
        }

    def _resolve_remote(self, name: str | None = None, *, repo_root: Path | None = None) -> str:
        root = repo_root or self._require_repo()
        known = [row["name"] for row in self.remotes(repo_root=root)]
        if name:
            remote = self._validate_remote_name(name)
            if remote not in known:
                raise GitError(f"Unknown remote: {remote}")
            return remote
        tracking = self.tracking(repo_root=root)
        if tracking and tracking.get("remote") in known:
            return str(tracking["remote"])
        if len(known) == 1:
            return known[0]
        if not known:
            raise GitError("No Git remote is configured.")
        raise GitError("Choose a remote because this repository has multiple remotes.")

    # ------------------------------------------------------------------
    # Explicit network-capable operations
    # ------------------------------------------------------------------
    def fetch(self, remote: str | None = None, *, prune: bool = True) -> dict:
        self._require_remote_enabled()
        repo_root = self._require_repo()
        selected = self._resolve_remote(remote, repo_root=repo_root)
        args = ["fetch"]
        if prune:
            args.append("--prune")
        args.append(selected)
        self._run(args, cwd=repo_root, timeout=120.0)
        return self.status()

    def pull(self, remote: str | None = None) -> dict:
        self._require_remote_enabled()
        repo_root = self._require_repo()
        status = self.status()
        if status["changes"]:
            raise GitError("Pull is blocked while the working tree has local changes. Commit, stage/commit, or otherwise clean them first.")
        branch = status.get("branch")
        if not branch:
            raise GitError("Pull requires a checked-out local branch.")
        selected = self._resolve_remote(remote, repo_root=repo_root)
        tracking = self.tracking(repo_root=repo_root)
        remote_branch = str(tracking["remote_branch"]) if tracking and tracking.get("remote") == selected else str(branch)
        # Fast-forward only: PAH does not create merge commits or start rebases.
        self._run(["pull", "--ff-only", selected, remote_branch], cwd=repo_root, timeout=120.0)
        return self.status()

    def push(self, remote: str | None = None, *, set_upstream: bool = False) -> dict:
        self._require_remote_enabled()
        repo_root = self._require_repo()
        status = self.status()
        branch = status.get("branch")
        if not branch:
            raise GitError("Push requires a checked-out local branch.")
        selected = self._resolve_remote(remote, repo_root=repo_root)
        args = ["push"]
        tracking = self.tracking(repo_root=repo_root)
        if set_upstream or not tracking:
            args.extend(["--set-upstream", selected, str(branch)])
        else:
            args.extend([selected, str(branch)])
        self._run(args, cwd=repo_root, timeout=120.0)
        return self.status()

    def clone(self, url: str, destination: str | Path, *, branch: str | None = None) -> dict:
        self._require_remote_enabled()
        target_url = self._validate_remote_url(url)
        raw_destination = str(destination).strip()
        if not raw_destination:
            raise GitError("Clone destination cannot be empty.")
        dest = Path(raw_destination).expanduser().resolve()
        if not dest.parent.exists() or not dest.parent.is_dir():
            raise GitError(f"Clone destination parent does not exist: {dest.parent}")
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            raise GitError("Clone destination already exists and is not an empty directory.")
        args = ["clone"]
        branch_name = str(branch or "").strip()
        if branch_name:
            if branch_name.startswith("-"):
                raise GitError("Clone branch cannot begin with '-'.")
            args.extend(["--branch", branch_name])
        args.extend([target_url, str(dest)])
        self._run(args, cwd=dest.parent, timeout=180.0)
        return {"destination": str(dest), "branch": branch_name or None}

    # ------------------------------------------------------------------
    # Submodules
    # ------------------------------------------------------------------
    def submodules(self, *, repo_root: Path | None = None) -> list[dict]:
        root = repo_root or self._repo_root()
        if root is None:
            return []
        result = self._run(["submodule", "status", "--recursive"], check=False, cwd=root, timeout=30.0)
        if result.returncode != 0:
            return []
        rows: list[dict] = []
        for line in result.stdout.splitlines():
            if not line:
                continue
            marker = line[0]
            body = line[1:].strip()
            parts = body.split(maxsplit=2)
            if len(parts) < 2:
                continue
            commit, path = parts[0], parts[1]
            description = parts[2] if len(parts) > 2 else ""
            rows.append(
                {
                    "path": path,
                    "commit": commit,
                    "description": description,
                    "state": {
                        "-": "not_initialized",
                        "+": "different_commit",
                        "U": "merge_conflict",
                        " ": "recorded_commit",
                    }.get(marker, "recorded_commit"),
                }
            )
        return rows

    def update_submodules(self, mode: str = "recorded") -> dict:
        self._require_remote_enabled()
        repo_root = self._require_repo()
        normalized = str(mode).strip().lower()
        if normalized == "recorded":
            args = ["submodule", "update", "--init", "--recursive"]
        elif normalized == "tracked_remote":
            args = ["submodule", "update", "--init", "--recursive", "--remote", "--merge"]
        else:
            raise GitError("Submodule update mode must be recorded or tracked_remote.")
        # Even the recorded-commit form may contact a submodule remote when the
        # required object is not available locally, so both forms require the
        # explicit Manual Remote permission.
        self._run(args, cwd=repo_root, timeout=180.0)
        return {"mode": normalized, "submodules": self.submodules(repo_root=repo_root), **self.connectivity()}
