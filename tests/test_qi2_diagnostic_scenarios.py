"""QI-2 reversibility, provenance, evidence integrity, and workspace isolation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.labs.quality_impact import QualityImpactInspector
from pah.labs.quality_impact_scenarios import (
    DiagnosticScenario, ScenarioError, editable_observations,
)


STANDARD = {
    'factors': {
        'tqi': {'Total': {'children': {'Maintainability': {}}}},
        'quality_aspects': {'Maintainability': {'children': {'Security': {}}}},
        'product_factors': {'Security': {'children': {'Count': {}}}},
    },
    'measures': {'Count': {'children': {'CWE-79': {}}}},
    'diagnostics': {'CWE-79': {'toolName': 'SAT'}, 'CWE-89': {'toolName': 'SAT'}},
}


def reader(path):
    if Path(path).read_text() != 'valid':
        raise ValueError('Invalid concluded model')
    return {'family': 'standard_pique', 'version_id': 'standard-version',
            'manifest': {'choice': 'native'}, 'documents': {'model.json': STANDARD},
            'archive_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64}


def summary(_):
    return {'comparison': {'unit': 'model_native', 'rows': []}}


def selected(tmp_path, name='A', *, with_evidence=True):
    root = tmp_path / name
    root.mkdir()
    model = root / 'model.zip'
    model.write_text('valid')
    evidence = root / 'findings.json'
    evidence.write_text(json.dumps({'findings': [
        {'cwe_id': 'CWE-79', 'file_path': 'src/test.c', 'line': 7},
        {'cwe_id': 79, 'file_path': 'src/test.c', 'line': 8},
        {'cwe_id': 'CWE-777', 'file_path': 'src/other.c', 'line': 3},
    ]}))
    inspector = QualityImpactInspector(reader=reader, summarizer=summary)
    response = inspector.select(name, str(model), str(evidence) if with_evidence else None)
    return inspector, model, evidence, response


def test_scenario_uses_explicit_record_count_not_invented_quality_inputs(tmp_path):
    inspector, model, evidence, view = selected(tmp_path)
    assert view['scenarios_enabled']
    scenario = view['scenario']
    assert scenario['read_only_sources'] and not scenario['evaluation_performed']
    assert scenario['changed_count'] == 0
    assert len(scenario['rows']) == 1  # CWE-89 has no SAT evidence: no inferred zero.
    row = scenario['rows'][0]
    assert row['node_id'] == 'CWE-79'
    assert row['baseline_value'] == 2
    assert row['scenario_value'] == 2
    assert row['unit'] == 'matched_sat_finding_count'
    assert row['diagnostic_ids'] == ['CWE-79']
    assert row['measure_ids'] == ['Count']
    assert not row['model_input_compatible']
    assert row['evidence_sha256'] == view['evidence']['source']['sha256']
    assert 'quality score' in scenario['warning']
    assert scenario['manifest_sha256'] == 'b' * 64


def test_set_undo_reset_log_revisions_are_reversible(tmp_path):
    inspector, _, evidence, original = selected(tmp_path)
    source_bytes = evidence.read_bytes()
    snap = inspector.scenario_action('A', 'set', node_id='CWE-79', value=4, expected_revision=0)
    s = snap['scenario']
    assert s['revision'] == 1
    assert s['changed_count'] == 1 and s['undo_available']
    assert s['rows'][0]['delta'] == 2
    assert s['history'][0]['old_value'] == 2
    assert s['history'][0]['new_value'] == 4
    assert s['history'][0]['sat_evidence_sha256'] == original['evidence']['source']['sha256']
    snap = inspector.scenario_action('A', 'set', node_id='CWE-79', value=1, expected_revision=1)
    assert snap['scenario']['rows'][0]['scenario_value'] == 1
    snap = inspector.scenario_action('A', 'undo', expected_revision=2)
    assert snap['scenario']['rows'][0]['scenario_value'] == 4
    snap = inspector.scenario_action('A', 'undo', expected_revision=3)
    assert snap['scenario']['changed_count'] == 0
    assert snap['scenario']['rows'][0]['scenario_value'] == 2
    assert [event['action'] for event in snap['scenario']['history']] == ['set', 'set', 'undo', 'undo']
    with pytest.raises(ScenarioError, match='no scenario edit'):
        inspector.scenario_action('A', 'undo', expected_revision=4)
    inspector.scenario_action('A', 'set', node_id='CWE-79', value=0, expected_revision=4)
    reset = inspector.scenario_action('A', 'reset', expected_revision=5)['scenario']
    assert reset['revision'] == 6 and reset['changed_count'] == 0
    assert reset['rows'][0]['scenario_value'] == 2
    assert [event['action'] for event in reset['history']][-2:] == ['set', 'reset']
    assert reset['history'][-1]['discarded_overrides'] == [{'node_id': 'CWE-79', 'old_value': 0, 'new_value': 2}]
    assert not reset['undo_available']
    assert evidence.read_bytes() == source_bytes


def test_unlinked_ids_stale_revisions_and_bad_values_are_rejected(tmp_path):
    inspector, _, _, _ = selected(tmp_path)
    for node in ('CWE-89', 'Count', 'Total', 'unknown', None):
        with pytest.raises(ScenarioError, match='explicitly SAT-linked'):
            inspector.scenario_action('A', 'set', node_id=node, value=3, expected_revision=0)
    for bad in (True, 2.5, '2', -1, 1_000_000_001, None):
        with pytest.raises(ScenarioError, match='nonnegative integers'):
            inspector.scenario_action('A', 'set', node_id='CWE-79', value=bad, expected_revision=0)
    with pytest.raises(ScenarioError, match='stale'):
        inspector.scenario_action('A', 'set', node_id='CWE-79', value=4, expected_revision='0')
    with pytest.raises(ScenarioError, match='No change'):
        inspector.scenario_action('A', 'set', node_id='CWE-79', value=2, expected_revision=0)
    assert inspector.snapshot('A')['scenario']['revision'] == 0
    inspector.scenario_action('A', 'set', node_id='CWE-79', value=3, expected_revision=0)
    with pytest.raises(ScenarioError, match='stale'):
        inspector.scenario_action('A', 'set', node_id='CWE-79', value=4, expected_revision=0)
    assert inspector.snapshot('A')['scenario']['rows'][0]['scenario_value'] == 3


def test_no_evidence_means_no_editing(tmp_path):
    inspector, _, _, view = selected(tmp_path, with_evidence=False)
    assert not view['scenarios_enabled']
    assert not view['scenario']['rows']
    with pytest.raises(ScenarioError, match='No explicitly SAT-linked'):
        inspector.scenario_action('A', 'set', node_id='CWE-79', value=3, expected_revision=0)


def test_concluded_model_or_evidence_change_drops_hypothetical_state(tmp_path):
    inspector, model, evidence, _ = selected(tmp_path)
    inspector.scenario_action('A', 'set', node_id='CWE-79', value=8, expected_revision=0)
    evidence.write_text(json.dumps({'findings': [{'cwe_id': 79, 'line': 12}]}))
    invalid = inspector.snapshot('A')
    assert not invalid['selected'] and 'changed' in invalid['diagnostic']
    recovered = inspector.select('A', str(model), str(evidence))
    assert recovered['scenario']['revision'] == 0
    assert recovered['scenario']['rows'][0]['baseline_value'] == 1
    assert recovered['scenario']['rows'][0]['scenario_value'] == 1
    inspector.scenario_action('A', 'set', node_id='CWE-79', value=7, expected_revision=0)
    model.write_text('corrupt')
    assert not inspector.snapshot('A')['selected']
    assert not inspector.snapshot('A')['selected']


def test_independent_workspace_selection_and_clear(tmp_path):
    insp, model_a, ev_a, view_a = selected(tmp_path, 'A')
    root_b = tmp_path / 'B'
    root_b.mkdir()
    model_b = root_b / 'model.zip'
    model_b.write_text('valid')
    ev_b = root_b / 'findings.json'
    ev_b.write_text(json.dumps({'diagnostics': {'CWE-79': [{'line': 2}]}}))
    insp.select('B', str(model_b), str(ev_b))
    insp.scenario_action('A', 'set', node_id='CWE-79', value=10, expected_revision=0)
    assert insp.snapshot('B')['scenario']['rows'][0]['scenario_value'] == 1
    assert insp.snapshot('B')['scenario']['revision'] == 0
    assert insp.snapshot('A')['scenario']['rows'][0]['scenario_value'] == 10
    insp.clear('A')
    assert not insp.snapshot('A')['selected']
    assert insp.snapshot('B')['selected']
    insp.select('A', str(model_a), str(ev_a))
    assert insp.snapshot('A')['scenario']['revision'] == 0


def test_mi_feature_input_is_supported_but_latent_and_backing_are_not():
    inspection = {
        'family': 'mi_informed_pique', 'version_id': 'mi-1',
        'manifest_sha256': 'f' * 64, 'archive_sha256': 'e' * 64,
        'network': {'nodes': [
            {'id': 'feature:CWE-79', 'kind': 'feature', 'feature_id': 'CWE-79'},
            {'id': 'latent:1', 'kind': 'latent'},
        ], 'edges': [{'source': 'feature:CWE-79', 'target': 'latent:1'}]},
        'probabilistic_backing': {'nodes': [{'id': 'CWE-79', 'kind': 'cwe'}], 'edges': []},
        'evidence': {'source': {'sha256': 'd' * 64, 'path': '/tmp/findings.json'},
                     'linked': {'feature:CWE-79': [{'diagnostic_id': 'CWE-79'}],
                                'latent:1': [{'diagnostic_id': 'CWE-79'}]}},
    }
    editable = editable_observations(inspection)
    assert list(editable) == ['feature:CWE-79']
    assert not editable['feature:CWE-79']['model_input_compatible']
    assert editable['feature:CWE-79']['measure_ids'] == []
    scenario = DiagnosticScenario(inspection)
    scenario.set_value('feature:CWE-79', 0, expected_revision=0)
    assert scenario.to_dict()['rows'][0]['delta'] == -1


def test_qi2_flask_route_and_ui_contract(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ui = (root / 'pah/web/static/pah.js').read_text()
    assert 'quality-impact/scenario' in ui
    assert 'Temporary diagnostic evidence scenario' in ui
    assert 'Undo last change' in ui and 'Reset scenario' in ui
    assert 'Separate learned probabilistic backing' in ui
    pytest.importorskip('flask')
    from pah import create_app
    workspace = tmp_path / 'repo'
    workspace.mkdir()
    archive = tmp_path / 'archive.zip'
    archive.write_text('valid')
    findings = tmp_path / 'findings.json'
    findings.write_text(json.dumps({'diagnostics': {'CWE-79': [{'line': 1}]}}))
    original = (archive.read_bytes(), findings.read_bytes())
    app = create_app(state_dir=tmp_path / 'state')
    app.config['TESTING'] = True
    inspector = app.extensions['pah_quality_impact']
    inspector._reader = reader
    inspector._summarizer = summary
    base = '/api/orchestration/code-analysis/quality-impact'
    with app.test_client() as client:
        assert client.post('/api/workspace/open', json={'path': str(workspace)}).status_code == 200
        selection = client.post(base + '/select', json={'path': str(archive), 'findings_path': str(findings)})
        assert selection.status_code == 200
        response = client.post(base + '/scenario', json={'action': 'set', 'node_id': 'CWE-79',
                                                        'value': 3, 'expected_revision': 0})
        assert response.status_code == 200
        assert response.get_json()['scenario']['rows'][0]['scenario_value'] == 3
        assert client.get(base).get_json()['scenario']['rows'][0]['scenario_value'] == 3
        stale = client.post(base + '/scenario', json={'action': 'set', 'node_id': 'CWE-79',
                                                     'value': 4, 'expected_revision': 0})
        assert stale.status_code == 409
        undo = client.post(base + '/scenario', json={'action': 'undo', 'expected_revision': 1})
        assert undo.get_json()['scenario']['changed_count'] == 0
        assert client.post(base + '/clear').get_json()['selected'] is False
        assert client.post(base + '/scenario', json={'action': 'undo', 'expected_revision': 0}).status_code == 409
    assert (archive.read_bytes(), findings.read_bytes()) == original
