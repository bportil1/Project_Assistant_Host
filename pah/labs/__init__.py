"""Goal-oriented PAH lab collections and orchestration infrastructure."""

from .artifacts import ArtifactInventory, ArtifactRegistry
from .catalog import CODE_ANALYSIS_LAB, ML_WORKFLOW_LAB, default_lab_registry
from .code_analysis import CodeAnalysisLabController
from .workflows import CODE_ANALYSIS_WORKFLOW
from .registry import LabManifest, LabOrchestrator, LabRegistry, ModuleRegistry, RegistryError

__all__ = [
    "ArtifactInventory",
    "ArtifactRegistry",
    "CODE_ANALYSIS_LAB",
    "CODE_ANALYSIS_WORKFLOW",
    "CodeAnalysisLabController",
    "ML_WORKFLOW_LAB",
    "LabManifest",
    "LabOrchestrator",
    "LabRegistry",
    "ModuleRegistry",
    "RegistryError",
    "default_lab_registry",
]
