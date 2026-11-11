"""PAH_Shared: a standalone, offline scientific presentation library.

No host, scientific-engine, network, or database dependencies are imported here.
"""
from importlib.resources import files

from .table_view import TableContractError, select_view, validate_snapshot

__version__ = "0.3.0"
TABLE_CONTRACT_VERSION = "1.0"


def static_asset(name: str):
    """Return an importlib.resources Traversable to a bundled offline asset.

    Use importlib.resources.as_file(...) when an actual filesystem path is needed.
    """
    if name not in {"table_view.mjs", "table_component.mjs", "table_exports.mjs", "matrix_editor.mjs", "table.css", "matrix.css"}:
        raise ValueError("Unknown PAH_Shared static asset")
    return files("pah_shared").joinpath("static", name)


__all__ = [
    "TABLE_CONTRACT_VERSION", "TableContractError", "select_view",
    "static_asset", "validate_snapshot", "__version__",
]
