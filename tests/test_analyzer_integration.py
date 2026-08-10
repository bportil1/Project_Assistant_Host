from pathlib import Path

import pytest

from pah.integrations import AnalyzerIntegration, AnalyzerIntegrationError


def test_analyzer_is_optional_when_module_missing(monkeypatch, tmp_path: Path):
    integration = AnalyzerIntegration()
    integration.bind(tmp_path)

    def fail_import(_name):
        raise ModuleNotFoundError("code_analyzer")

    monkeypatch.setattr("pah.integrations.analyzer.importlib.import_module", fail_import)
    status = integration.status()
    assert status["available"] is False
    assert status["analyzed"] is False
    with pytest.raises(AnalyzerIntegrationError, match="not installed"):
        integration.analyze()


def test_real_code_analyzer_integration_when_available(tmp_path: Path):
    pytest.importorskip("code_analyzer")

    (tmp_path / "alpha.py").write_text(
        "def alpha(x):\n"
        "    return beta(x)\n\n"
        "def beta(x):\n"
        "    return x * 2\n",
        encoding="utf-8",
    )
    (tmp_path / "gamma.py").write_text(
        "def gamma(value):\n"
        "    return value * 2\n",
        encoding="utf-8",
    )

    integration = AnalyzerIntegration()
    integration.bind(tmp_path)
    assert integration.status()["analyzed"] is False

    overview = integration.analyze()
    assert overview["summary"]["python_files"] == 2
    assert overview["summary"]["functions"] == 3

    functions = integration.functions()
    assert len(functions) == 3
    alpha = next(row for row in functions if row["name"] == "alpha")
    beta = next(row for row in functions if row["name"] == "beta")

    file_rows = integration.file_entities("alpha.py")["entities"]
    assert {row["name"] for row in file_rows if row["node_type"] == "function"} == {"alpha", "beta"}

    deps = integration.dependencies(alpha["id"])
    assert any(row["target_id"] == beta["id"] for row in deps["outgoing"])

    neighbors = integration.similar(alpha["id"], limit=2)["neighbors"]
    assert len(neighbors) == 2

    comparison = integration.compare(alpha["id"], beta["id"])
    assert 0.0 <= comparison["score"] <= 1.0

    matrix = integration.matrix()
    assert matrix["summary"]["function_count"] == 3
    assert "matrix" not in matrix

    duplicates = integration.duplicates(threshold=0.0, limit=3, include_source=False)
    assert duplicates["summary"]["compared_pair_count"] == 3

    clusters = integration.clusters(k=2)
    assert clusters["k"] == 2
    assert sum(cluster["size"] for cluster in clusters["clusters"]) == 3

    integration.mark_stale()
    assert integration.status()["stale"] is True
    integration.analyze()
    assert integration.status()["stale"] is False
