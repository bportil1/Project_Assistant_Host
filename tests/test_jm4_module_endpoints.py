"""Check actual module boundaries emit job entries without changing results."""
from pathlib import Path
import time

from pah_jobs.exchange import WorkspaceJobReader, monitor_directory


def test_ml_lab_task_emits_record(tmp_path):
    from ml_lab.application import execute_task
    with monitor_directory(tmp_path):
        result=execute_task('data.inspect',{'paths': [str(tmp_path)]})
    assert result['task']=='data.inspect'
    assert any(row['label']=='ML Lab task execution' and row['state']=='succeeded'
               for row in WorkspaceJobReader(tmp_path,'ml_lab').snapshot()['jobs'])


def test_ml_lab_profile_background_keeps_own_workspace(tmp_path, monkeypatch):
    from ml_lab.ui import jobs
    class Data:
        profiles = [object()]
        warnings = []
    seen=[]
    def profile_paths(*args, progress, **kwargs):
        progress({'stage':'profiling_file','current':1,'total':1})
        return Data()
    def persist_profile_run(*args, **kwargs):
        return {'status':'ok'}
    monkeypatch.setattr(jobs.data,'profile_paths',profile_paths)
    monkeypatch.setattr(jobs.data,'persist_profile_run',persist_profile_run)
    manager=jobs.ProfileJobManager(output_root=tmp_path/'results')
    with monitor_directory(tmp_path/'monitor'):
        job_id=manager.start({'paths':[str(tmp_path/'source.csv')]})
    for _ in range(200):
        rec=manager.get(job_id)
        if rec['status'] in {'completed','failed'}:
            break
        time.sleep(0.01)
    assert rec['status']=='completed',rec
    records=WorkspaceJobReader(tmp_path/'monitor','ml_lab').snapshot()['jobs']
    assert len(records)==1 and records[0]['state']=='succeeded'
    assert records[0]['run_id']==job_id


def test_code_analyzer_scanning_and_comparison(tmp_path):
    from code_analyzer.api import CodeAnalyzer
    project=tmp_path/'source'
    project.mkdir()
    (project/'a.py').write_text('def foo(x):\n    return x+1\n')
    with monitor_directory(tmp_path/'monitor'):
        analyzer=CodeAnalyzer(project)
        result=analyzer.catalog_dict(refresh=True)
    assert result
    labels={job['label'] for job in WorkspaceJobReader(tmp_path/'monitor','code_analyzer').snapshot()['jobs']}
    assert 'Scan repository and build catalog' in labels
    assert 'Repository catalog' in labels


def test_documents_invalid_compile_keeps_original_exception(tmp_path):
    from tech_documents.api import DocumentEngine
    from tech_documents.errors import UnsupportedFileTypeError
    import pytest
    engine=DocumentEngine(base_dir=tmp_path/'doc')
    project=tmp_path/'project';project.mkdir()
    (project/'a.md').write_text('hello')
    with monitor_directory(tmp_path/'monitor'):
        with pytest.raises(UnsupportedFileTypeError):
            engine.compile_latex_path(project,'a.md')
    rows=WorkspaceJobReader(tmp_path/'monitor','tech_documents').snapshot()['jobs']
    assert rows and rows[0]['state']=='failed'
