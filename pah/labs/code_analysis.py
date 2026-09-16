"""Code Analysis Lab controller.

This module is the intentional home for cross-module workflow knowledge.  It
knows which capabilities and generic artifact kinds make up the Code Analysis
Lab process, while Code Analyzer, pyPIQUE, and HSQA_DBN remain independent.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from pah.contracts import ArtifactRef, ArtifactRequirement, ModuleContext

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
    """Resolve providers, selected inputs, lineage freshness, and workflow readiness."""

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

    @staticmethod
    def _project_id(context: ModuleContext | None) -> str | None:
        root = getattr(context, "project_root", None) if context is not None else None
        return str(root) if root is not None else None

    @staticmethod
    def _prefer_current(items: tuple[ArtifactRef, ...]) -> ArtifactRef | None:
        if not items:
            return None
        aliases = tuple(item for item in items if item.metadata.get("registry_alias"))
        candidates = aliases or items
        return max(candidates, key=lambda item: (item.created_at or "", item.artifact_id))

    def _selected_artifact(
        self,
        step,
        requirement: ArtifactRequirement,
        *,
        context: ModuleContext | None,
    ) -> tuple[ArtifactRef | None, str, str | None]:
        project_id = self._project_id(context)
        selected_id = self.artifacts.selected_id(
            project_id=project_id,
            workflow_id=self.workflow.workflow_id,
            step_id=step.step_id,
            kind=requirement.kind,
        )
        if selected_id:
            selected = self.artifacts.get(selected_id)
            if selected is not None and selected.matches(requirement):
                if project_id is None or selected.project_id in {None, project_id}:
                    return selected, "pinned", selected_id
            # A persisted pin whose artifact disappeared or no longer satisfies the
            # contract is intentionally not replaced silently by a current artifact.
            return None, "pinned_missing", selected_id

        matches = self.artifacts.matching(requirement, project_id=project_id)
        return self._prefer_current(matches), "current", None

    def _requirement_snapshot(
        self,
        step,
        requirement: ArtifactRequirement,
        *,
        context: ModuleContext | None,
    ) -> dict[str, Any]:
        selected, selection_mode, pinned_id = self._selected_artifact(step, requirement, context=context)
        project_id = self._project_id(context)
        history = self.artifacts.history(requirement, project_id=project_id)
        expected = requirement.kind
        qualifiers = []
        if requirement.producer_module:
            qualifiers.append(f"from {requirement.producer_module}")
        if requirement.schema_id:
            schema = requirement.schema_id
            if requirement.schema_version:
                schema += f"@{requirement.schema_version}"
            qualifiers.append(f"schema {schema}")
        if requirement.capability:
            qualifiers.append(f"capability {requirement.capability}")
        if qualifiers:
            expected = f"{expected} ({', '.join(qualifiers)})"
        return {
            **requirement.to_dict(),
            "expected": expected,
            "satisfied": selected is not None or requirement.optional,
            "matches": [selected.to_dict()] if selected is not None else [],
            "selected": selected.to_dict() if selected is not None else None,
            "selected_artifact_id": selected.artifact_id if selected is not None else pinned_id,
            "selection_mode": selection_mode,
            "history": [
                {
                    **item.to_dict(),
                    "selectable": bool(item.metadata.get("history_selectable", True)),
                    "siblings": len(self.artifacts.siblings(item.artifact_id)),
                    "dependents": len(self.artifacts.dependents(item.artifact_id)),
                }
                for item in history
            ],
        }

    def _output_snapshot(
        self,
        kind: str,
        provider_module: str | None,
        *,
        context: ModuleContext | None,
        selected_inputs: tuple[ArtifactRef, ...],
        allow_history: bool,
        requirement: ArtifactRequirement | None = None,
    ) -> dict[str, Any]:
        project_id = self._project_id(context)
        history_requirement = requirement or ArtifactRequirement(kind=kind, producer_module=provider_module)
        current_artifacts = list(self.artifacts.matching(
            history_requirement,
            include_history=False,
            project_id=project_id,
        ))
        invalid_current = list(self.artifacts.find(
            kind=history_requirement.kind,
            producer_module=history_requirement.producer_module,
            capability=history_requirement.capability,
            schema_id=history_requirement.schema_id,
            schema_version=history_requirement.schema_version,
            project_id=project_id,
            validation_state="invalid",
            include_history=False,
        ))
        history = list(self.artifacts.history(history_requirement, project_id=project_id))
        candidates = current_artifacts + history if allow_history else current_artifacts

        selected_ids = tuple(
            self.artifacts.resolve_alias(item.artifact_id) or item.artifact_id
            for item in selected_inputs
        )

        def lineage_matches(artifact: ArtifactRef) -> bool:
            lineage_managed = bool(
                artifact.metadata.get("runtime_managed")
                or artifact.metadata.get("registry_alias")
                or artifact.metadata.get("history_snapshot")
            )
            return (
                not selected_ids
                or not lineage_managed
                or all(self.artifacts.descends_from(artifact.artifact_id, parent_id) for parent_id in selected_ids)
            )

        fresh = [artifact for artifact in candidates if lineage_matches(artifact)]
        stale_candidates = list(candidates)
        if not allow_history:
            # Historical descendants are never silently promoted to "current", but
            # they still explain why a stage is stale after an upstream selection
            # changes or a provider retracts its mutable current alias.
            stale_candidates.extend(history)
        stale_by_id = {
            artifact.artifact_id: artifact
            for artifact in stale_candidates
            if not lineage_matches(artifact)
        }
        stale = tuple(stale_by_id.values())

        payload = {
            "kind": kind,
            "available": bool(fresh),
            "artifacts": [item.to_dict() for item in fresh],
            "invalid_artifacts": [item.to_dict() for item in invalid_current],
            "stale_artifacts": [item.to_dict() for item in stale],
            "history": [
                {
                    **item.to_dict(),
                    "siblings": len(self.artifacts.siblings(item.artifact_id)),
                    "dependents": len(self.artifacts.dependents(item.artifact_id)),
                }
                for item in history
            ],
            "fresh_against": list(selected_ids),
        }
        if requirement is not None:
            payload["requirement"] = requirement.to_dict()
        return payload

    def _runtime_snapshot(self, module_id: str | None, context: ModuleContext | None) -> dict[str, Any] | None:
        if not module_id or self.runtimes is None:
            return None
        return self.runtimes.status(module_id, context=context).to_dict()

    def select_input(
        self,
        step_id: str,
        kind: str,
        artifact_id: str | None,
        *,
        context: ModuleContext | None = None,
    ) -> dict[str, Any]:
        step = next((item for item in self.workflow.steps if item.step_id == str(step_id)), None)
        if step is None:
            raise ValueError(f"Unknown Code Analysis Lab step {step_id!r}")
        requirement = next(
            (item for item in (*step.requires, *step.requires_any) if item.kind == str(kind)),
            None,
        )
        if requirement is None:
            raise ValueError(f"Step {step_id!r} does not consume artifact kind {kind!r}")
        if artifact_id is not None:
            artifact = self.artifacts.get(str(artifact_id))
            if artifact is None:
                raise ValueError(f"Unknown PAH artifact {artifact_id!r}")
            if not artifact.matches(requirement):
                raise ValueError(f"Artifact {artifact_id!r} does not satisfy the {kind!r} input contract")
            project_id = self._project_id(context)
            if project_id is not None and artifact.project_id not in {None, project_id}:
                raise ValueError(f"Artifact {artifact_id!r} belongs to a different PAH workspace")
        selected = self.artifacts.select(
            project_id=self._project_id(context),
            workflow_id=self.workflow.workflow_id,
            step_id=step.step_id,
            kind=requirement.kind,
            artifact_id=artifact_id,
        )
        return {
            "step_id": step.step_id,
            "kind": requirement.kind,
            "selection_mode": "pinned" if selected else "current",
            "artifact_id": selected,
        }

    def execution_context(self, step_id: str, context: ModuleContext | None = None) -> tuple[str, ModuleContext]:
        """Build a provider context containing the explicitly selected step inputs."""
        step = next((item for item in self.workflow.steps if item.step_id == str(step_id)), None)
        if step is None:
            raise ValueError(f"Unknown Code Analysis Lab step {step_id!r}")

        snapshot = self.step_snapshot(step, context=context)
        resolution = snapshot.get("resolution") or {}
        provider = resolution.get("provider") or {}
        module_id = provider.get("module_id") if isinstance(provider, dict) else None
        if resolution.get("state") != "resolved" or not module_id:
            raise ValueError(snapshot.get("blocking_reason") or f"Step {step.step_id!r} has no resolved provider")
        if snapshot.get("missing_requirements") or (step.requires_any and not snapshot.get("selected_alternative_kind")):
            raise ValueError(snapshot.get("blocking_reason") or f"Step {step.step_id!r} is missing required artifacts")

        selected: dict[str, dict[str, Any]] = {}
        for requirement in snapshot.get("requirements", []):
            artifact = requirement.get("selected")
            if isinstance(artifact, dict):
                selected[str(requirement["kind"])] = artifact

        base = context or ModuleContext()
        runtime = dict(base.runtime)
        runtime.update({
            "pah_lab": self.lab.lab_id,
            "pah_workflow": self.workflow.workflow_id,
            "pah_step": step.step_id,
            "input_artifacts": selected,
        })
        if step.step_id == "representation_analysis":
            feature_requirement = next((item for item in step.requires if item.kind == "feature_dataset"), None)
            if feature_requirement is not None:
                history = self.artifacts.history(
                    feature_requirement, project_id=self._project_id(context)
                )
                runtime["artifact_history"] = {
                    "feature_dataset": [item.to_dict() for item in history]
                }
        if step.step_id == "mi_informed_analysis":
            runtime.update({
                "requested_view": "mi-informed",
                "focused_view": True,
            })
        return str(module_id), replace(base, runtime=runtime)

    def step_snapshot(self, step, *, context: ModuleContext | None = None) -> dict[str, Any]:
        resolution = self.orchestrator.resolve_step(step)
        requirements = [self._requirement_snapshot(step, item, context=context) for item in step.requires]
        alternatives = [self._requirement_snapshot(step, item, context=context) for item in step.requires_any]
        selected_alternative = next((item for item in alternatives if item.get("selected") is not None), None)
        if selected_alternative is not None:
            selected_alternative = {**selected_alternative, "alternative_input": True}
            requirements.append(selected_alternative)
        missing_required = [item for item in requirements if not item["optional"] and not item["satisfied"]]
        missing_alternative = bool(step.requires_any) and selected_alternative is None
        provider = resolution.get("provider") or {}
        provider_id = provider.get("module_id") if isinstance(provider, dict) else None
        if provider_id and isinstance(provider, dict):
            resolution = dict(resolution)
            resolution["provider"] = {**provider, "runtime": self._runtime_snapshot(provider_id, context)}

        selected_list: list[ArtifactRef] = []
        pinned_branch = False
        for item in requirements:
            raw = item.get("selected")
            if isinstance(raw, dict):
                artifact = self.artifacts.get(str(raw.get("artifact_id") or ""))
                if artifact is not None:
                    selected_list.append(artifact)
            if item.get("selection_mode") == "pinned":
                pinned_branch = True
        selected_inputs = tuple(selected_list)

        output_requirements = {item.kind: item for item in step.output_requirements}
        outputs = [
            self._output_snapshot(
                kind,
                provider_id or step.provider_module,
                context=context,
                selected_inputs=selected_inputs,
                allow_history=pinned_branch,
                requirement=output_requirements.get(kind),
            )
            for kind in step.produces
        ]
        stale_outputs = [item for item in outputs if item.get("stale_artifacts") and not item.get("available")]

        if resolution["state"] != "resolved":
            state = resolution["state"]
        elif missing_required or missing_alternative:
            state = "blocked"
        elif step.produces and outputs and all(item["available"] for item in outputs):
            state = "complete"
        elif stale_outputs:
            state = "stale"
        else:
            state = "ready"

        blocking_reason = None
        if state == "blocked" and (missing_required or missing_alternative):
            parts: list[str] = []
            if missing_required:
                expected = ", ".join(item["expected"] for item in missing_required)
                noun = "artifact" if len(missing_required) == 1 else "artifacts"
                parts.append(f"Missing required {noun}: {expected}.")
            if missing_alternative:
                expected = " OR ".join(item["expected"] for item in alternatives)
                parts.append(f"Provide one input source: {expected}.")
            blocking_reason = " ".join(parts)
        elif state == "stale":
            stale_kinds = ", ".join(item["kind"] for item in stale_outputs)
            selected_ids = [item.artifact_id for item in selected_inputs]
            blocking_reason = (
                f"Existing {stale_kinds} output does not descend from the selected input artifact"
                f"{'s' if len(selected_ids) != 1 else ''}: {', '.join(selected_ids)}. Re-run this stage or restore the current input selection."
            )

        return {
            **step.to_dict(),
            "state": state,
            "resolution": resolution,
            "requirements": requirements,
            "input_alternatives": alternatives,
            "selected_alternative_kind": selected_alternative.get("kind") if selected_alternative else None,
            "missing_requirements": missing_required,
            "blocking_reason": blocking_reason,
            "outputs": outputs,
            "branch_mode": pinned_branch,
        }

    def snapshot(self, *, context: ModuleContext | None = None) -> dict[str, Any]:
        steps = [self.step_snapshot(step, context=context) for step in self.workflow.steps]
        actionable_states = {"ready", "stale", "blocked", "missing_provider", "missing_capability", "ambiguous"}
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
            "artifact_registry": self.artifacts.registry_snapshot(),
            "recommended_step": recommended,
        }
