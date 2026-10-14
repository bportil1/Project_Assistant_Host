"""JM-3A regression tests: host diagnostic events are opt-in and non-invasive."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from pah.job_instrumentation import HostWorkflowMonitor
from pah.jobs import JobMonitorAggregator
from pah_jobs import JobRegistry


def _jobs(observer):
    return observer.registry.snapshot()["jobs"]


def test_traces_record_success_and_exception_without_swallowing():
    o = HostWorkflowMonitor()
    with o.trace('Launch analysis step representation_analysis') as job:
        job.note('Selected inputs: feature_dataset')
        job.launched(SimpleNamespace(launched=True, metadata={}, presentation='url', module_id='hsqa_dbn'))
    assert _jobs(o)[0]['state'] == 'succeeded'
    lines = str(o.registry.outputs(_jobs(o)[0]['job_id']))
    assert 'Dispatch result: launched=True' in lines
    with pytest.raises(ValueError, match='missing reference'):
        with o.trace('Launch analysis step representation_analysis'):
            raise ValueError('missing reference')
    assert _jobs(o)[1]['state'] == 'failed'
    with pytest.raises(TimeoutError):
        with o.trace('Cppcheck launch'):
            raise TimeoutError('watchdog')
    assert _jobs(o)[2]['state'] == 'timed_out'


def test_artifact_change_deduplication_and_scope():
    o = HostWorkflowMonitor()
    row = {'kind': 'feature_dataset', 'artifact_id': 'current',
           'validation_state': 'valid', 'capabilities': ['benchmark_reference']}
    o.artifact_refresh('pypique', [row], workspace='project1', phase='quality_modeling')
    o.artifact_refresh('pypique', [row], workspace='project1', phase='quality_modeling')
    assert len(_jobs(o)) == 1
    o.artifact_refresh('pypique', [], workspace='project1', phase='mi_informed_analysis')
    assert len(_jobs(o)) == 2
    output = str(o.registry.outputs(_jobs(o)[1]['job_id']))
    assert 'Warning: no benchmark_reference' not in output  # MI-only is expected to omit it
    o.artifact_refresh('pypique', [], workspace='project1', phase='quality_modeling')
    assert len(_jobs(o)) == 3
    assert 'Warning: no benchmark_reference feature_dataset' in str(o.registry.outputs(_jobs(o)[2]['job_id']))
    o.artifact_refresh('pypique', [row], workspace='project2', phase='quality_modeling')
    assert len(_jobs(o)) == 4


def test_workflow_readiness_change_and_error_redaction():
    o = HostWorkflowMonitor()
    blocked = {'steps': [{'step_id': 'representation_analysis', 'state': 'blocked',
                          'blocking_reason': 'Missing required artifact: feature_dataset'}]}
    o.workflow_snapshot(blocked, workspace='experiment')
    o.workflow_snapshot(blocked, workspace='experiment')
    assert len(_jobs(o)) == 1
    o.workflow_snapshot({'steps': [{**blocked['steps'][0], 'state':'ready', 'blocking_reason': None}]}, workspace='experiment')
    assert len(_jobs(o)) == 2
    o.discovery_error('pypique', ValueError('Authorization: Bearer this-is-secret'))
    latest = _jobs(o)[2]
    assert latest['state'] == 'failed'
    assert 'this-is-secret' not in str(o.registry.outputs(latest['job_id']))


def test_module_owned_reader_explicit_opt_in_and_owner_isolation():
    o = HostWorkflowMonitor()
    agg = JobMonitorAggregator()
    agg.attach(o.registry.reader())
    child = JobRegistry('pypique')
    child.start('logical', 'GitHub scrape')
    class Registry:
        def module_ids(self): return ('pypique', 'hsqa_dbn')
        def get(self, module_id):
            return SimpleNamespace(job_reader=child.reader) if module_id == 'pypique' else object()
    o.attach_runtime_readers(Registry(), agg)
    o.attach_runtime_readers(Registry(), agg)
    assert sorted(source['owner'] for source in agg.snapshot()['sources']) == ['pah', 'pypique']
    assert agg.snapshot()['job_count'] == 1


@pytest.mark.skipif(not os.path.exists('/proc/self/stat'), reason='Linux PID identity only')
def test_verified_pid_is_child_of_dispatch_and_observed_without_signaling():
    o = HostWorkflowMonitor()
    with o.trace('Launch runtime pypique') as span:
        span.launched(SimpleNamespace(module_id='pypique', launched=True,
                                     metadata={'pid': os.getpid()}, presentation='url'))
    jobs = _jobs(o)
    assert len(jobs) == 2
    assert jobs[0]['state'] == 'succeeded'
    assert jobs[1]['kind'] == 'process' and jobs[1]['parent_id'] == jobs[0]['job_id']
    o.observe_processes()
    assert _jobs(o)[1]['liveness'] == 'alive'


def test_host_routes_trace_failures_when_flask_is_available(tmp_path):
    pytest.importorskip('flask')
    from pah.app import create_app
    app = create_app(state_dir=tmp_path / 'state')
    try:
        response = app.test_client().post('/api/orchestration/code-analysis/steps/representation_analysis/launch')
        assert response.status_code == 409
        monitor = app.extensions['pah_job_monitor']
        jobs = next(s['jobs'] for s in monitor.snapshot()['sources'] if s['owner'] == 'pah')
        assert any(j['label'] == 'Launch analysis step representation_analysis' and j['state'] == 'failed' for j in jobs)
    finally:
        app.extensions['pah_shutdown']()
