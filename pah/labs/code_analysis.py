"""Code Analysis Lab controller.

This module is the intentional home for cross-module workflow knowledge.  It
knows which capabilities and generic artifact kinds make up the Code Analysis
Lab process, while Code Analyzer, pyPIQUE, and HSQA_DBN remain independent.
"""
from __future__ import annotations

from typing import Any

from pah.contracts import ArtifactRequirement, ModuleContext

from .artifacts import ArtifactInventory
from .registry import LabManifest, LabOrchestrator, ModuleRegistry
from pah.runtime import RuntimeRegistry
from .workflows import CODE_ANALYSIS_WORKFLOW


EXPECTED_MODULES = (
    ("code_analyzer", "Code Analyzer"),
    ("pypique", "pyPIQUE"),
    ("hsqa_dbn", "EBM / DBN Analysis Lab"),
)


class CodeAnalysisLabController:
    """Resolve providers and artifact readiness for the Code Analysis Lab."""

    def __init__(
        self,
        modules: ModuleRegistry,
        *,
        lab: LabManifest,
        artifacts: ArtifactInventory | None = None,
        runtimes: RuntimeRegistry | None = None,
    ) -> None:
        self.modules = modules
        self.lab = lab
        self.artifacts = artifacts or ArtifactInventory()
        self.runtimes = runtimes
        self.workflow = CODE_ANALYSIS_WORKFLOW
        self.orchestrator = LabOrchestrator(lab, modules)

    def _requirement_snapshot(self, requirement: ArtifactRequirement) -> dict[str, Any]:
        matches = self.artifacts.matching(requirement)
        return {
            **requirement.to_dict(),
            "satisfied": bool(matches) or requirement.optional,
            "matches": [item.to_dict() for item in matches],
        }

    def _output_snapshot(self, kind: str, provider_module: str | None) -> dict[str, Any]:
        artifacts = [item for item in self.artifacts.by_kind(kind) if not provider_module or item.producer_module == provider_module]
        return {
            "kind": kind,
            "available": bool(artifacts),
            "artifacts": [item.to_dict() for item in artifacts],
        }

    def _runtime_snapshot(self, module_id: str | None, context: ModuleContext | None) -> dict[str, Any] | None:
        if not module_id or self.runtimes is None:
            return None
        return self.runtimes.status(module_id, context=context).to_dict()

    def step_snapshot(self, step, *, context: ModuleContext | None = None) -> dict[str, Any]:
        resolution = self.orchestrator.resolve_step(step)
        requirements = [self._requirement_snapshot(item) for item in step.requires]
        missing_required = [item for item in requirements if not item["optional"] and not item["satisfied"]]
        provider = resolution.get("provider") or {}
        provider_id = provider.get("module_id") if isinstance(provider, dict) else None
        if provider_id and isinstance(provider, dict):
            resolution = dict(resolution)
            resolution["provider"] = {**provider, "runtime": self._runtime_snapshot(provider_id, context)}
        outputs = [self._output_snapshot(kind, provider_id or step.provider_module) for kind in step.produces]

        if resolution["state"] != "resolved":
            state = resolution["state"]
        elif step.produces and outputs and all(item["available"] for item in outputs):
            state = "complete"
        elif missing_required:
            state = "blocked"
        else:
            state = "ready"

        return {
            **step.to_dict(),
            "state": state,
            "resolution": resolution,
            "requirements": requirements,
            "missing_requirements": missing_required,
            "outputs": outputs,
        }

    def snapshot(self, *, context: ModuleContext | None = None) -> dict[str, Any]:
        steps = [self.step_snapshot(step, context=context) for step in self.workflow.steps]
        actionable_states = {"ready", "blocked", "missing_provider", "missing_capability", "ambiguous"}
        recommended = next(
            (step["step_id"] for step in steps if not step["optional"] and step["state"] in actionable_states),
            None,
        )
        if recommended is None:
            recommended = next(
                (step["step_id"] for step in steps if step["state"] in actionable_states),
                None,
            )
        expected_modules = []
        for module_id, display_name in EXPECTED_MODULES:
            manifest = self.modules.get(module_id)
            expected_modules.append({
                "module_id": module_id,
                "display_name": display_name,
                "registered": manifest is not None,
                "manifest": manifest.to_dict() if manifest else None,
                "runtime": self._runtime_snapshot(module_id, context),
            })
        return {
            "lab": self.lab.to_dict(),
            "workflow": {
                "workflow_id": self.workflow.workflow_id,
                "display_name": self.workflow.display_name,
                "description": self.workflow.description,
                "steps": steps,
            },
            "expected_modules": expected_modules,
            "artifacts": self.artifacts.snapshot(),
            "recommended_step": recommended,
        }
