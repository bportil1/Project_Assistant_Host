"""Project Assistant Host (PAH)."""


def create_app(*args, **kwargs):
    """Create the Flask host app without making Flask a core-service import dependency."""
    from .app import create_app as _create_app
    return _create_app(*args, **kwargs)


__all__ = ["create_app"]
