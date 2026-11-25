"""Regression: editable source installs cannot create an offline isolated build env."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pah import lifecycle
from pah.components import PYTHON_COMPONENTS


def test_editable_install_uses_pah_venv_backend_without_skipping_deps():
    python = Path('/fake/venv/bin/python')
    assert lifecycle._editable_install_command(python, '../ML_Lab[ui]') == [
        python, '-m', 'pip', 'install', '--no-build-isolation', '-e', '../ML_Lab[ui]'
    ]
    assert '--no-deps' not in lifecycle._editable_install_command(python, '.')


@pytest.mark.parametrize('offline', [True, False])
def test_setup_reuses_venv_build_backend_for_every_sibling(tmp_path, monkeypatch, offline):
    root = tmp_path / 'Project_Assistant_Host'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nname="project-assistant-host"\n', encoding='utf8')
    for component in PYTHON_COMPONENTS:
        if component.key == 'pah':
            continue
        source = (root / component.path).resolve()
        source.mkdir(parents=True, exist_ok=True)
        (source / 'pyproject.toml').write_text('[project]\nname="placeholder"\n', encoding='utf8')
    monkeypatch.setattr(lifecycle, 'declared_constraints', lambda *_: ())
    monkeypatch.setattr(lifecycle, 'bootstrap_pah_shared', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lifecycle, '_code_analyzer_api_status', lambda *_args, **_kwargs: (True, None))
    if offline:
        monkeypatch.setenv('PIP_NO_INDEX', '1')
    else:
        monkeypatch.delenv('PIP_NO_INDEX', raising=False)
    calls = []

    def fake_run(args, **kwargs):
        calls.append([str(v) for v in args])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle, '_run', fake_run)
    lifecycle.install_python_components(root, Path('/fake/venv/bin/python'))
    editable = [cmd for cmd in calls if '-e' in cmd]
    assert len(editable) == len(PYTHON_COMPONENTS)
    assert all('--no-build-isolation' in cmd for cmd in editable)
    assert all('--no-deps' not in cmd for cmd in editable)
    assert all(not any('/modules/' in part for part in cmd) for cmd in editable)
    assert any('setuptools>=68' in cmd for cmd in calls)


def test_developer_extra_uses_same_backend(monkeypatch, tmp_path):
    probes = iter([1, 0])
    commands = []

    def fake_run(args, **kwargs):
        cmd = [str(x) for x in args]
        commands.append(cmd)
        if cmd[-2:] == ['-c', 'import pytest']:
            return SimpleNamespace(returncode=next(probes))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(lifecycle, '_run', fake_run)
    lifecycle.ensure_compatibility_test_dependencies(tmp_path, Path('/fake/python'))
    install = next(cmd for cmd in commands if '-e' in cmd)
    assert install[-3:] == ['--no-build-isolation', '-e', '.[dev]']
