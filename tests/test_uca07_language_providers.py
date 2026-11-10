from pathlib import Path
from dataclasses import dataclass

import pytest

from code_analyzer.language_providers import (
    CONTRACT_VERSION, LanguageProviderRegistry, ProviderCapabilities,
    ProviderDescriptor, PythonLanguageProvider, default_registry,
)


def test_default_registry_advertises_python_only():
    registry = default_registry()
    descriptor, = registry.descriptors()
    assert descriptor.suffixes == (".py",)
    assert descriptor.capabilities.structural
    assert descriptor.capabilities.symbols
    assert not descriptor.capabilities.semantic
    assert not descriptor.capabilities.similarity
    assert registry.provider_for("app.py") is not None
    assert registry.provider_for("test.ats") is None


def test_python_projection_preserves_indexer_payload(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text("class Widget:\n    def go(self):\n        pass\n\ndef outer():\n    return Widget()\n")
    result = default_registry().analyze("sample.py", tmp_path)
    assert result.contract_version == CONTRACT_VERSION
    assert result.provider_artifact["path"] == "sample.py"
    assert [(item.kind, item.line_start) for item in result.items] == [
        ("class", 1), ("method", 2), ("function", 5)
    ]
    assert result.items[1].parent_id == result.items[0].item_id


def test_syntax_errors_are_diagnostics_not_fake_symbols(tmp_path):
    (tmp_path / "bad.py").write_text("def invalid(:\n")
    result = default_registry().analyze("bad.py", tmp_path)
    assert result.diagnostics
    assert not result.items
    assert result.provider_artifact["parse_error"]


def test_registry_is_explicit_and_rejects_colliding_suffixes():
    registry = LanguageProviderRegistry()
    registry.register(PythonLanguageProvider())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(PythonLanguageProvider())

    @dataclass
    class Other:
        descriptor: ProviderDescriptor = ProviderDescriptor(
            "atlas", "atlas", (".py",), ProviderCapabilities(lexical=True)
        )
        def analyze(self, path, root):
            raise RuntimeError("should not execute")
    with pytest.raises(ValueError, match="Suffix already"):
        registry.register(Other())


def test_invalid_descriptor_contract_and_suffix():
    from code_analyzer.language_providers.contracts import validate_descriptor
    with pytest.raises(ValueError, match="Unsupported"):
        validate_descriptor(ProviderDescriptor("bad", "x", (".x",), ProviderCapabilities(), "old"))
    with pytest.raises(ValueError, match="suffixes"):
        validate_descriptor(ProviderDescriptor("bad", "x", ("x",), ProviderCapabilities()))


def test_unknown_extension_and_scope_validation(tmp_path):
    registry = default_registry()
    (tmp_path / "text.txt").write_text("x")
    with pytest.raises(ValueError, match="No provider"):
        registry.analyze("text.txt", tmp_path)
    with pytest.raises(ValueError, match="Invalid repository-relative source"):
        registry.analyze("../escape.py", tmp_path)


def test_symlinks_are_rejected(tmp_path):
    outside = tmp_path.parent / "outside_uca07.py"
    outside.write_text("x=1")
    (tmp_path / "link.py").symlink_to(outside)
    with pytest.raises(ValueError, match="Symlinked"):
        default_registry().analyze("link.py", tmp_path)


def test_legacy_catalog_remains_authoritative(tmp_path):
    from code_analyzer.catalog.catalog_builder import build_catalog
    (tmp_path / "alpha.py").write_text("def alpha():\n    return 1\n")
    before = build_catalog(tmp_path).to_dict()
    default_registry().analyze("alpha.py", tmp_path)
    after = build_catalog(tmp_path).to_dict()
    assert before == after
