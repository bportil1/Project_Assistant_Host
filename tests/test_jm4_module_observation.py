"""JM-4 opt-in module job telemetry; no Flask or external work required."""
from pathlib import Path
import os
import pytest

from pah_jobs.exchange import (
    WorkspaceJobReader, monitor_directory, monitor_root, observed, job_scope,
)


def test_all_supported_module_owners_publish_and_are_workspace_scoped(tmp_path, monkeypatch):
    monkeypatch.delenv('PAH_JOB_MONITOR_DIR', raising=False)
    owners = ('ml_lab','code_analyzer','tech_documents','reference_manager','research_search')
    a,b = tmp_path/'a',tmp_path/'b'
    for owner in owners:
        with monitor_directory(a):
            assert monitor_root() == str(a.resolve())
            with job_scope(owner, 'Observed operation'):
                pass
        assert len(WorkspaceJobReader(a,owner).snapshot()['jobs']) == 1
        assert WorkspaceJobReader(b,owner).snapshot()['jobs'] == []
    assert monitor_root() is None


def test_observed_preserves_return_error_and_nesting(tmp_path):
    @observed('ml_lab','outer task')
    def task():
        return inner()
    @observed('ml_lab','inner task')
    def inner():
        return 19
    @observed('ml_lab','failing task')
    def broken():
        raise LookupError('intentional error')
    with monitor_directory(tmp_path):
        assert task() == 19
        with pytest.raises(LookupError,match='intentional error'):
            broken()
    jobs=WorkspaceJobReader(tmp_path,'ml_lab').snapshot()['jobs']
    by_label={x['label']:x for x in jobs}
    assert by_label['inner task']['parent_id'] == by_label['outer task']['job_id']
    assert by_label['failing task']['state'] == 'failed'
    assert by_label['outer task']['state'] == 'succeeded'


def test_unsuccessful_result_is_reported_not_raised(tmp_path):
    class Outcome:
        ok=False
    @observed('tech_documents','preflight')
    def operation():
        return Outcome()
    with monitor_directory(tmp_path):
        result=operation()
    assert result.ok is False
    row=WorkspaceJobReader(tmp_path,'tech_documents').snapshot()['jobs'][0]
    assert row['state'] == 'failed'


def test_monitor_restores_workspace_across_exceptions(tmp_path):
    with pytest.raises(ZeroDivisionError):
        with monitor_directory(tmp_path):
            assert monitor_root()
            1 / 0
    assert monitor_root() is None
