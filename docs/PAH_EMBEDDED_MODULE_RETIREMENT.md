# PAH source ownership: retire embedded Git submodules

PAH does not own copies of Code Analyzer, pyPIQUE, HSQA_DBN, ML_Lab, Document
Workbench, or Reference Manager. Their authoritative checkouts are standalone
siblings of `Project_Assistant_Host`, and PAH uses their installed Python
packages and explicit per-workspace module selection.

## Why `.gitignore` alone cannot fix this

Git gitlinks have mode `160000`. Git continues tracking gitlinks even if
`/modules/` is ignored. A one-time index removal is required and must be
committed to the **PAH host** Git repository to remove module pointers from
subsequent clones. Do not run `git submodule deinit -f`, `git clean -fdx`,
`git reset --hard`, or `rm -rf modules` while any embedded tree may have
uncommitted modifications.

## Safe local migration (no changes to standalone repositories)

1. Apply the host-only source patch. Confirm `.gitmodules` has been removed and
   `/modules/` appears in `.gitignore`.
2. From the PAH root, run `python3 scripts/retire_embedded_modules.py` to
   **preview** the existing gitlinks and physical entries. This is read-only.
3. Run `python3 scripts/retire_embedded_modules.py --apply` explicitly. This
   moves *all* physical module children, including untracked and modified files,
   into `../Project_Assistant_Host_embedded_module_recovery_<UTC>/modules/`.
   It does **not** touch `../ML_Lab`, `../HSQA_DBN`, `../pyPIQUE`,
   `../Code_Repository_Cataloguer` or other standalone repositories.
4. The tool removes Git `160000` entries using `git rm --cached`; this is an
   **index-only** operation. Other tracked files in PAH are not staged.
5. Review the recovery directory (especially modified/untracked worktrees),
   compare any unique work with the standalone checkouts, and retain the
   recovery directory until reconciled. `.git` pointers in preserved submodule
   worktrees may depend on the original PAH `.git/modules` metadata; moving
   a directory back to its old path restores that relative pointer.
6. Review `git status`, `git diff --cached --submodule=short`, and `git diff`.
   Stage the remaining host patch files with `git add -A` **only after review**,
   then commit and push the PAH changes from its standalone repository.

No `.gitmodules` file, gitlink, module source tree or `modules/README.md` is
included in new PAH commits. An empty local `modules/` directory may remain as
an ignored placeholder; it is not part of the Git repository.

The `~/.local/share/pah/runtime/<instance_id>/modules/` runtime metadata
location is separate from `Project_Assistant_Host/modules/` and remains valid.

## Guarantees and limits

- Nothing is changed on a remote by the script; `git push` remains manual.
- The script does not synchronize, fast-forward, reset or reinstall any module.
- It refuses unknown tracked files under `modules/`, symlinks and a still-present
  `.gitmodules` working-tree file.
- PAH's existing Python setup and runtime discovery continue to use **sibling
  repositories**. The source retirement does not itself change which installed
  components users elect to enable inside a workspace.
