# P5-18 source evidence: first read-only boundary

The `pah.labs.source_evidence` module provides the offline, explicit-coordinate
verification and source excerpt boundary for pyPIQUE SAT evidence.  It is a
library contract, not a new HTTP endpoint, UI, SAT parser, or Code Analyzer edit
operation.

## Producer/caller obligations

- pyPIQUE must explicitly publish `producer_module=pypique`, stable finding ID,
  PAH project ID, canonical repository-relative POSIX path, 1-based inclusive
  line span, and SHA-256 of the **entire source file** corresponding to the finding.
- PAH must independently authorize the active workspace and repository resource;
  it must not derive repository roots from an untrusted finding or infer a source
  position from diagnostic prose.  The active project ID must match the locator.
- Code Analyzer remains authoritative for AST navigation and source analysis;
  this resolver does not rewrite or index its symbols or change its source.

## Output and constraints

The resolver returns `pah.source-evidence@1`, `mode=read_only`, original location,
verified source SHA-256, and a bounded UTF-8 excerpt.  It rejects stale hashes,
source escapes, invalid paths/spans, binary files, files above 8 MiB, spans above
80 lines, and excerpt output exceeding 24 KiB.  Errors do not trigger automatic
fallback to another source file or revision.

## Acceptance still outstanding

Wire the authorized PAH workspace and producer evidence into a read-only UI;
validate true SAT finding/Code Analyzer provenance on a representative project;
exercise Flask/browser permissions, project switches, and symlink/swap races.
Source snapshots need a stable open descriptor to close concurrent replacement
races before exposing this through an externally reachable endpoint.  No edit
permissions are created by this contract.

## P5-18 descriptor-relative hardening

On POSIX hosts, source inspection opens the authorized repository directory and
walks each relative component with descriptor-relative `os.open` and
`O_NOFOLLOW`. The final opened descriptor must refer to a regular file, and is
read with strict byte limits and before/after metadata checks; source SHA-256
remains mandatory. A path replaced with a symlink during traversal is rejected
instead of followed. An unsupported platform fails closed rather than falling
back to path-based reads. This closes pathname-swap and symlink-follow races
inside the opened repository. It does not make a mutable repository snapshot
immutable or prove no transient in-place modifications occurred between checks.
Hosted permission/browser checks remain outstanding.
