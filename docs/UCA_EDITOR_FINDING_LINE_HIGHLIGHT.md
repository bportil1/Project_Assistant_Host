# UCA: source finding line reveal and highlight

When a user explicitly navigates from a pyPIQUE finding (or Code Analyzer source selection),
PAH opens the repository-relative source through the existing authorized file route.
The editor navigation handler retains the active workspace checks and compares the
loaded file's **exact raw-byte SHA-256** to the server-provided **current-source** SHA-256.
The existing file API supplies that hash from the same bytes it decodes, so CRLF
normalization in the editor cannot create a false revision mismatch.
A mismatched or dirty tab is not navigated. This comparison does *not* prove that
an older pyPIQUE scan ran against the same revision.

After the editor is mounted and laid out, PAH converts the finding's one-based
inclusive source line range to Ace's zero-based marker range, scrolls to its first
line, and draws an amber full-line highlight. The marker is replaced for a new
successful navigation and cleared on workspace/repository change or leaving the
unified workspace. No editor content is altered and no SAT job is launched.

The check is deliberately deferred until after the actual Ace editor session exists;
this avoids cursor positioning before the docked editor has dimensions. Browser
integration against the user's installed PAH checkout is still required.

Local regression: `node --test tests/uca_ace_source_target.test.mjs`.
