"""PAH integration adapters and cross-module bridges.

Major modules remain independent. PAH alone coordinates analyzer, document, and
reference behavior through their public façades.
"""

from .analyzer import AnalyzerIntegration, AnalyzerIntegrationError
from .documents import DocumentIntegration, DocumentIntegrationError
from .code_document import (
    CodeDocumentBridgeError,
    code_document_snippet,
    extract_code_markers,
    refresh_code_references,
)
from .references import ReferenceIntegration, ReferenceIntegrationError
from .reference_document import ReferenceDocumentBridgeError, reference_document_snippet
from .analysis_diagram import AnalysisDiagramBridgeError, entity_dependency_diagram, suggested_diagram_path
from .documentation_scaffold import (
    DocumentationScaffoldError,
    entity_scaffold,
    file_scaffold,
    project_scaffold,
)
from .artifact_links import ArtifactLinkIndex
from .diagram_document import DiagramDocumentBridgeError, diagram_document_snippet
from .overleaf import OverleafImportError, OverleafImportService

__all__ = [
    "AnalysisDiagramBridgeError",
    "AnalyzerIntegration",
    "AnalyzerIntegrationError",
    "ArtifactLinkIndex",
    "CodeDocumentBridgeError",
    "DocumentIntegration",
    "DocumentIntegrationError",
    "DiagramDocumentBridgeError",
    "DocumentationScaffoldError",
    "ReferenceDocumentBridgeError",
    "ReferenceIntegration",
    "ReferenceIntegrationError",
    "OverleafImportError",
    "OverleafImportService",
    "code_document_snippet",
    "diagram_document_snippet",
    "entity_dependency_diagram",
    "entity_scaffold",
    "extract_code_markers",
    "file_scaffold",
    "project_scaffold",
    "reference_document_snippet",
    "refresh_code_references",
    "suggested_diagram_path",
]
