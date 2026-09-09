"""Host-owned workflow descriptions for PAH lab collections."""
from __future__ import annotations

from pah.contracts import ArtifactRequirement, WorkflowManifest, WorkflowStep


CODE_ANALYSIS_WORKFLOW = WorkflowManifest(
    workflow_id="code_analysis_research",
    display_name="Code Analysis Research Workflow",
    description=(
        "Move from repository analysis to software-quality evidence, learned "
        "representations, and latent-information inspection without coupling "
        "the underlying scientific modules to one another."
    ),
    steps=(
        WorkflowStep(
            step_id="repository_analysis",
            label="Repository analysis",
            capability="static_analysis",
            description="Inspect repository structure, dependencies, similarity, and code-level evidence.",
            provider_module="code_analyzer",
            produces=("code_analysis",),
            optional=True,
        ),
        WorkflowStep(
            step_id="quality_modeling",
            label="Quality evidence and model",
            capability="quality_modeling",
            description=(
                "Consume the current Code Analyzer project handoff, then build or load "
                "pyPIQUE quality evidence and a calibrated project evaluation."
            ),
            provider_module="pypique",
            requires=(
                ArtifactRequirement(
                    kind="code_analysis",
                    schema_id="pah.code-analysis.current",
                    schema_version="1",
                    producer_module="code_analyzer",
                ),
            ),
            produces=("quality_model", "quality_evaluation"),
        ),
        WorkflowStep(
            step_id="representation_learning",
            label="Learn representation",
            capability="representation_learning",
            description="Train a representation model from an aligned feature dataset and optional domain semantics.",
            provider_module="hsqa_dbn",
            requires=(
                ArtifactRequirement(
                    kind="feature_dataset",
                    schema_id="pah.feature-dataset.matrix",
                    schema_version="1",
                    producer_module="pypique",
                ),
                ArtifactRequirement(
                    kind="domain_mapping",
                    schema_id="pah.domain-mapping.feature-groups",
                    schema_version="1",
                    optional=True,
                    producer_module="pypique",
                ),
            ),
            produces=("representation",),
        ),
        WorkflowStep(
            step_id="latent_analysis",
            label="Inspect latent information",
            capability="mutual_information_analysis",
            description="Analyze the learned representation and its information relationship to the supplied domain semantics.",
            provider_module="hsqa_dbn",
            requires=(ArtifactRequirement(kind="representation", producer_module="hsqa_dbn"),),
            produces=("representation_analysis",),
        ),
    ),
)
