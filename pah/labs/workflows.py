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
                "Build or load the software-quality evidence, operational feature dataset, "
                "and domain mapping used by downstream representation experiments."
            ),
            provider_module="pypique",
            produces=("feature_dataset", "domain_mapping", "quality_model"),
        ),
        WorkflowStep(
            step_id="representation_learning",
            label="Learn representation",
            capability="representation_learning",
            description="Train a representation model from an aligned feature dataset and optional domain semantics.",
            provider_module="hsqa_dbn",
            requires=(
                ArtifactRequirement(kind="feature_dataset"),
                ArtifactRequirement(kind="domain_mapping", optional=True),
            ),
            produces=("representation",),
        ),
        WorkflowStep(
            step_id="latent_analysis",
            label="Inspect latent information",
            capability="mutual_information_analysis",
            description="Analyze the learned representation and its information relationship to the supplied domain semantics.",
            provider_module="hsqa_dbn",
            requires=(ArtifactRequirement(kind="representation"),),
            produces=("representation_analysis",),
        ),
    ),
)
