"""QI-5: scientific handoff contract only, no invented MI distributions."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from pah.labs.quality_impact import QualityImpactInspector
from pah.labs.quality_impact_mi import MIContractError, build_mi_request, read_mi_adapter


SIGNED = {
    'nodes': [{'id': 'feature:CWE-79', 'kind': 'feature', 'feature_id': 'CWE-79'},
              {'id': 'latent:1:0', 'kind': 'latent'}],
    'edges': [{'source': 'feature:CWE-79', 'target': 'latent:1:0',
               'relationship': 'signed_information', 'signed_score': -.3}],
}
BACKING = {
    'nodes': [{'id': 'CWE-79', 'kind': 'cwe'}, {'id': 'latent:1:0', 'kind': 'latent'}],
    'relationships': [{'source': 'CWE-79', 'target': 'latent:1:0',
                       'relationship': 'learned_rbm_connection', 'weight': -.6}],
}


def fixture(tmp_path):
    source = tmp_path / 'mi.zip'
    source.write_bytes(b'valid')
    evidence = tmp_path / 'sat.json'
    evidence.write_text(json.dumps({'findings': [
        {'cwe_id': 79, 'file_path': 'a.c', 'line': 5},
        {'cwe_id': 79, 'file_path': 'b.c', 'line': 17},
    ]}))

    def reader(path):
        if Path(path).read_bytes() != b'valid':
            raise ValueError('invalid source')
        return {'family': 'mi_informed_pique', 'version_id': 'mi-version',
                'documents': {'signed_information_topology.json': SIGNED,
                              'probabilistic_model.json': BACKING},
                'manifest': {'choice': 'configured', 'files': {
                    'signed_information_topology.json': 'd' * 64,
                    'probabilistic_model.json': 'e' * 64}},
                'archive_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64}

    insp = QualityImpactInspector(reader=reader, summarizer=lambda _: {'comparison': {'unit': 'normalized_information_share', 'rows': []}})
    initial = insp.select('A', str(source), str(evidence))
    assert initial['mi_handoff']['status'] == 'needs_adapter'
    return insp, source, evidence, initial


def adapter_document(inspection):
    return {'schema': 'pah.mi_inference_adapter', 'schema_version': 1,
            'model_manifest_sha256': inspection['manifest_sha256'],
            'sat_evidence_sha256': inspection['evidence']['source']['sha256'],
            'signed_network_sha256': inspection['mi_signed_network_sha256'],
            'backing_model_sha256': inspection['mi_backing_model_sha256'],
            'provider': {'id': 'hsqa_dbn', 'version': 'unconnected-prototype',
                         'capability': 'mi.distribution_reestimation@1',
                         'owner': 'HSQA statistical provider'},
            'protocol': {'mode': 'distribution_reestimation',
                         'reference_population': 'NIST SARD benchmark cohort',
                         'conditioning_context': 'No conditioning performed in PAH',
                         'assumptions': 'Provider must document whether count perturbation is supported'},
            'feature_mappings': [{'source_node_id': 'feature:CWE-79', 'backing_node_id': 'CWE-79',
                                  'transformation': {'kind': 'provider_defined',
                                                     'source_unit': 'matched_sat_finding_count',
                                                     'target_unit': 'binary_presence_event',
                                                     'target_event': 'CWE-79 observed',
                                                     'provenance': 'User-defined experimental conversion'}}]}


def write_mapping(tmp_path, inspection, *, changes=None, name='adapter.json'):
    data = adapter_document(inspection)
    if changes:
        changes(data)
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_explicit_mi_mapping_prepares_deterministic_unexecuted_envelope(tmp_path):
    insp, model, evidence, original = fixture(tmp_path)
    before = model.read_bytes(), evidence.read_bytes()
    path = write_mapping(tmp_path, original)
    attached = insp.bind_mi_adapter('A', str(path))
    assert attached['mi_handoff']['status'] == 'needs_scenario'
    updated = insp.scenario_action('A', 'set', node_id='feature:CWE-79', value=5, expected_revision=0)
    assert updated['mi_handoff']['status'] == 'ready_to_prepare'
    envelope = insp.prepare_mi_request('A', expected_revision=1)
    assert envelope == insp.prepare_mi_request('A', expected_revision=1)
    assert envelope['status'] == 'prepared_not_executed'
    assert envelope['network']['signed_information_topology_sha256'] == 'd' * 64
    assert envelope['network']['learned_probabilistic_backing_sha256'] == 'e' * 64
    assert envelope['provider']['connection_status'] == 'declared_not_connected'
    assert envelope['estimation']['performed'] is False
    assert envelope['estimation']['updated_distributions'] is None
    assert envelope['estimation']['pf_tqi'] is None
    assert envelope['inputs'][0]['baseline_observed_count'] == 2
    assert envelope['inputs'][0]['hypothetical_observed_count'] == 5
    assert envelope['inputs'][0]['observation_delta'] == 3
    assert envelope['inputs'][0]['model_input_value'] is None
    assert envelope['inputs'][0]['transformation']['execution'] == 'not_performed_by_pah'
    assert len(envelope['request_sha256']) == 64
    assert envelope['request_sha256'] == sha256(json.dumps(
        {k: v for k, v in envelope.items() if k != 'request_sha256'},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert (model.read_bytes(), evidence.read_bytes()) == before
    assert insp.snapshot('A')['comparison']['native_values'] == []
    assert insp.snapshot('B')['selected'] is False


def test_stale_revision_reset_and_source_changes_are_fail_closed(tmp_path):
    insp, model, evidence, snap = fixture(tmp_path)
    path = write_mapping(tmp_path, snap)
    insp.bind_mi_adapter('A', str(path))
    with pytest.raises(MIContractError, match='hypothetical'):
        insp.prepare_mi_request('A', expected_revision=0)
    insp.scenario_action('A', 'set', node_id='feature:CWE-79', value=3, expected_revision=0)
    with pytest.raises(MIContractError, match='revision'):
        insp.prepare_mi_request('A', expected_revision=0)
    with pytest.raises(MIContractError, match='revision'):
        insp.prepare_mi_request('A', expected_revision=True)
    assert insp.prepare_mi_request('A', expected_revision=1)['scenario_lineage']['revision'] == 1
    insp.scenario_action('A', 'undo', expected_revision=1)
    assert insp.snapshot('A')['mi_handoff']['status'] == 'needs_scenario'
    evidence.write_text(evidence.read_text() + ' ')
    assert insp.snapshot('A')['selected'] is False
    assert insp._mi_adapters.get('A') is None
    assert insp._scenarios.get('A') is None


def test_edited_adapter_invalidates_only_binding_and_preserves_scenario(tmp_path):
    insp, _, _, snap = fixture(tmp_path)
    path = write_mapping(tmp_path, snap)
    insp.bind_mi_adapter('A', str(path))
    insp.scenario_action('A', 'set', node_id='feature:CWE-79', value=8, expected_revision=0)
    path.write_text(path.read_text() + '\n')
    current = insp.snapshot('A')
    assert current['selected'] is True
    assert current['mi_handoff']['status'] == 'blocked'
    assert current['mi_handoff']['adapter_invalidated']
    assert current['scenario']['revision'] == 1
    assert insp.snapshot('A')['mi_handoff']['status'] == 'needs_adapter'
    insp.bind_mi_adapter('A', str(path))
    assert insp.snapshot('A')['mi_handoff']['status'] == 'ready_to_prepare'
    insp.clear_mi_adapter('A')
    assert insp.snapshot('A')['scenario']['revision'] == 1
    assert insp.snapshot('A')['mi_handoff']['status'] == 'needs_adapter'


@pytest.mark.parametrize('changes,pattern', [
    (lambda x: x.update(model_manifest_sha256='f'*64), 'model_manifest_sha256'),
    (lambda x: x['provider'].update(capability='mi.posterior_fixed_pmi@1'), 'capability'),
    (lambda x: x['protocol'].update(mode='fixed_pmi_posterior'), 'distribution_reestimation'),
    (lambda x: x['feature_mappings'][0].update(source_node_id='made-up'), 'SAT-linked'),
    (lambda x: x['feature_mappings'][0].update(backing_node_id='made-up'), 'backing'),
    (lambda x: x['feature_mappings'][0]['transformation'].update(kind='guessed_linear'), 'provider_defined'),
    (lambda x: x['feature_mappings'][0]['transformation'].update(target_event=''), 'target_event'),
    (lambda x: x['feature_mappings'].append(dict(x['feature_mappings'][0])), 'Duplicated'),
])
def test_invalid_mapping_rejected_without_replacing_good_one(tmp_path, changes, pattern):
    insp, _, _, snap = fixture(tmp_path)
    good = write_mapping(tmp_path, snap)
    insp.bind_mi_adapter('A', str(good))
    bad = write_mapping(tmp_path, snap, changes=changes, name='bad.json')
    with pytest.raises(MIContractError, match=pattern):
        insp.bind_mi_adapter('A', str(bad))
    assert insp.snapshot('A')['mi_handoff']['status'] == 'needs_scenario'


def test_duplicate_keys_and_symlink_refused(tmp_path):
    insp, _, _, snap = fixture(tmp_path)
    path = write_mapping(tmp_path, snap)
    with path.open('a') as f:
        f.write(' ')
    link = tmp_path / 'linked.json'
    link.symlink_to(path)
    with pytest.raises(MIContractError, match='non-symlink'):
        read_mi_adapter(link, snap)
    duplicate = tmp_path / 'duplicate.json'
    duplicate.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(MIContractError, match='Duplicate'):
        read_mi_adapter(duplicate, snap)


def test_ui_api_contract_and_stage_two_unchanged():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'pah/web/static/pah.js').read_text()
    app = (root / 'pah/app.py').read_text()
    assert 'MI inference provider handoff (QI-5)' in js
    assert 'Export unexecuted MI request' in js
    assert '/quality-impact/mi/prepare' in js and '/quality-impact/mi/adapter' in app
    from pah.labs.workflows import CODE_ANALYSIS_WORKFLOW
    assert CODE_ANALYSIS_WORKFLOW.steps[1].step_id == 'quality_modeling'


def test_flask_endpoints_bound_to_workspace_and_revision(tmp_path):
    pytest.importorskip('flask')
    from pah import create_app
    insp, model, evidence, _ = fixture(tmp_path)
    workspace = tmp_path / 'repo'; workspace.mkdir()
    app = create_app(state_dir=tmp_path / 'state')
    app.config['TESTING'] = True
    app.extensions['pah_quality_impact']._reader = insp._reader
    app.extensions['pah_quality_impact']._summarizer = insp._summarizer
    endpoint = '/api/orchestration/code-analysis/quality-impact'
    with app.test_client() as client:
        assert client.post('/api/workspace/open', json={'path': str(workspace)}).status_code == 200
        original = client.post(endpoint + '/select', json={'path': str(model), 'findings_path': str(evidence)}).get_json()
        path = write_mapping(tmp_path, original)
        assert client.post(endpoint + '/mi/adapter', json={'path': str(path)}).status_code == 200
        changed = client.post(endpoint + '/scenario', json={
            'action': 'set', 'node_id': 'feature:CWE-79', 'value': 5, 'expected_revision': 0})
        assert changed.status_code == 200, changed.get_json()
        bad = client.post(endpoint + '/mi/prepare', json={'expected_revision': 0})
        assert bad.status_code == 409
        prepared = client.post(endpoint + '/mi/prepare', json={'expected_revision': 1})
        assert prepared.status_code == 200, prepared.get_json()
        assert prepared.get_json()['request']['estimation']['performed'] is False
        cleared = client.post(endpoint + '/mi/clear', json={})
        assert cleared.get_json()['scenario']['revision'] == 1
        assert cleared.get_json()['mi_handoff']['status'] == 'needs_adapter'
