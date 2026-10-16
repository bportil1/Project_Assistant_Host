"""MI-U1 must validate semantics without pretending to estimate a distribution."""
import json
from copy import deepcopy

import pytest

from pique_py.finalized_model_registry import read_conclusion
from pique_py.mi_update_contract import MIUpdateContractError, build_mi_u1_contract, main
from pique_py.research_models import canonical_sha256
from pique_py.visualizer import conclude_project_mi_model, conclude_project_standard_model
from test_mf4_mi_model_conclusion import _setup as mi_project
from test_mf3_standard_model_conclusion import project as standard_project


def fixture(tmp_path):
    target, sources = mi_project(tmp_path)
    conclusion = conclude_project_mi_model(target=target, choice='configured')
    path = conclusion['archive_path']
    verified = read_conclusion(path)
    data = {
        'schema': 'pypique.mi_update.evidence_spec', 'schema_version': 1,
        'model': {'version_id': verified['version_id'], 'manifest_sha256': verified['manifest_sha256'],
                  'archive_sha256': verified['archive_sha256']},
        'model_compatibility': {'rbm_family': 'bernoulli', 'latent_depth': 1},
        'reference_population': {'id': 'benchmark-ref-v1', 'snapshot_sha256': 'd' * 64,
                                 'sample_count': 527, 'sampling_unit': 'project',
                                 'sampling_frame': 'benchmark training cohort',
                                 'cohort_rule': 'selected benchmark projects, no targets',
                                 'data_origin': 'benchmark_reference'},
        'distribution': {'mode': 'reference_conditioning', 'conditioning_variables': ['CWE-1'],
                         'estimand': 'reference cohort conditional project-level event distribution',
                         'assumptions': 'overlap, sufficient support and stable event definitions must be verified',
                         'target_population': 'benchmark-compatible projects'},
        'features': [{'diagnostic_node_id': 'feature:CWE-1', 'measure_id': 'CWE-1', 'backing_node_id': 'CWE-1',
                      'source_unit': 'matched_sat_finding_count',
                      'transform': {'kind': 'presence_threshold', 'threshold': 1},
                      'event': {'kind': 'binary_presence', 'positive_state': 1, 'negative_state': 0},
                      'missingness': {'policy': 'mask_and_exclude', 'mask_field': 'observed'},
                      'baseline': {'observed': True, 'value': 5},
                      'hypothetical': {'observed': True, 'value': 0}}]}
    return path, sources, data, verified


def test_valid_concluded_model_contract_is_nonexecuting_and_deterministic(tmp_path):
    path, sources, data, verified = fixture(tmp_path)
    before = {k: p.read_bytes() for k, p in sources.items()}
    first = build_mi_u1_contract(conclusion_path=path, specification=data)
    second = build_mi_u1_contract(conclusion_path=path, specification=data)
    assert first == second
    assert first['schema'] == 'pypique.mi_update.evidence_contract'
    assert first['contract_sha256'] == canonical_sha256({k: v for k, v in first.items() if k != 'contract_sha256'})
    assert first['execution']['status'] == 'contract_only_not_executed'
    assert first['execution']['updated_signed_pmi'] is None
    assert first['identifiability']['status'] == 'not_established'
    assert first['model']['signed_topology_sha256'] == verified['manifest']['files']['signed_information_topology.json']
    assert first['model_compatibility']['family_evidence'] == 'operator_declared_unverified'
    assert before == {k: p.read_bytes() for k, p in sources.items()}


def test_cli_stdout_and_explicit_output_only(tmp_path, capsys):
    path, _, data, _ = fixture(tmp_path)
    spec_path = tmp_path / 'spec.json'
    spec_path.write_text(json.dumps(data))
    assert main([str(path), str(spec_path)]) == 0
    assert json.loads(capsys.readouterr().out)['identifiability']['status'] == 'not_established'
    output_path = tmp_path / 'validated.json'
    assert main([str(path), str(spec_path), '--output', str(output_path)]) == 0
    assert output_path.is_file()
    with pytest.raises(FileExistsError):
        main([str(path), str(spec_path), '--output', str(output_path)])


