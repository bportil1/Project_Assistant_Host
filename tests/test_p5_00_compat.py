"""Offline runner contract: never report absent suites or failures as passing."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

RUNNER = Path(__file__).resolve().parents[1] / 'tools' / 'p5_00_compat.py'
spec = importlib.util.spec_from_file_location('p5_00_compat', RUNNER)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


def test_manifest_records_all_five_archival_baselines():
    document = json.loads(compat.MANIFEST.read_text())
    assert set(document['modules']) == {'pah','pypique','hsqa_dbn','ml_lab','code_analyzer'}
    for name, cfg in document['modules'].items():
        assert len(cfg['archive_baseline']['sha256']) == 64
        assert cfg['suites']['baseline']


def test_suite_selection_deduplicates_without_changing_order():
    cfg = {'suites':{'baseline':['tests/a.py','tests/b.py'], 'scenario':['tests/b.py','tests/c.py']}}
    assert compat._tests_for(cfg,'all') == ['tests/a.py','tests/b.py','tests/c.py']
    assert compat._tests_for(cfg,'scenario') == ['tests/b.py','tests/c.py']
    assert compat._tests_for({'suites':cfg['suites'] | {'scenario':[]}},'scenario') == []


def test_missing_repo_reports_unavailable_without_running(tmp_path):
    result = compat._run_one('stub', {'suites':{'baseline':['tests/a.py']},
                              'archive_baseline':{'sha256':'0'*64},'pythonpath':'.'},
                             root=tmp_path / 'missing', python=Path(sys.executable),
                             profile='baseline', timeout=5)
    assert result['status'] == 'unavailable'
    assert result['exit_code'] is None


def test_missing_test_reports_unavailable_without_running(tmp_path):
    result = compat._run_one('stub', {'suites':{'baseline':['tests/a.py']},
                              'archive_baseline':{'sha256':'0'*64},'pythonpath':'.'},
                             root=tmp_path, python=Path(sys.executable),
                             profile='baseline', timeout=5)
    assert result['status'] == 'unavailable'
    assert result['missing'] == ['tests/a.py']


def test_mocked_pytest_failure_is_not_reported_as_pass(tmp_path, monkeypatch):
    (tmp_path/'tests').mkdir()
    (tmp_path/'tests/a.py').write_text('def test_foo(): pass\n')
    class Completed:
        returncode=1
        stdout='1 failed, 2 passed in 0.1s'
        stderr=''
    monkeypatch.setattr(compat.subprocess,'run',lambda *a,**kw: Completed())
    result=compat._run_one('stub', {'suites':{'baseline':['tests/a.py']},
                              'archive_baseline':{'sha256':'0'*64},'pythonpath':'.'},
                             root=tmp_path, python=Path(sys.executable),
                             profile='baseline', timeout=5)
    assert result['status']=='failed'
    assert result['counts']=={'failed':1,'passed':2}
    assert result['file_sha256']['tests/a.py']
