"""Generic workflow descriptions used by PAH lab orchestrators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifacts import ArtifactRequirement


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    label: str
    capability: str
    description: str = ""
    provider_module: str | None = None
    requires: tuple[ArtifactRequirement, ...] = ()
    requires_any: tuple[ArtifactRequirement, ...] = ()
    produces: tuple[str, ...] = ()
    output_requirements: tuple[ArtifactRequirement, ...] = ()
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "label": self.label,
            "capability": self.capability,
            "description": self.description,
            "provider_module": self.provider_module,
            "requires": [item.to_dict() for item in self.requires],
            "requires_any": [item.to_dict() for item in self.requires_any],
            "produces": list(self.produces),
            "output_requirements": [item.to_dict() for item in self.output_requirements],
            "optional": self.optional,
        }


@dataclass(frozen=True)
class WorkflowManifest:
    workflow_id: str
    display_name: str
    description: str = ""
    steps: tuple[WorkflowStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "display_name": self.display_name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
        }
