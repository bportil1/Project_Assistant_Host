"""QI-4: source-isolated comparisons, exact recorded paths, explicit export."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.labs.quality_impact import QualityImpactInspector
from pah.labs.quality_impact_comparison import (
    ComparisonError, build_comparison, native_rows, reachable_paths,
)
from test_qi2_diagnostic_scenarios import selected
from test_qi3_standard_forward import setup_real_standard, create_mapping


def test_explicit_paths_skip_unrecorded_edges_and_do_not_claim_causality():
    network = {'nodes': [{'id': name} for name in ('D1', 'D2', 'M1', 'PF', 'TQI')],
               'edges': [{'source': 'D1', 'target': 'M1'},
                         {'source': 'M1', 'target': 'PF'},
                         {'source': 'PF', 'target': 'TQI'},
                         {'source': 'D2', 'target': 'ghost'},
                         {'source': 'TQI', 'target': 'M1'}]}
    result = reachable_paths(network, ['D1'], [{'node_id': 'PF', 'delta': .2}], family='standard_pique')
    assert result['reachable_nodes'] == ['D1', 'M1', 'PF', 'TQI']
    assert result['recorded_edge_indices'] == [0, 1, 2, 4]  # includes recorded cycle, no fabricated links
    assert result['native_changed_nodes'] == ['PF']
    assert 'not causal' in result['meaning']
    mi = reachable_paths(network, ['D1'], [], family='mi_informed_pique')
    assert mi['relationship'] == 'recorded_information_topology_context_only'
    assert mi['native_changed_nodes'] == []


def test_qi2_observation_only_comparison_no_guessed_quality_deltas(tmp_path):
    inspector, model, evidence, initial = selected(tmp_path)
    before = model.read_bytes(), evidence.read_bytes()
    assert initial['comparison']['status'] == 'observation_only'
    updated = inspector.scenario_action('A', 'set', node_id='CWE-79', value=5, expected_revision=0)
    comp = updated['comparison']
    assert comp['observations'][0]['delta'] == 3
    assert comp['observations'][0]['unit'] == 'matched_sat_finding_count'
    assert comp['native_values'] == []
    assert comp['network_highlights']['reachable_nodes'] == ['CWE-79', 'Count', 'Maintainability', 'Security', 'Total']
    assert len(comp['network_highlights']['recorded_edge_indices']) == 4
    assert 'no' in updated['forward_evaluation']['reason'].lower() or updated['forward_evaluation']['status'] == 'needs_mapping'
    assert (model.read_bytes(), evidence.read_bytes()) == before


def test_real_native_quality_comparison_changes_only_native_nodes(tmp_path):
    inspector, model, evidence, initial = setup_real_standard(tmp_path)
    mapping = create_mapping(tmp_path, initial)
    inspector.bind_native_inputs('A', str(mapping))
    updated = inspector.scenario_action('A', 'set', node_id='D1', value=4, expected_revision=0)
    comp = updated['comparison']
    assert comp['status'] == 'native_ready'
    assert comp['observations'][0]['delta'] == 2
    rows = {(r['kind'], r['node_id']): r for r in comp['native_values']}
    assert rows['diagnostic', 'D1']['delta'] == pytest.approx(2)
    assert rows['measure', 'M1']['delta'] == pytest.approx(.2)
    assert rows['measure', 'M2']['delta'] == 0
    assert rows['product_factor', 'PF']['delta'] == pytest.approx(.1)
    assert rows['tqi', 'Total']['delta'] == pytest.approx(.1)
    assert 'D1' in comp['network_highlights']['reachable_nodes']
    assert 'D2' not in comp['network_highlights']['reachable_nodes']
    undone = inspector.scenario_action('A', 'undo', expected_revision=1)
    assert all(row['delta'] == 0 for row in undone['comparison']['native_values'])
    assert undone['comparison']['network_highlights']['recorded_edge_indices'] == []


def test_checkpoints_compare_distinct_hypothetical_revisions_and_reset(tmp_path):
    inspector, _, _, original = setup_real_standard(tmp_path)
    inspector.bind_native_inputs('A', str(create_mapping(tmp_path, original)))
    first = inspector.scenario_action('A', 'set', node_id='D1', value=4, expected_revision=0)
    captured = inspector.comparison_action('A', 'capture', label='After D1', expected_revision=1)
    ref = captured['comparison_checkpoints'][0]['id']
    second = inspector.scenario_action('A', 'set', node_id='D1', value=6, expected_revision=1)
    selected = inspector.comparison_action('A', 'select', checkpoint_id=ref, expected_revision=2)
    comp = selected['comparison']
    assert comp['reference_revision'] == 1 and comp['scenario_revision'] == 2
    assert next(r for r in comp['observations'] if r['node_id'] == 'D1')['delta'] == 2
    assert next(r for r in comp['native_values'] if r['kind'] == 'tqi')['delta'] == pytest.approx(.1)
    reset = inspector.scenario_action('A', 'reset', expected_revision=2)
    assert reset['comparison']['reference_id'] == ref
    assert next(r for r in reset['comparison']['observations'] if r['node_id'] == 'D1')['delta'] == -2
    removed = inspector.comparison_action('A', 'remove', checkpoint_id=ref, expected_revision=3)
    assert removed['comparison']['reference_id'] == 'baseline'
    assert not removed['comparison_checkpoints']


def test_validation_is_revision_guarded_and_workspaces_isolated(tmp_path):
    inspector, model, evidence, initial = selected(tmp_path)
    with pytest.raises(ComparisonError, match='revision'):
        inspector.comparison_action('A', 'capture', label='bad', expected_revision=True)
    with pytest.raises(ComparisonError, match='label'):
        inspector.comparison_action('A', 'capture', label='', expected_revision=0)
    assert len(inspector.comparison_action('A', 'capture', label='A', expected_revision=0)['comparison_checkpoints']) == 1
    assert inspector.select('B', str(model), str(evidence))['comparison_checkpoints'] == []
    with pytest.raises(ComparisonError, match='Unknown'):
        inspector.comparison_action('B', 'select', checkpoint_id='not-an-id', expected_revision=0)
    evidence.write_text(evidence.read_text() + ' ')
    assert not inspector.snapshot('A')['selected']
    assert not inspector.snapshot('B')['selected']
    assert inspector._checkpoints.get('A') is None


def test_native_mapping_change_never_compares_incompatible_native_values(tmp_path):
    inspector, _, _, initial = setup_real_standard(tmp_path)
    mapping = create_mapping(tmp_path, initial)
    inspector.bind_native_inputs('A', str(mapping))
    inspector.comparison_action('A', 'capture', label='Mapped', expected_revision=0)
    inspector.scenario_action('A', 'set', node_id='D1', value=4, expected_revision=0)
    mapping.write_text(mapping.read_text() + '\n')
    result = inspector.snapshot('A')
    assert result['selected']
    assert result['comparison']['status'] == 'observation_only'
    assert result['forward_evaluation']['native_mapping_invalidated']
    assert result['comparison']['native_values'] == []


def test_explicit_report_is_reproducible_and_does_not_persist(tmp_path):
    inspector, model, evidence, initial = setup_real_standard(tmp_path)
    mapping = create_mapping(tmp_path, initial)
    before = tuple(p.read_bytes() for p in (model, evidence, mapping))
    inspector.bind_native_inputs('A', str(mapping))
    inspector.scenario_action('A', 'set', node_id='D1', value=3, expected_revision=0)
    with pytest.raises(ComparisonError, match='revision'):
        inspector.export_report('A', expected_revision=0)
    report = inspector.export_report('A', expected_revision=1)
    assert report['schema_version'] == 1 and report['sources_modified'] is False
    assert report['model']['manifest_sha256'] == initial['manifest_sha256']
    assert report['comparison']['native_mapping_sha256'] == report['forward_evaluation']['mapping_sha256']
    assert json.loads(json.dumps(report))['scenario']['revision'] == 1
    assert tuple(p.read_bytes() for p in (model, evidence, mapping)) == before


def test_qi4_api_and_ui_contracts(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ui = (root / 'pah/web/static/pah.js').read_text()
    app_source = (root / 'pah/app.py').read_text()
    assert 'quality-impact/comparison' in ui and 'quality-impact/export' in ui
    assert 'quality-impact/comparison' in app_source and 'quality-impact/export' in app_source
    assert 'qi-path-edge' in ui and 'recorded structural reachability' in ui
    pytest.importorskip('flask')
    from pah import create_app
    archive = tmp_path / 'archive.zip'
    archive.write_text('valid')
    findings = tmp_path / 'findings.json'
    findings.write_text(json.dumps({'diagnostics': {'CWE-79': [{'line': 2}]}}))
    from test_qi1_quality_impact import fake_reader, fake_summary
    app = create_app(state_dir=tmp_path / 'state')
    app.config['TESTING'] = True
    app.extensions['pah_quality_impact']._reader = fake_reader
    app.extensions['pah_quality_impact']._summarizer = fake_summary
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    endpoint = '/api/orchestration/code-analysis/quality-impact'
    with app.test_client() as client:
        assert client.post('/api/workspace/open', json={'path': str(workspace)}).status_code == 200
        assert client.post(endpoint + '/select', json={'path': str(archive),
            'findings_path': str(findings)}).status_code == 200
        saved = client.post(endpoint + '/comparison', json={
            'action': 'capture', 'label': 'Reference state', 'expected_revision': 0})
        assert saved.status_code == 200, saved.get_json()
        assert saved.get_json()['comparison_checkpoints'][0]['label'] == 'Reference state'
        exported = client.post(endpoint + '/export', json={'expected_revision': 0})
        assert exported.status_code == 200
        assert exported.get_json()['report']['sources_modified'] is False
        assert client.post(endpoint + '/export', json={'expected_revision': 2}).status_code == 409


def test_mi_changes_show_observation_and_recorded_context_only(tmp_path):
    from test_qi1_quality_impact import _recorded_network
    model = tmp_path / 'mi.zip'
    model.write_text('ok')
    evidence = tmp_path / 'mi.json'
    evidence.write_text(json.dumps({'findings': [
        {'cwe_id': 79, 'file_path': 'src/a.c', 'line': 5},
    ]}))
    topology = {'nodes': [{'id': 'F79', 'kind': 'feature', 'feature_id': 'CWE-79'},
                          {'id': 'L1', 'kind': 'latent'}],
                'edges': [{'source': 'F79', 'target': 'L1',
                           'relationship': 'signed_information', 'signed_score': -.12}]}
    backing = {'nodes': [{'id': 'F79', 'kind': 'feature'}, {'id': 'L1', 'kind': 'latent'}],
               'relationships': [{'source': 'F79', 'target': 'L1',
                                  'relationship': 'learned_rbm_connection', 'weight': .6}]}

    def reader(_):
        return {'family': 'mi_informed_pique', 'version_id': 'mi-version',
                'manifest': {'choice': 'original'},
                'documents': {'signed_information_topology.json': topology,
                              'probabilistic_model.json': backing},
                'archive_sha256': 'c' * 64, 'manifest_sha256': 'd' * 64}

    inspector = QualityImpactInspector(reader=reader, summarizer=lambda _: {'comparison': {'rows': []}})
    snap = inspector.select('MI', str(model), str(evidence))
    assert snap['scenario']['rows'][0]['node_id'] == 'F79'
    result = inspector.scenario_action('MI', 'set', node_id='F79', value=3, expected_revision=0)
    comp = result['comparison']
    assert comp['status'] == 'observation_only'
    assert comp['observations'][0]['delta'] == 2
    assert comp['network_highlights']['relationship'] == 'recorded_information_topology_context_only'
    assert comp['network_highlights']['recorded_edge_indices'] == [0]
    assert comp['native_values'] == []
    assert result['probabilistic_backing']['edges'][0]['weight'] == .6
    assert 'signed_score' not in result['probabilistic_backing']['edges'][0]
