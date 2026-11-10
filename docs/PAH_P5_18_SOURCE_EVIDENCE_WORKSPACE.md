# P5-18 — PAH Code Analysis read-only evidence workspace pilot

The Code Analysis Lab contains an **opt-in manual locator** panel. Paste an explicit
`pah.source-evidence@1` locator from a producer. PAH independently obtains the
active research workspace's *repository* resource and workspace identity, then
validates the current file's SHA-256 and requested line span.

- This is not an automatic pyPIQUE selection bridge; only valid scan-time source
  fingerprints can be viewed. No hash is inferred from a later checkout.
- The endpoint is read-only. It does not invoke the existing editor, git, SAT,
  or source-remediation functions. No local or remote artifact storage is added.
- The panel clears on workspace-selector changes and workspace-open requests;
  every request is reauthorized on the server against the active workspace.
- HTML in source excerpts is displayed as text; not executed.
- No browser/Flask production deployment or concurrent file-replacement race
  acceptance has been completed. The underlying P5-18 resolver still needs
  descriptor-based path-open hardening before exposure outside a trusted local
  loopback environment. Do not publish this endpoint on a public interface.
