# UCA-03 — Single-editor docking contract

PAH owns one Ace instance and a single set of tabs, dirty buffers, file revisions, save and Run actions. The Unified Analysis editor pane temporarily moves the existing `.main-pane` DOM node into its slot. It never clones an editor and never saves through another controller. On leaving UCA or hiding the editor pane, the node is restored to its original Workspace location.

The dock only handles DOM placement; it does not introduce source-selection dispatch. UCA-04–06 will implement explicit verified source navigation, with unsaved-buffer and revision checks. The editor remains fully governed by the existing PAH authorizations and save behavior.

Important: browser integration, project switching while docked, and Ace resizing require a real hosted smoke test before declaring UCA-03 fully accepted. No legacy editor is removed.
