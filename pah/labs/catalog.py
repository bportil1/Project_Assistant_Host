"""Host-owned definitions of PAH's goal-oriented workflow collections."""
from __future__ import annotations

from pah.labs.registry import LabManifest, LabRegistry
from pah.labs.workflows import CODE_ANALYSIS_WORKFLOW, EXISTING_FINDINGS_WORKFLOW


CODE_ANALYSIS_LAB = LabManifest(
    lab_id="code_analysis_lab",
    display_name="Code Analysis Lab",
    description="Software structure, security, quality-modeling, and learned-representation workflows.",
    workflows=(CODE_ANALYSIS_WORKFLOW, EXISTING_FINDINGS_WORKFLOW),
)

# Lab IDs and module IDs live in separate registries. Keep ``ml_lab`` as the
# collection ID because existing module manifests (including HSQA_DBN) already
# declare that membership. A future ML_Lab engine manifest may use the same
# token as a module ID without ambiguity because it is namespaced by registry.
ML_WORKFLOW_LAB = LabManifest(
    lab_id="ml_lab",
    display_name="ML Lab",
    description="Model training, comparison, representation learning, and experimental ML workflows.",
)


def default_lab_registry() -> LabRegistry:
    return LabRegistry((CODE_ANALYSIS_LAB, ML_WORKFLOW_LAB))
