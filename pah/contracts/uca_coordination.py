"""UCA-10 read-only reconciliation of producer-owned jobs and artifacts.

This module neither starts jobs nor publishes artifacts. A reported job outcome
is always read from the producer's JobReader at inspection time. An artifact
is a producer-issued reference, not a host-generated result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Any

from pah.contracts.artifacts import ArtifactRef, coerce_artifact_ref

SCHEMA = "pah.uca-analysis-handoff@1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = {"code_analyzer", "pypique", "hsqa_dbn", "ml_lab"}


class HandoffError(ValueError):
    """An untrusted or inconsistent producer handoff."""


def _required(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise HandoffError(f"Invalid {label}")
    return value


@dataclass(frozen=True)
class AnalysisHandoff:
    project_id: str
    repository_id: str
    producer: str
    source_sha256: str
    job_id: str | None = None
    artifact_id: str | None = None

    def __post_init__(self):
        _required(self.project_id, "project_id")
        _required(self.repository_id, "repository_id")
        if self.producer not in _ALLOWED:
            raise HandoffError("Unknown producer")
        if not isinstance(self.source_sha256, str) or not _SHA.fullmatch(self.source_sha256):
            raise HandoffError("Invalid source_sha256")
        if self.job_id is None and self.artifact_id is None:
            raise HandoffError("Producer job or artifact identity required")
        if self.job_id is not None:
            _required(self.job_id, "job_id")
        if self.artifact_id is not None:
            _required(self.artifact_id, "artifact_id")


def inspect_handoff(handoff: AnalysisHandoff, *, project_id: str, repository_id: str,
                    readers: Mapping[str, Any], artifact: ArtifactRef | Mapping[str, Any] | None = None) -> dict:
    """Check an explicit handoff against available producer observations.

    `readers` maps owner names to read-only JobReader objects. No producer
    state is mutated; unknown or absent observations remain unverified.
    """
    if handoff.project_id != project_id or handoff.repository_id != repository_id:
        raise HandoffError("Active project or repository mismatch")
    result = {"schema": SCHEMA, "project_id": project_id,
              "repository_id": repository_id, "producer": handoff.producer,
              "source_sha256": handoff.source_sha256,
              "job": {"id": handoff.job_id, "verification": "not_supplied"},
              "artifact": {"id": handoff.artifact_id, "verification": "not_supplied"}}
    if handoff.job_id is not None:
        reader = readers.get(handoff.producer)
        if reader is None or getattr(reader, "owner", None) != handoff.producer:
            result["job"]["verification"] = "unavailable"
        else:
            observed = reader.job(handoff.job_id)
            if not isinstance(observed, Mapping) or observed.get("owner") != handoff.producer:
                result["job"]["verification"] = "unavailable"
            else:
                result["job"].update(verification="observed", state=observed.get("state", "unknown"))
                # Job records are not required to carry a source hash or project;
                # observation cannot by itself certify the handoff's project.
    if handoff.artifact_id is not None:
        if artifact is None:
            result["artifact"]["verification"] = "unavailable"
        else:
            reference = coerce_artifact_ref(artifact)
            if (reference.artifact_id != handoff.artifact_id or
                    reference.producer_module != handoff.producer or
                    reference.project_id != handoff.project_id):
                raise HandoffError("Producer artifact identity mismatch")
            # A producer may certify source identity in provenance; absence
            # is *not* evidence that an artifact belongs to this source.
            sha = reference.provenance.get("source_sha256")
            if sha != handoff.source_sha256:
                result["artifact"]["verification"] = "source_unverified" if sha is None else "source_mismatch"
            elif reference.validation_state == "valid":
                result["artifact"]["verification"] = "producer_validated"
            else:
                result["artifact"]["verification"] = reference.validation_state
    return result