@pytest.mark.parametrize('mutator,expression', [
    (lambda d: d['model'].update(manifest_sha256='f' * 64), 'manifest_sha256'),
    (lambda d: d['reference_population'].update(data_origin='target_project'), 'Target-project'),
    (lambda d: d['reference_population'].update(sampling_unit='finding'), 'project-level'),
    (lambda d: d['model_compatibility'].update(latent_depth=2), 'latent depth'),
    (lambda d: d['model_compatibility'].update(rbm_family='unsupported'), 'RBM family'),
    (lambda d: d['distribution'].update(mode='posterior_only_fixed_pmi'), 'Option B'),
    (lambda d: d['distribution'].update(conditioning_variables=[]), 'conditioning'),
    (lambda d: d['features'][0].update(backing_node_id='latent:1:0'), 'backing node'),
    (lambda d: d['features'][0].update(measure_id='CWE-2'), 'measure_id'),
    (lambda d: d['features'][0]['transform'].update(threshold=0), 'threshold'),
    (lambda d: d['features'][0]['event'].update(positive_state=0), 'binary event'),
    (lambda d: d['features'][0]['missingness'].update(policy='zero_impute'), 'masking'),
    (lambda d: d['features'][0]['baseline'].update(value=-2), 'count'),
    (lambda d: d['features'][0]['hypothetical'].update(value=float('nan')), 'finite'),
    (lambda d: d['features'][0]['baseline'].update(observed=False), 'masked observation'),
    (lambda d: d['features'].append(deepcopy(d['features'][0])), 'Duplicate'),
    (lambda d: d['features'][0]['hypothetical'].update(value=5), 'No diagnostic change'),
])
def test_fail_closed_for_invalid_mapping_or_scenario(tmp_path, mutator, expression):
    path, _, data, _ = fixture(tmp_path)
    mutator(data)
    with pytest.raises(MIUpdateContractError, match=expression):
        build_mi_u1_contract(conclusion_path=path, specification=data)


def test_masks_are_not_replaced_by_zero(tmp_path):
    path, _, data, _ = fixture(tmp_path)
    data['features'][0]['hypothetical'] = {'observed': False, 'value': None}
    result = build_mi_u1_contract(conclusion_path=path, specification=data)
    assert result['features'][0]['hypothetical'] == {'observed': False, 'value': None}
    assert result['execution']['updated_marginals'] is None


def test_gaussian_event_interval_declaration_is_not_fake_probability(tmp_path):
    path, _, data, _ = fixture(tmp_path)
    data['model_compatibility']['rbm_family'] = 'gaussian'
    data['features'][0]['source_unit'] = 'native_value'
    data['features'][0]['transform'] = {'kind': 'identity'}
    data['features'][0]['event'] = {'kind': 'numeric_interval', 'lower': 0.0, 'upper': 1.0, 'unit': 'normalized_feature'}
    data['features'][0]['baseline']['value'] = 0.7
    data['features'][0]['hypothetical']['value'] = 0.2
    result = build_mi_u1_contract(conclusion_path=path, specification=data)
    assert result['model_compatibility']['rbm_family'] == 'gaussian'
    assert result['features'][0]['event']['kind'] == 'numeric_interval'
    assert result['identifiability']['status'] == 'not_established'


def test_qi5_handoff_validation_accepts_bound_only_and_never_transforms(tmp_path):
    path, _, data, verified = fixture(tmp_path)
    data['distribution']['mode'] = 'reference_reweighting'
    data['distribution']['conditioning_variables'] = []
    model_hashes = verified['manifest']['files']
    row = data['features'][0]
    handoff = {
        'schema': 'pah.mi_inference_request', 'schema_version': 1, 'status': 'prepared_not_executed',
        'network': {'concluded_family': 'mi_informed_pique', 'concluded_version_id': verified['version_id'],
                    'archive_sha256': verified['archive_sha256'], 'manifest_sha256': verified['manifest_sha256'],
                    'signed_information_topology_sha256': model_hashes['signed_information_topology.json'],
                    'learned_probabilistic_backing_sha256': model_hashes['probabilistic_model.json']},
        'inputs': [{'source_node_id': row['diagnostic_node_id'], 'backing_node_id': row['backing_node_id'],
                    'unit': 'matched_sat_finding_count', 'baseline_observed_count': 5,
                    'hypothetical_observed_count': 0, 'model_input_value': None,
                    'model_input_status': 'requires_provider_transformation'}],
        'estimation': {'performed': False, 'results': None},
    }
    handoff['request_sha256'] = canonical_sha256(handoff)
    result = build_mi_u1_contract(conclusion_path=path, specification=data, pah_request=handoff)
    assert result['lineage']['source'] == 'qi5_handoff'
    assert result['lineage']['pah_request_sha256'] == handoff['request_sha256']
    tampered = deepcopy(handoff)
    tampered['inputs'][0]['hypothetical_observed_count'] = 22
    with pytest.raises(MIUpdateContractError, match='fingerprint mismatch'):
        build_mi_u1_contract(conclusion_path=path, specification=data, pah_request=tampered)
    tampered['request_sha256'] = canonical_sha256({k: v for k, v in tampered.items() if k != 'request_sha256'})
    with pytest.raises(MIUpdateContractError, match='conflicts'):
        build_mi_u1_contract(conclusion_path=path, specification=data, pah_request=tampered)


def test_reject_standard_conclusion(tmp_path):
    standard_target, source, _ = standard_project(tmp_path)
    standard = conclude_project_standard_model(target=standard_target, model_path=source, choice='configured')
    _, _, data, _ = fixture(tmp_path/'other')
    with pytest.raises(MIUpdateContractError, match='concluded MI'):
        build_mi_u1_contract(conclusion_path=standard['archive_path'], specification=data)
