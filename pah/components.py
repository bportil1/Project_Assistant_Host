"""Shared PAH component registry used by setup, update, and diagnostics.

The registry describes integration requirements without taking ownership away from
standalone modules. Each module still owns its own pyproject and vendor scripts;
PAH only coordinates those existing entry points.
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
    """A managed development repository inside the PAH checkout."""

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
        path="modules/code_analyzer",
        install_spec="modules/code_analyzer[web]",
        imports=("code_analyzer", "numpy", "flask"),
    ),
    PythonComponent(
        key="pypique",
        label="pyPIQUE",
        path="modules/pypique",
        install_spec="modules/pypique[full]",
        imports=("pique_py", "flask", "bandit"),
        compatibility_tests=("tests/test_pah_integration.py",),
        pah_entry_points=(("pah.modules", "pypique"), ("pah.runtimes", "pypique")),
    ),
    PythonComponent(
        key="hsqa_dbn",
        label="HSQA_DBN",
        path="modules/hsqa_dbn",
        install_spec="modules/hsqa_dbn[visual]",
        imports=("hsqa_dbn", "dash", "plotly", "torch", "geomloss"),
        compatibility_tests=("tests/test_pah_module_adapter.py",),
        pah_entry_points=(("pah.modules", "hsqa_dbn"), ("pah.runtimes", "hsqa_dbn")),
    ),
    PythonComponent(
        key="tech_documents",
        label="Document Workbench",
        path="modules/tech_documents",
        install_spec="modules/tech_documents[web]",
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
        path="modules/reference_manager",
        install_spec="modules/reference_manager[web]",
        imports=("reference_manager", "fitz", "flask"),
    ),
    PythonComponent(
        key="paper_searcher",
        label="Research Search",
        path="modules/reference_manager/modules/paper_searcher",
        install_spec="modules/reference_manager/modules/paper_searcher",
        imports=("paper_searcher", "flask"),
    ),
)


# Shallow-to-deep order is intentional. Parent repositories are advanced while
# their nested submodules still match the recorded commit; nested repositories
# are advanced last so the resulting parent pointer changes are easy to review.
GIT_COMPONENTS = (
    GitComponent(
        key="code_analyzer",
        label="Code Analyzer",
        path="modules/code_analyzer",
    ),
    GitComponent(
        key="pypique",
        label="pyPIQUE",
        path="modules/pypique",
        repository_url="git@github.com:bportil1/pyPIQUE.git",
    ),
    GitComponent(
        key="hsqa_dbn",
        label="HSQA_DBN",
        path="modules/hsqa_dbn",
        repository_url="git@github.com:bportil1/HSQA_DBN.git",
        branch="refactor",
    ),
    GitComponent(
        key="tech_documents",
        label="Document Workbench",
        path="modules/tech_documents",
    ),
    GitComponent(
        key="reference_manager",
        label="Reference Manager",
        path="modules/reference_manager",
    ),
    GitComponent(
        key="paper_searcher",
        label="Research Search",
        path="modules/reference_manager/modules/paper_searcher",
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
        script="modules/tech_documents/scripts/vendor_ace.py",
        markers=("modules/tech_documents/tech_documents/web/static/vendor/ace/ace.js",),
    ),
    BrowserAsset(
        key="workbench_reveal",
        label="Reveal.js",
        owner="Document Workbench",
        script="modules/tech_documents/scripts/vendor_reveal.py",
        markers=(
            "modules/tech_documents/tech_documents/web/static/vendor/reveal/dist/reveal.js",
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
