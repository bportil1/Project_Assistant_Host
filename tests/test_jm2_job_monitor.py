"""JM-2 read-only monitor routes and GUI contract."""
from __future__ import annotations

from pathlib import Path

import pytest

from pah_jobs import JobRegistry


def make_app(tmp_path):
    pytest.importorskip("flask")
    from pah.app import create_app
    return create_app(state_dir=tmp_path / "state")


ROOT = Path(__file__).resolve().parents[1]


def test_jm2_empty_registry_and_read_only_endpoints(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get('/api/jobs')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert [source['owner'] for source in response.json['sources']] == ['pah']
    assert response.json['job_count'] == 0
    assert client.post('/api/jobs').status_code == 405
    assert client.get('/api/jobs/nope/nope/output').status_code == 404
    app.extensions['pah_shutdown']()


def test_jm2_hierarchy_owner_isolation_and_logs(tmp_path):
    app = make_app(tmp_path)
    aggregator = app.extensions['pah_job_monitor']
    pypique = JobRegistry('pypique')
    hsqa = JobRegistry('hsqa_dbn')
    root = pypique.start('logical', 'GitHub scrape')
    worker = pypique.start('logical', 'Cppcheck worker', parent_id=root)
    pypique.output(worker, 'GITHUB_TOKEN=top-secret-abc')
    hsqa.start('logical', 'Trial 1')
    aggregator.attach(pypique.reader())
    aggregator.attach(hsqa.reader())
    client = app.test_client()
    response = client.get('/api/jobs')
    assert response.status_code == 200
    assert response.json['job_count'] == 3
    jobs = {job['job_id']: job for source in response.json['sources'] for job in source['jobs']}
    assert jobs[worker]['parent_id'] == root
    output = client.get(f'/api/jobs/pypique/{worker}/output')
    assert output.status_code == 200
    assert '[REDACTED]' in output.json['output'][0]['text']
    assert 'top-secret-abc' not in str(output.json)
    assert client.get(f'/api/jobs/hsqa_dbn/{worker}/output').status_code == 404
    assert client.get('/api/jobs/pypique/missing/output').status_code == 404
    for limit in ['0', '101', 'nan', '-1']:
        assert client.get(f'/api/jobs/pypique/{worker}/output?limit={limit}').status_code == 400
    assert client.post(f'/api/jobs/pypique/{worker}/output').status_code == 405
    app.extensions['pah_shutdown']()


def test_jm2_viewer_has_collapsible_controls_and_safe_renderer():
    template = (ROOT / 'pah/web/templates/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'pah/web/static/job-monitor.js').read_text(encoding='utf-8')
    css = (ROOT / 'pah/web/static/job-monitor.css').read_text(encoding='utf-8')
    assert 'id="jobMonitorDrawer"' in template and 'hidden>' in template
    assert 'id="toolsJobMonitor"' in template
    assert 'id="jobMonitorToggle"' in template
    assert 'id="jobMonitorTree"' in template
    assert 'id="jobMonitorLog"' in template
    assert 'job-monitor.js' in template
    assert '.job-monitor[hidden]' in css
    assert 'textContent' in js and 'replaceChildren' in js
    assert 'innerHTML' not in js and 'shell' not in js
    assert 'clearInterval(monitor.timer)' in js
    assert '/api/jobs' in js
