"""Standalone source-owner registry used by setup, update, and diagnostics.

The registry describes integration requirements without taking ownership away from
standalone modules. Each module still owns its own pyproject and vendor scripts;
PAH installs from sibling source repositories; its embedded Git submodules are legacy snapshots only.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PythonComponent:
    key: str
    label: str
    path: str
    install_spec: str
    imports: tuple[str, ...]
    required: bool = True
    compatibility_tests: tuple[str, ...] = ("tests",)
    pah_entry_points: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class GitComponent:
    """A standalone source repository adjacent to the PAH host."""

    key: str
    label: str
    path: str
    repository_url: str | None = None
    remote: str = "origin"
    default_branch: str = "main"
    required: bool = True


@dataclass(frozen=True)
class BrowserAsset:
    key: str
    label: str
    owner: str
    script: str
    markers: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class SystemTool:
    key: str
    label: str
    command: str
    affects: str
    required: bool = False
    auto_install: bool = False
    installer: str | None = None
    package_name: str | None = None


PYTHON_COMPONENTS = (
    PythonComponent(
        key="pah",
        label="PAH host",
        path=".",
        install_spec=".",
        imports=("pah", "flask"),
    ),
    PythonComponent(
        key="code_analyzer",
        label="Code Analyzer",
        path="../Code_Repository_Cataloguer",
        install_spec="../Code_Repository_Cataloguer[web]",
        imports=("code_analyzer", "numpy", "flask"),
    ),
    PythonComponent(
        key="pypique",
        label="pyPIQUE",
        path="../pyPIQUE",
        install_spec="../pyPIQUE[full]",
        imports=("pique_py", "flask", "bandit"),
        compatibility_tests=("tests/test_pah_integration.py",),
        pah_entry_points=(("pah.modules", "pypique"), ("pah.runtimes", "pypique")),
    ),
    PythonComponent(
        key="hsqa_dbn",
        label="HSQA_DBN",
        path="../HSQA_DBN",
        install_spec="../HSQA_DBN[visual]",
        imports=("hsqa_dbn", "dash", "plotly", "torch", "geomloss"),
        compatibility_tests=("tests/test_pah_module_adapter.py",),
        pah_entry_points=(("pah.modules", "hsqa_dbn"), ("pah.runtimes", "hsqa_dbn")),
    ),
    PythonComponent(
        key="ml_lab",
        label="ML Lab",
        path="../ML_Lab",
        install_spec="../ML_Lab[ui]",
        imports=("ml_lab", "flask"),
        compatibility_tests=("tests/test_pah_integration.py",),
        pah_entry_points=(("pah.modules", "ml_lab"), ("pah.runtimes", "ml_lab")),
    ),
    PythonComponent(
        key="tech_documents",
        label="Document Workbench",
        path="../Research_Document_Workbench",
        install_spec="../Research_Document_Workbench[web]",
        imports=(
            "tech_documents",
            "flask",
            "nbformat",
            "jupyter_client",
            "ipykernel",
            "nbconvert",
        ),
    ),
    PythonComponent(
        key="reference_manager",
        label="Reference Manager",
        path="../Research_Paper_Repository_Manager",
        install_spec="../Research_Paper_Repository_Manager[web]",
        imports=("reference_manager", "fitz", "flask"),
    ),
    PythonComponent(
        key="paper_searcher",
        label="Research Search",
        path="../Research_Paper_Repository_Manager/modules/paper_searcher",
        install_spec="../Research_Paper_Repository_Manager/modules/paper_searcher",
        imports=("paper_searcher", "flask"),
    ),
)


# Explicit --latest-modules operations target standalone source repositories only.
# Default setup/update never advances these repositories.
GIT_COMPONENTS = (
    GitComponent(
        key="code_analyzer",
        label="Code Analyzer",
        path="../Code_Repository_Cataloguer",
    ),
    GitComponent(
        key="pypique",
        label="pyPIQUE",
        path="../pyPIQUE",
        repository_url="git@github.com:bportil1/pyPIQUE.git",
    ),
    GitComponent(
        key="hsqa_dbn",
        label="HSQA_DBN",
        path="../HSQA_DBN",
        repository_url="git@github.com:bportil1/HSQA_DBN.git",
        default_branch="refactor",
    ),
    GitComponent(
        key="ml_lab",
        label="ML Lab",
        path="../ML_Lab",
    ),
    GitComponent(
        key="tech_documents",
        label="Document Workbench",
        path="../Research_Document_Workbench",
    ),
    GitComponent(
        key="reference_manager",
        label="Reference Manager",
        path="../Research_Paper_Repository_Manager",
    ),
    GitComponent(
        key="paper_searcher",
        label="Research Search",
        path="../Research_Paper_Repository_Manager/modules/paper_searcher",
    ),
)


BROWSER_ASSETS = (
    BrowserAsset(
        key="pah_ace",
        label="Ace editor",
        owner="PAH",
        script="scripts/vendor_ace.py",
        markers=("pah/web/static/vendor/ace/ace.js",),
    ),
    BrowserAsset(
        key="pah_xterm",
        label="xterm.js + fit addon",
        owner="PAH",
        script="scripts/vendor_xterm.py",
        markers=(
            "pah/web/static/vendor/xterm/xterm.js",
            "pah/web/static/vendor/xterm/xterm.css",
            "pah/web/static/vendor/xterm/addon-fit.js",
        ),
    ),
    BrowserAsset(
        key="workbench_ace",
        label="Ace notebook editor",
        owner="Document Workbench",
        script="../Research_Document_Workbench/scripts/vendor_ace.py",
        markers=("../Research_Document_Workbench/tech_documents/web/static/vendor/ace/ace.js",),
    ),
    BrowserAsset(
        key="workbench_reveal",
        label="Reveal.js",
        owner="Document Workbench",
        script="../Research_Document_Workbench/scripts/vendor_reveal.py",
        markers=(
            "../Research_Document_Workbench/tech_documents/web/static/vendor/reveal/dist/reveal.js",
        ),
    ),
)


SYSTEM_TOOLS = (
    SystemTool(
        key="git",
        label="Git",
        command="git",
        affects="repository and submodule lifecycle",
        required=True,
    ),
    SystemTool(
        key="graphviz",
        label="Graphviz",
        command="dot",
        affects="graph rendering/export workflows",
        auto_install=True,
        installer="package",
        package_name="graphviz",
    ),
    SystemTool(
        key="quarto",
        label="Quarto",
        command="quarto",
        affects="DOCX/PPTX and selected notebook exports",
        auto_install=True,
        installer="quarto_release",
    ),
    SystemTool(
        key="latex",
        label="LaTeX",
        command="pdflatex",
        affects="LaTeX, PDF, and Beamer builds",
    ),
)
