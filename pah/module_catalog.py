"""PAH-owned manifests for modules already integrated by the host.

New standalone modules should prefer the ``pah.modules`` Python entry-point
contract so PAH does not need to import them by name. These legacy manifests
bridge the three mature 0.9.x integrations into the same semantic registry.
"""
from __future__ import annotations

from pah.contracts import ModuleManifest
from pah.labs import ModuleRegistry


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
        metadata={"host_surface": "analysis"},
    ),
    ModuleManifest(
        module_id="tech_documents",
        display_name="Document Workbench",
        description="Markdown, LaTeX, notebook, presentation, and diagram workflows.",
        capabilities=("document_editing", "document_build", "notebook", "diagramming"),
        interfaces=("callable_api", "standalone_ui", "embedded_ui", "detachable_ui"),
    ),
    ModuleManifest(
        module_id="reference_manager",
        display_name="Reference Manager",
        description="Research-paper cataloguing, references, bibliographies, and PDF metadata.",
        capabilities=("reference_management", "bibliography", "paper_catalog"),
        interfaces=("callable_api", "standalone_ui", "embedded_ui", "detachable_ui"),
    ),
    ModuleManifest(
        module_id="research_search",
        display_name="Research Search",
        description="Literature discovery companion owned by the Reference Manager.",
        capabilities=("literature_search",),
        interfaces=("standalone_ui", "detachable_ui"),
    ),
)


def default_module_registry(*, discover: bool = True) -> ModuleRegistry:
    registry = ModuleRegistry(HOST_MODULES)
    if discover:
        registry.discover_entry_points()
    return registry
