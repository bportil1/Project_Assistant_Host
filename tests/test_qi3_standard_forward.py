"""QI-3: authentic Standard model evaluation with an explicit native input bridge."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.labs.quality_impact import QualityImpactInspector
from pah.labs.quality_impact_forward import ForwardEvaluationError


MODEL = {
    'name': 'Native-QI-3',
    'factors': {
        'tqi': {'Total': {'children': {'QA': {}}, 'weights': {'QA': 1.0}}},
        'quality_aspects': {'QA': {'children': {'PF': {}}, 'weights': {'PF': 1.0}}},
        'product_factors': {'PF': {'children': {'M1': {}, 'M2': {}},
                                   'aggregation': 'legacy_arithmetic_mean'}},
    },
    'measures': {
        'M1': {'children': {'D1': {}}, 'positive': True, 'thresholds': [0, 10],
               'utility_function': 'pique.evaluation.DefaultUtility'},
        'M2': {'children': {'D2': {}}, 'positive': True, 'thresholds': [0, 10],
               'utility_function': 'pique.evaluation.DefaultUtility'},
    },
    'diagnostics': {'D1': {'toolName': 'SAT'}, 'D2': {'toolName': 'SAT'}},
}


def setup_real_standard(tmp_path):
    pytest.importorskip('pique_py')
    from pique_py.io import load_quality_model
    from pique_py.standard_model_conclusion import write_standard_conclusion
    from pique_py.finalized_model_registry import read_conclusion

    model_source = tmp_path / 'model.json'
    model_source.write_text(json.dumps(MODEL))
    source_evidence = tmp_path / 'source_evidence.json'
    source_evidence.write_text(json.dumps({'diagnostics': {'D1': 2, 'D2': 6}}))
    acceptance = {'node_values': {'PF': 0.4, 'Total': 0.4}}
    conclusion = write_standard_conclusion(
        results_dir=tmp_path, model=load_quality_model(model_source),
        source_model=model_source, findings=source_evidence,
        choice='configured', configuration={}, baseline=acceptance,
        selected=acceptance)
    path = Path(conclusion['archive_path'])
    inspected_evidence = tmp_path / 'sat_findings.json'
    inspected_evidence.write_text(json.dumps({'findings': [
        {'diagnostic_id': 'D1', 'file_path': 'a.py'} for _ in range(2)
    ] + [{'diagnostic_id': 'D2', 'file_path': 'a.py'} for _ in range(6)]}))
    inspector = QualityImpactInspector()
    snap = inspector.select('A', str(path), str(inspected_evidence))
    assert read_conclusion(path)['version_id'] == snap['version_id']
    return inspector, path, inspected_evidence, snap


def create_mapping(tmp_path, snap, *, records=None):
    records = records or {
        'D1': {'baseline_native_value': 2, 'native_units_per_finding': 1,
               'provenance': 'Documented unit-severity native finding sum'},
        'D2': {'baseline_native_value': 6, 'native_units_per_finding': 1,
               'provenance': 'Documented unit-severity native finding sum'},
    }
    document = {'schema': 'pah.standard_native_diagnostic_mapping', 'schema_version': 1,
                'model_manifest_sha256': snap['manifest_sha256'],
                'sat_evidence_sha256': snap['evidence']['source']['sha256'],
                'diagnostics': records}
    path = tmp_path / 'native_inputs.json'
    path.write_text(json.dumps(document))
    return path


def test_real_concluded_forward_uses_actual_model_evaluators(tmp_path):
    insp, model, evidence, snap = setup_real_standard(tmp_path)
    before = model.read_bytes(), evidence.read_bytes()
    assert snap['forward_evaluation']['status'] == 'needs_mapping'
    path = create_mapping(tmp_path, snap)
    bound = insp.bind_native_inputs('A', str(path))
    result = bound['forward_evaluation']
    assert result['status'] == 'ready'
    assert result['baseline']['node_values']['diagnostic'] == {'D1': 2, 'D2': 6}
    assert result['baseline']['node_values']['measure'] == pytest.approx({'M1': 0.2, 'M2': 0.6})
    assert result['baseline']['node_values']['product_factor']['PF'] == pytest.approx(0.4)
    assert result['baseline']['node_values']['tqi']['Total'] == pytest.approx(0.4)
    assert result['scenario']['tqi'] == pytest.approx(0.4)
    updated = insp.scenario_action('A', 'set', node_id='D1', value=4, expected_revision=0)
    evaluated = updated['forward_evaluation']
    assert evaluated['scenario']['node_values']['diagnostic']['D1'] == pytest.approx(4)
    assert evaluated['scenario']['node_values']['measure']['M1'] == pytest.approx(0.4)
    assert evaluated['scenario']['node_values']['measure']['M2'] == pytest.approx(0.6)
    assert evaluated['scenario']['node_values']['product_factor']['PF'] == pytest.approx(0.5)
    assert evaluated['scenario']['tqi'] == pytest.approx(0.5)
    assert evaluated['native_input_transformations'][0]['assumption'] == 'operator_supplied_linear_per_finding_conversion'
    assert 'pique_py.QualityModel' in evaluated['scenario']['evaluation_engine']
    undone = insp.scenario_action('A', 'undo', expected_revision=1)
    assert undone['forward_evaluation']['scenario']['tqi'] == pytest.approx(0.4)
    assert (model.read_bytes(), evidence.read_bytes()) == before


def test_invalid_binding_does_not_replace_existing_verified_mapping(tmp_path):
    insp, model, evidence, snap = setup_real_standard(tmp_path)
    path = create_mapping(tmp_path, snap)
    assert insp.bind_native_inputs('A', str(path))['forward_evaluation']['status'] == 'ready'
    invalid = tmp_path / 'wrong.json'
    doc = json.loads(path.read_text())
    doc['sat_evidence_sha256'] = 'f' * 64
    invalid.write_text(json.dumps(doc))
    with pytest.raises(ForwardEvaluationError, match='fingerprint'):
        insp.bind_native_inputs('A', str(invalid))
    assert insp.snapshot('A')['forward_evaluation']['status'] == 'ready'
    doc['sat_evidence_sha256'] = snap['evidence']['source']['sha256']
    doc['diagnostics'].pop('D2')
    invalid.write_text(json.dumps(doc))
    with pytest.raises(ForwardEvaluationError, match='missing'):
        insp.bind_native_inputs('A', str(invalid))
    doc['diagnostics']['D2'] = {'baseline_native_value': True, 'provenance': 'bad'}
    invalid.write_text(json.dumps(doc))
    with pytest.raises(ForwardEvaluationError, match='finite numeric'):
        insp.bind_native_inputs('A', str(invalid))


def test_changed_mapping_invalidates_only_native_bridge(tmp_path):
    insp, _, _, snap = setup_real_standard(tmp_path)
    path = create_mapping(tmp_path, snap)
    insp.bind_native_inputs('A', str(path))
    insp.scenario_action('A', 'set', node_id='D1', value=4, expected_revision=0)
    path.write_text(path.read_text() + '\n ')
    current = insp.snapshot('A')
    assert current['selected']
    assert current['scenario']['revision'] == 1
    assert current['forward_evaluation']['status'] == 'blocked'
    assert current['forward_evaluation']['native_mapping_invalidated']
    assert insp.snapshot('A')['forward_evaluation']['status'] == 'needs_mapping'


def test_missing_per_finding_factor_blocks_scenario_not_native_baseline(tmp_path):
    insp, _, _, snap = setup_real_standard(tmp_path)
    records = {
        'D1': {'baseline_native_value': 2, 'provenance': 'measured output'},
        'D2': {'baseline_native_value': 6, 'provenance': 'measured output'},
    }
    path = create_mapping(tmp_path, snap, records=records)
    insp.bind_native_inputs('A', str(path))
    updated = insp.scenario_action('A', 'set', node_id='D1', value=5, expected_revision=0)
    result = updated['forward_evaluation']
    assert result['status'] == 'scenario_blocked'
    assert result['baseline']['tqi'] == pytest.approx(0.4)
    assert result['scenario'] is None
    assert 'native_units_per_finding' in result['reason']


def test_native_bridge_is_workspace_scoped_and_not_usable_for_mi(tmp_path):
    insp, model, evidence, snap = setup_real_standard(tmp_path)
    path = create_mapping(tmp_path, snap)
    insp.bind_native_inputs('A', str(path))
    assert insp.select('B', str(model), str(evidence))['forward_evaluation']['status'] == 'needs_mapping'
    assert insp.snapshot('A')['forward_evaluation']['status'] == 'ready'
    insp.clear_native_inputs('A')
    assert insp.snapshot('A')['forward_evaluation']['status'] == 'needs_mapping'
    assert insp.snapshot('B')['selected']


def test_qi3_ui_and_api_wiring():
    root = Path(__file__).resolve().parents[1]
    ui = (root / 'pah/web/static/pah.js').read_text()
    app = (root / 'pah/app.py').read_text()
    assert 'Standard PIQUE native forward evaluation' in ui
    assert 'Bind verified native inputs' in ui
    assert 'forward/inputs' in app and 'forward/clear' in app
    assert 'Hypothetical scenario' in ui


def test_qi3_flask_binding_uses_existing_workspace_and_scenario(tmp_path):
    pytest.importorskip('flask')
    from pah import create_app
    _, archive, evidence, _ = setup_real_standard(tmp_path)
    app = create_app(state_dir=tmp_path / 'state')
    app.config['TESTING'] = True
    workspace = tmp_path / 'repo'
    workspace.mkdir()
    route = '/api/orchestration/code-analysis/quality-impact'
    with app.test_client() as client:
        assert client.post('/api/workspace/open', json={'path': str(workspace)}).status_code == 200
        initial = client.post(route + '/select', json={'path': str(archive), 'findings_path': str(evidence)}).get_json()
        assert initial['forward_evaluation']['status'] == 'needs_mapping'
        mapping = create_mapping(tmp_path, initial)
        attached = client.post(route + '/forward/inputs', json={'path': str(mapping)})
        assert attached.status_code == 200
        assert attached.get_json()['forward_evaluation']['status'] == 'ready'
        changed = client.post(route + '/scenario', json={
            'action': 'set', 'node_id': 'D1', 'value': 3, 'expected_revision': 0,
        }).get_json()
        assert changed['forward_evaluation']['scenario']['tqi'] == pytest.approx(0.45)
        detached = client.post(route + '/forward/clear', json={}).get_json()
        assert detached['forward_evaluation']['status'] == 'needs_mapping'
        assert detached['scenario']['revision'] == 1
        assert client.get(route).get_json()['selected']
