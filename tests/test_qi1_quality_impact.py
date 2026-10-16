"""QI-1: verified source model inspection; no scenario writes or invented edges."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.labs.quality_impact import (
    QualityImpactError, QualityImpactInspector, _link_evidence,
    _read_evidence, _recorded_network, _standard_network,
)


STANDARD = {
    'name': 'Model',
    'factors': {
        'tqi': {'Total': {'children': {'Maintainability': {}}}},
        'quality_aspects': {'Maintainability': {'children': {'Security': {}}}},
        'product_factors': {'Security': {'children': {'Count': {}}, 'weights': {'Count': 0.5}}},
    },
    'measures': {'Count': {'children': {'CWE-79': {}}}},
    'diagnostics': {'CWE-79': {'toolName': 'SAT', 'description': 'Explicit rule'},
                    'CWE-89': {'toolName': 'SAT'}},
}


def test_standard_network_is_exact_not_implicitly_full_connected():
    result = _standard_network(STANDARD)
    assert [node['kind'] for node in result['nodes']] == [
        'diagnostic', 'diagnostic', 'measure', 'product_factor', 'quality_aspect', 'tqi',
    ]
    assert {(row['source'], row['target']) for row in result['edges']} == {
        ('CWE-79', 'Count'), ('Count', 'Security'),
        ('Security', 'Maintainability'), ('Maintainability', 'Total'),
    }
    assert next(row['weight'] for row in result['edges'] if row['source'] == 'Count') == 0.5
    assert not any(row['source'] == 'CWE-89' for row in result['edges'])


def test_linking_requires_explicit_identifiers_and_leaves_missing_unmapped(tmp_path):
    source = tmp_path / 'findings.json'
    rows = {'diagnostics': {
        'CWE-79': [{'file_path': 'src/example.py', 'line': 11, 'severity': 2}],
        'CWE-999': [{'file_path': 'src/other.py', 'line': 20}],
    }}
    source.write_text(json.dumps(rows))
    before = source.read_bytes()
    observed = _read_evidence(source)
    linked = _link_evidence(_standard_network(STANDARD), observed)
    assert linked['linked_observations'] == 1
    assert linked['linked']['CWE-79'][0]['file_path'] == 'src/example.py'
    assert linked['linked']['CWE-79'][0]['line'] == 11
    assert linked['unmatched'][0]['diagnostic_id'] == 'CWE-999'
    assert source.read_bytes() == before


def test_mi_signed_network_and_probabilistic_backing_stay_separate():
    topology = {'nodes': [{'id': 'feature:CWE-79', 'kind': 'feature', 'feature_id': 'CWE-79'},
                          {'id': 'latent:1', 'kind': 'latent'}],
                'edges': [{'source': 'feature:CWE-79', 'target': 'latent:1',
                           'relationship': 'signed_information', 'signed_score': -0.3}]}
    probabilistic = {'nodes': [{'id': 'CWE-79', 'kind': 'cwe'}, {'id': 'latent:1', 'kind': 'latent'}],
                     'relationships': [{'source': 'CWE-79', 'target': 'latent:1',
                                        'relationship': 'learned_rbm_connection', 'weight': -0.6}]}
    signed = _recorded_network(topology, role='signed_information_topology', edge_key='edges')
    backing = _recorded_network(probabilistic, role='learned_probabilistic_backing', edge_key='relationships')
    assert signed['edges'][0]['signed_score'] == -0.3
    assert 'weight' not in signed['edges'][0]
    assert backing['edges'][0]['weight'] == -0.6
    evidence = {'path': 'p', 'sha256': '0' * 64,
                'findings': [{'diagnostic_id': 'CWE-79', 'file_path': 'test.py', 'line': 5}]}
    assert _link_evidence(signed, evidence)['linked']['feature:CWE-79'][0]['line'] == 5


def test_canonical_sat_cwe_fields_map_without_guessing(tmp_path):
    source = tmp_path / 'canonical.json'
    source.write_text(json.dumps({'findings': [
        {'cwe_id': 79, 'file_path': 'a.py', 'line': 5},
        {'cwes': ['CWE-79', 'CWE-89'], 'file_path': 'b.py', 'line': 9},
        {'rule_id': 'weak-name-similarity', 'file_path': 'c.py', 'line': 1},
    ]}))
    evidence = _read_evidence(source)
    links = _link_evidence(_standard_network(STANDARD), evidence)
    assert len(links['linked']['CWE-79']) == 2
    assert len(links['linked']['CWE-89']) == 1
    assert len(links['unmatched']) == 1


def test_input_rejects_unknown_evidence_shapes_and_links(tmp_path):
    source = tmp_path / 'findings.json'
    source.write_text(json.dumps({'data': [1, 2, 3]}))
    with pytest.raises(QualityImpactError, match='diagnostics map or findings array'):
        _read_evidence(source)
    source.unlink()
    source.symlink_to(tmp_path / 'other.json')
    with pytest.raises(QualityImpactError, match='symbolic link'):
        _read_evidence(source)


def fake_reader(path):
    if not Path(path).is_file() or Path(path).read_text() != 'valid':
        raise ValueError('Integrity verification failed')
    return {'family': 'standard_pique', 'version_id': 'fixture',
            'documents': {'model.json': STANDARD},
            'manifest': {'choice': 'configured'},
            'archive_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64}


def fake_summary(data):
    return {'comparison': {'unit': 'native_quality_model_value', 'rows': []}}


def test_selection_is_isolated_rechecked_and_atomic(tmp_path):
    good = tmp_path / 'good.zip'
    good.write_text('valid')
    bad = tmp_path / 'bad.zip'
    bad.write_text('invalid')
    inspector = QualityImpactInspector(reader=fake_reader, summarizer=fake_summary)
    first = inspector.select('workspace-A', str(good))
    assert first['selected'] and first['read_only'] and not first['scenarios_enabled']
    assert not inspector.snapshot('workspace-B')['selected']
    with pytest.raises(QualityImpactError, match='verification failed'):
        inspector.select('workspace-A', str(bad))
    assert inspector.snapshot('workspace-A')['selected']
    good.write_text('corrupted')
    snapshot = inspector.snapshot('workspace-A')
    assert not snapshot['selected']
    assert 'no longer verifies' in snapshot['diagnostic']
    inspector.clear('workspace-A')
    assert not inspector.snapshot('workspace-A')['selected']


def test_pa_handoff_endpoints_and_no_code_or_evidence_modification(tmp_path):
    pytest.importorskip('flask')
    from pah import create_app
    repo = tmp_path / 'code'
    repo.mkdir()
    source = repo / 'main.py'
    source.write_text('print(42)\n')
    archive = tmp_path / 'concluded.zip'
    archive.write_text('valid')
    findings = tmp_path / 'findings.json'
    findings.write_text(json.dumps({'diagnostics': {'CWE-79': [
        {'file_path': 'main.py', 'line': 1}
    ]}}))
    before = (source.read_bytes(), findings.read_bytes(), archive.read_bytes())
    app = create_app(state_dir=tmp_path / 'state')
    app.config['TESTING'] = True
    inspector = app.extensions['pah_quality_impact']
    inspector._reader = fake_reader
    inspector._summarizer = fake_summary
    with app.test_client() as client:
        assert client.post('/api/workspace/open', json={'path': str(repo)}).status_code == 200
        endpoint = '/api/orchestration/code-analysis/quality-impact'
        assert not client.get(endpoint).get_json()['selected']
        selected = client.post(endpoint + '/select', json={
            'path': str(archive), 'findings_path': str(findings),
        })
        assert selected.status_code == 200, selected.get_json()
        result = selected.get_json()
        assert result['network']['edges'][0]['source'] == 'CWE-79'
        assert result['evidence']['linked']['CWE-79'][0]['line'] == 1
        assert client.get(endpoint).get_json()['selected']
        assert client.post(endpoint + '/select', json={'path': str(tmp_path / 'missing.zip')}).status_code == 409
        assert client.get(endpoint).get_json()['selected']
        assert client.post(endpoint + '/clear').get_json()['selected'] is False
    assert before == (source.read_bytes(), findings.read_bytes(), archive.read_bytes())


def test_changed_sat_evidence_invalidates_selected_view(tmp_path):
    archive = tmp_path / 'archive.zip'
    archive.write_text('valid')
    findings = tmp_path / 'findings.json'
    findings.write_text(json.dumps({'diagnostics': {'CWE-79': [{'file_path': 'a.py', 'line': 1}]}}))
    inspector = QualityImpactInspector(reader=fake_reader, summarizer=fake_summary)
    inspector.select('project', str(archive), str(findings))
    findings.write_text(json.dumps({'diagnostics': {'CWE-79': [{'file_path': 'a.py', 'line': 2}]}}))
    after = inspector.snapshot('project')
    assert after['selected'] is False
    assert 'findings changed' in after['diagnostic']
    assert not inspector.snapshot('project')['selected']


def test_qi1_frontend_is_stage_four_and_does_not_remove_stage_two():
    root = Path(__file__).resolve().parents[1]
    from pah.labs.workflows import CODE_ANALYSIS_WORKFLOW
    assert [step.step_id for step in CODE_ANALYSIS_WORKFLOW.steps][1] == 'quality_modeling'
    assert CODE_ANALYSIS_WORKFLOW.steps[3].label == 'Quality Impact Analysis'
    ui = (root / 'pah/web/static/pah.js').read_text()
    assert "stepId === 'mi_informed_analysis'" in ui
    assert 'renderQualityImpactPanel(holder)' in ui
    assert 'quality-impact/select' in ui
    assert 'Separate learned probabilistic backing' in ui
    assert 'Stage 2 remains unchanged' in ui
