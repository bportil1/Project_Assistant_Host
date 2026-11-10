"""Producer-owned lifecycle and read-only observation tests (no Flask)."""
from datetime import datetime, timedelta, timezone
import pytest
from pah.jobs import JobMonitorAggregator
from pah_jobs import JobRegistry
from pah_jobs.observations import observe, SCHEMA
from pah_jobs.observation_history import ObservationHistory


def test_request_is_not_cancellation():
    reg = JobRegistry('pypique')
    j = reg.start('logical', 'job')
    reg.request_cancellation(j, reason='User requested')
    snap = reg.job(j)
    assert snap['state'] == 'running'
    assert snap['cancellation_requested_at'] is not None
    assert snap['cancellation_reason'] == 'User requested'
    reg.transition(j, 'cancelled')
    assert reg.job(j)['state'] == 'cancelled'
    with pytest.raises(ValueError):
        reg.request_cancellation(j)


def test_interrupted_and_cancelled_distinct():
    reg = JobRegistry('pypique')
    a = reg.start('logical', 'one')
    b = reg.start('logical', 'two')
    reg.transition(a, 'interrupted')
    reg.transition(b, 'cancelled')
    data = JobMonitorAggregator()
    data.attach(reg.reader())
    obs = {x['job_id']: x for x in data.snapshot()['observations']}
    assert obs[a]['producer_state'] == 'interrupted'
    assert obs[b]['producer_state'] == 'cancelled'
    assert obs[a]['producer_confirmed_terminal']
    assert obs[b]['producer_confirmed_terminal']


def test_staleness_is_observational_only():
    now = datetime.now(timezone.utc)
    data = observe({'job_id': 'a', 'state': 'running',
                    'updated_at': (now-timedelta(seconds=90)).isoformat()},
                   owner='ml_lab', now=now)
    assert data['schema'] == SCHEMA
    assert data['producer_state'] == 'running'
    assert data['telemetry_status'] == 'stale'
    assert not data['producer_confirmed_terminal']
    assert observe({'job_id': 'b', 'state': 'failed'}, owner='ml_lab')['telemetry_status'] == 'undated'


def test_optional_project_local_index(tmp_path):
    p = tmp_path / 'a'; q = tmp_path / 'b'; p.mkdir(); q.mkdir()
    a, b = ObservationHistory(p), ObservationHistory(q)
    record = observe({'job_id': 'j1', 'state': 'running'}, owner='hsqa_dbn')
    assert a.record([record]) == 1
    assert a.record([record]) == 0
    assert not b.recent()
    record['observed_state'] = 'cancelled'
    record['producer_state'] = 'cancelled'
    assert a.record([record]) == 1
    assert len(a.recent()) == 2
    assert a.path.is_file()


def test_history_rejects_bad_identity(tmp_path):
    index = ObservationHistory(tmp_path)
    with pytest.raises(ValueError):
        index.record([{'schema': SCHEMA, 'version': 1, 'owner': 'ml_lab', 'job_id': None}])
