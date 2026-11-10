"""Server-owned read-only UCA source navigation scope. No filesystem mutation."""
from __future__ import annotations
import hashlib
from pathlib import Path


def navigation_scope(workspace_id: str | None, repository_root: str | Path | None,
                     context_token: str, context_revision: int) -> dict[str, object]:
    """Return IDs anchored to the currently selected PAH workspace resource.

    The host workspace profile is the current project authority in this phase.
    Repository identity is a deterministic fingerprint of the normalized root,
    not a claim about source revision. No filesystem content is read.
    """
    if not workspace_id or repository_root is None or not context_token:
        raise ValueError('Active workspace and repository resource required')
    if type(context_revision) is not int or context_revision < 0:
        raise ValueError('Invalid host context revision')
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Selected repository resource must be a directory')
    repo_id = 'repo-' + hashlib.sha256(str(root).encode('utf-8')).hexdigest()
    return {
        'schema': 'pah.uca-navigation-scope@1',
        'workspace_id': str(workspace_id),
        'project_id': str(workspace_id),
        'repository_id': repo_id,
        'repository_root': str(root),
        'context_token': str(context_token),
        'context_revision': context_revision,
    }
