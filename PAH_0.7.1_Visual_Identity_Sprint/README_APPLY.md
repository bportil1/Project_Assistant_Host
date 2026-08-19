# PAH 0.7.1 Visual Identity Sprint — Apply Bundle

This bundle was generated against the supplied current `Project_Assistant_Host` archive.
It intentionally contains separate patches for the PAH host and each Git submodule, including nested Research Search.

## Apply

From anywhere:

```bash
bash /path/to/PAH_0.7.1_Visual_Identity_Sprint/apply_visual_identity.sh \
  ~/Documents/venv/Project_Assistant_Host
```

The script performs `git apply --check` in all five repositories before it changes anything. If any check fails, no patch is applied.

## Repositories changed

1. PAH host
2. `modules/code_analyzer`
3. `modules/tech_documents`
4. `modules/reference_manager`
5. `modules/reference_manager/modules/paper_searcher`

The sprint does not intentionally change Git submodule pointers. After review/testing, commit each changed submodule in its own repository first, then commit the resulting submodule pointers in its parent repository(s), and finally commit the PAH host changes.

Do not use `git add .` blindly if your working tree already contains unrelated module changes.
