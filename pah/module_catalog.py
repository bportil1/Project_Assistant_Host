"""PAH-owned manifests for modules already integrated by the host.

New standalone modules should prefer the ``pah.modules`` Python entry-point
contract so PAH does not need to import them by name. These legacy manifests
bridge the three mature 0.9.x integrations into the same semantic registry.
"""
from __future__ import annotations

from dataclasses import replace

from pah.contracts import ModuleManifest
from pah.labs import ModuleRegistry

MODULE_CATEGORIES = {
    "document_creation": "Document Creation",
    "literature_references": "Literature & References",
    "software_analysis": "Software Analysis",
    "machine_learning": "Machine Learning",
    "data_research_utilities": "Data / Research Utilities",
}

WORKSPACE_PRESETS = {
    "blank": {
        "label": "Blank Workspace",
        "description": "Start with no modules enabled and choose resources/capabilities manually.",
        "categories": (),
    },
    "document_creation": {
        "label": "Document Creation",
        "description": "Writing, document builds, notebooks, figures, and related authoring tools.",
        "categories": ("document_creation",),
    },
    "literature_review": {
        "label": "Literature Review",
        "description": "Reference, bibliography, paper-catalog, and literature-discovery tools.",
        "categories": ("literature_references",),
    },
    "software_analysis": {
        "label": "Software Analysis",
        "description": "Repository analysis, quality evidence, dependency, and software-analysis tools.",
        "categories": ("software_analysis",),
    },
    "ml_data_research": {
        "label": "ML / Data Research",
        "description": "Machine-learning and general data/research utility modules.",
        "categories": ("machine_learning", "data_research_utilities"),
    },
    "full_research": {
        "label": "Full Research Workspace",
        "description": "Enable every module installed on this PAH installation.",
        "categories": tuple(MODULE_CATEGORIES),
    },
}

_KNOWN_MODULE_CATEGORIES = {
    "code_analyzer": "software_analysis",
    "pypique": "software_analysis",
    "hsqa_dbn": "machine_learning",
    "ml_lab": "machine_learning",
    "tech_documents": "document_creation",
    "reference_manager": "literature_references",
    "research_search": "literature_references",
}

def module_category(manifest: ModuleManifest) -> tuple[str, str]:
    metadata = dict(manifest.metadata or {})
    category = str(metadata.get("category") or _KNOWN_MODULE_CATEGORIES.get(manifest.module_id) or "").strip()
    if not category:
        capabilities = set(manifest.capabilities)
        if capabilities & {"document_editing", "document_build", "notebook", "diagramming"}:
            category = "document_creation"
        elif capabilities & {"reference_management", "bibliography", "paper_catalog", "literature_search"}:
            category = "literature_references"
        elif capabilities & {"static_analysis", "quality_modeling", "code_structure", "dependency_analysis"}:
            category = "software_analysis"
        elif capabilities & {"classification", "regression", "clustering", "representation_learning", "mutual_information_analysis"}:
            category = "machine_learning"
        else:
            category = "data_research_utilities"
    label = str(metadata.get("category_label") or MODULE_CATEGORIES.get(category) or category.replace("_", " ").title())
    return category, label

def _with_category(manifest: ModuleManifest) -> ModuleManifest:
    category, label = module_category(manifest)
    metadata = dict(manifest.metadata or {})
    metadata.update({"category": category, "category_label": label})
    return replace(manifest, metadata=metadata)


HOST_MODULES = (
    ModuleManifest(
        module_id="code_analyzer",
        display_name="Code Analyzer",
        description="Repository structure, dependencies, similarity, clustering, and graph analysis.",
        collections=("code_analysis_lab",),
        capabilities=(
            "static_analysis",
            "code_structure",
            "dependency_analysis",
            "similarity_analysis",
            "clustering",
            "graph_artifacts",
        ),
        interfaces=("callable_api", "standalone_ui", "embedded_ui", "detachable_ui"),
        metadata={"host_surface": "analysis", "category": "software_analysis", "category_label": "Software Analysis"},
    ),
    ModuleManifest(
        module_id="tech_documents",
        display_name="Document Workbench",
        description="Markdown, LaTeX, notebook, presentation, and diagram workflows.",
        capabilities=("document_editing", "document_build", "notebook", "diagramming"),
        interfaces=("callable_api", "standalone_ui", "embedded_ui", "detachable_ui"),
        metadata={"category": "document_creation", "category_label": "Document Creation"},
    ),
    ModuleManifest(
        module_id="reference_manager",
        display_name="Reference Manager",
        description="Research-paper cataloguing, references, bibliographies, and PDF metadata.",
        capabilities=("reference_management", "bibliography", "paper_catalog"),
        interfaces=("callable_api", "standalone_ui", "embedded_ui", "detachable_ui"),
        metadata={"category": "literature_references", "category_label": "Literature & References"},
    ),
    ModuleManifest(
        module_id="research_search",
        display_name="Research Search",
        description="Literature discovery companion owned by the Reference Manager.",
        capabilities=("literature_search",),
        interfaces=("standalone_ui", "detachable_ui"),
        metadata={"category": "literature_references", "category_label": "Literature & References"},
    ),
)


def default_module_registry(*, discover: bool = True) -> ModuleRegistry:
    registry = ModuleRegistry(_with_category(item) for item in HOST_MODULES)
    if discover:
        registry.discover_entry_points()
        for item in registry.all():
            registry.register(_with_category(item), replace=True)
    return registry
