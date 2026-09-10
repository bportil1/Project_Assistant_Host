"""Host-owned workflow descriptions for PAH lab collections."""
from __future__ import annotations

from pah.contracts import ArtifactRequirement, WorkflowManifest, WorkflowStep


CODE_ANALYSIS_WORKFLOW = WorkflowManifest(
    workflow_id="code_analysis_research",
    display_name="Code Analysis Research Workflow",
    description=(
        "Move from repository analysis to software-quality evidence, learned "
        "representations, signed information analysis, and MI-informed quality "
        "inspection without coupling the scientific modules to one another."
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
            requires=(ArtifactRequirement(
                kind="code_analysis", schema_id="pah.code-analysis.current", schema_version="1",
                producer_module="code_analyzer",
            ),),
            produces=("quality_model", "quality_evaluation"),
        ),
        WorkflowStep(
            step_id="representation_analysis",
            label="Representation & information analysis",
            capability="representation_learning",
            description=(
                "Use HSQA_DBN to learn a representation and run its MI/domain analysis in one "
                "provider session. Representation and analysis remain separately tracked artifacts."
            ),
            provider_module="hsqa_dbn",
            requires=(
                ArtifactRequirement(
                    kind="feature_dataset", schema_id="pah.feature-dataset.matrix", schema_version="1",
                    producer_module="pypique",
                ),
                ArtifactRequirement(
                    kind="domain_mapping", schema_id="pah.domain-mapping.feature-groups", schema_version="1",
                    optional=True, producer_module="pypique",
                ),
            ),
            produces=("representation", "representation_analysis"),
            output_requirements=(
                ArtifactRequirement(
                    kind="representation", producer_module="hsqa_dbn",
                    schema_id="hsqa_dbn.representation_bundle", schema_version="1",
                    capability="representation_learning",
                ),
                ArtifactRequirement(
                    kind="representation_analysis", producer_module="hsqa_dbn",
                    schema_id="hsqa_dbn.representation_analysis", schema_version="1",
                    capability="mutual_information_analysis",
                ),
            ),
        ),
        WorkflowStep(
            step_id="mi_informed_analysis",
            label="MI-informed quality analysis",
            capability="mi_informed_modeling",
            description=(
                "Inspect HSQA-derived dependence and signed topology, then generate an experimental "
                "non-negative PIQUE weighting candidate with explicit aggregation and weight-effect controls."
            ),
            provider_module="pypique",
            requires=(
                ArtifactRequirement(
                    kind="code_analysis", schema_id="pah.code-analysis.current", schema_version="1",
                    producer_module="code_analyzer",
                ),
                ArtifactRequirement(
                    kind="information_network", schema_id="pah.information-network", schema_version="1",
                    producer_module="pah",
                ),
            ),
            produces=("mi_informed_analysis", "mi_informed_model_experiment", "mi_informed_quality_model"),
            output_requirements=(
                ArtifactRequirement(
                    kind="mi_informed_analysis", producer_module="pypique",
                    schema_id="pypique.mi_informed_analysis", schema_version="1",
                    capability="mi_informed_analysis",
                ),
                ArtifactRequirement(
                    kind="mi_informed_model_experiment", producer_module="pypique",
                    schema_id="pypique.mi_informed_model_experiment", schema_version="1",
                    capability="mi_informed_modeling",
                ),
                ArtifactRequirement(
                    kind="mi_informed_quality_model", producer_module="pypique",
                    schema_id="pypique.mi_informed_quality_model", schema_version="1",
                    capability="mi_informed_modeling",
                ),
            ),
        ),
    ),
)
