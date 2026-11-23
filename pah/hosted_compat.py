"""Legacy UI factories for PAH-owned compatibility surfaces.

Only this compatibility boundary knows the import paths required by old
hosted UI integrations. New modules should provide their own `pah.runtimes`
entry point or a standalone process launch contract, not be imported into
FullToolManager. These factories do NOT reinterpret module-local projects.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable


def code_analyzer_app(workspace: Path, on_analysis: Callable[[Any, str], Any] | None = None):
    create_app = importlib.import_module("code_analyzer.web.app").create_app
    return create_app(workspace, on_analysis=on_analysis)


def document_workbench_app():
    """Return Workbench's own app and project manager without replacing them."""
    return importlib.import_module("tech_documents.web.app").app


def reference_manager_app(config_path: Path):
    """Bridge the legacy global config path until Reference Manager has a public adapter.

    The global assignment is intentionally isolated here; unlike the WSGI
    engine, it cannot safely be reused for multiple instances in-process.
    MI-03's per-process launches are the proper multi-instance destination.
    """
    web_config = importlib.import_module("reference_manager.web.config")
    web_config.CONFIG_PATH = config_path
    return importlib.import_module("reference_manager.web.app").create_app()
