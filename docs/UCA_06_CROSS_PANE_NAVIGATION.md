# UCA-06 — Verified source navigation, first integration slice

- pyPIQUE finding preview is verified by PAH's P5-18 endpoint before publication.
- Browser coordinator scopes events to the visible workspace/repository and suppresses repeated producer/consumer delivery. It is **not** an authorization layer, and does not instantiate the UCA-01 Python coordinator in the server.
- PAH's single editor opens through its existing authenticated file API, checks the loaded saved-buffer SHA-256 (not unsaved edits), and only then moves to the selected line. A source change after the check is still possible; source edits are not authorized by navigation.
- Code Analyzer shows **candidate** span overlaps only if results are not marked stale. Its structural results lack complete per-entity source fingerprint evidence; therefore no exact AST revision equivalence is asserted and no automatic analysis is performed.
- No model recomputation, SAT execution, source edit, or third-party IO occurs as a side effect of selection.
- Remaining UCA-06 work: bind authoritative server workspace/project/repository IDs to UCA-01 coordinator, add current-source selection from editor, and fully revision-verified Code Analyzer bidirectional navigation. Browser/Flask acceptance remains outstanding.
