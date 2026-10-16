"""Distribution protocol: independently known event frequencies + fail-closed boundaries."""
import json
from pathlib import Path
from copy import deepcopy

import pytest

from pique_py.mi_update_contract import build_mi_u1_contract
from pique_py.mi_distribution_update import (MIDistributionUpdateError, estimate_mi_u2_distribution,
                                              main, DATASET_SCHEMA, PROTOCOL_SCHEMA)
from pique_py.research_models import canonical_sha256
from test_mi_u1_evidence_event_contract import fixture as original_fixture


def setup(tmp_path, mode='reference_conditioning'):
    path, files, spec, verified = original_fixture(tmp_path)
    # Twenty projects; 12 event present (6 co-present with CWE-2 when added), 8 absent.
    rows = []
    for i in range(20):
        rows.append({'project_id': f'benchmark-{i:02d}', 'features': {
            'CWE-1': {'observed': True, 'value': 3 if i < 12 else 0}}})
    dataset = {'schema': DATASET_SCHEMA, 'schema_version': 1, 'population_id': 'benchmark-ref-v1',
               'sampling_unit': 'project', 'data_origin': 'benchmark_reference', 'rows': rows}
    spec['reference_population']['sample_count'] = len(rows)
    spec['reference_population']['snapshot_sha256'] = canonical_sha256(dataset)
    spec['distribution']['mode'] = mode
    if mode != 'reference_conditioning':
        spec['distribution']['conditioning_variables'] = []
    contract = build_mi_u1_contract(conclusion_path=path, specification=spec)
    protocol = {'schema': PROTOCOL_SCHEMA, 'schema_version': 1,
                'min_complete_cases': 5, 'min_effective_sample_size': 5.0}
    return path, contract, dataset, protocol


def run(bundle):
    path, contract, dataset, protocol = bundle
    return estimate_mi_u2_distribution(conclusion_path=path, contract=contract,
                                       reference_dataset=dataset, protocol=protocol)


def test_conditioning_uses_real_reference_support_and_preserves_model(tmp_path):
    bundle = setup(tmp_path)
    path = bundle[0]
    before = Path(path).read_bytes()
    result = run(bundle)
    assert result['distribution_mode'] == 'reference_conditioning'
    assert result['baseline']['support']['project_count'] == 12
    assert result['hypothetical']['support']['project_count'] == 8
    assert result['baseline']['probabilities']['marginals']['CWE-1']['event_true'] == 1
    assert result['hypothetical']['probabilities']['marginals']['CWE-1']['event_true'] == 0
    assert result['limits']['updated_pmi'] is None
    assert result['limits']['trained_rbm_inference_performed'] is False
    assert result['result_sha256'] == canonical_sha256({k: v for k, v in result.items() if k != 'result_sha256'})
    assert result == run(bundle)
    assert Path(path).read_bytes() == before


def test_reweighting_calibrates_prevalence_not_direct_count(tmp_path):
    bundle = setup(tmp_path, 'reference_reweighting')
    bundle[3]['target_event_prevalences'] = {'CWE-1': 0.3}
    result = run(bundle)
    assert result['baseline']['probabilities']['marginals']['CWE-1']['event_true'] == pytest.approx(0.6)
    assert result['hypothetical']['probabilities']['marginals']['CWE-1']['event_true'] == pytest.approx(0.3)
    assert result['hypothetical']['support']['effective_sample_size'] >= 5
    assert result['protocol_details']['iterations'] >= 1
    assert 'NOT inferred' in result['protocol_details']['interpretation']


def test_reweighting_requires_declared_population_target(tmp_path):
    bundle = setup(tmp_path, 'reference_reweighting')
    with pytest.raises(MIDistributionUpdateError, match='prevalence targets'):
        run(bundle)


def test_missingness_excludes_not_zero_imputes(tmp_path):
    bundle = setup(tmp_path)
    bundle[2]['rows'][0]['features']['CWE-1'] = {'observed': False, 'value': None}
    # dataset must be re-fingerprinted, requiring a NEW U1 contract; tampering is rejected.
    with pytest.raises(MIDistributionUpdateError, match='snapshot SHA256'):
        run(bundle)
    bundle[2]['rows'][0]['features']['CWE-1'] = {'observed': True, 'value': 3}
    assert run(bundle)['reference']['excluded_missing'] == 0


def test_rejects_tampered_mi_u1_contract(tmp_path):
    bundle = setup(tmp_path)
    bundle[1]['distribution']['mode'] = 'reference_reweighting'
    with pytest.raises(MIDistributionUpdateError, match='fingerprint mismatch'):
        run(bundle)


def test_rejects_duplicate_project_and_negative_counts(tmp_path):
    bundle = setup(tmp_path)
    bundle[2]['rows'][0]['project_id'] = bundle[2]['rows'][1]['project_id']
    with pytest.raises(MIDistributionUpdateError, match='snapshot SHA256'):
        run(bundle)
    bundle = setup(tmp_path/'second')
    bundle[2]['rows'][0]['features']['CWE-1']['value'] = -1
    bundle[1]['reference_population']['snapshot_sha256'] = canonical_sha256(bundle[2])
    bundle[1]['contract_sha256'] = canonical_sha256({k: v for k, v in bundle[1].items() if k != 'contract_sha256'})
    with pytest.raises(MIDistributionUpdateError, match='nonnegative integer'):
        run(bundle)


def test_conditioning_insufficient_support(tmp_path):
    bundle = setup(tmp_path)
    bundle[3]['min_complete_cases'] = 9  # hypothetical absent state only has 8
    with pytest.raises(MIDistributionUpdateError, match='support'):
        run(bundle)


def test_reweighting_rejects_unsupported_targets(tmp_path):
    bundle = setup(tmp_path, 'reference_reweighting')
    bundle[3]['target_event_prevalences'] = {'CWE-1': 0.0}
    with pytest.raises(MIDistributionUpdateError, match='strictly between'):
        run(bundle)
    bundle[3]['target_event_prevalences'] = {'CWE-1': 0.9999}
    bundle[3]['min_effective_sample_size'] = 13
    with pytest.raises(MIDistributionUpdateError, match='effective sample support'):
        run(bundle)


def test_declared_scenario_requires_independent_cohort(tmp_path):
    bundle = setup(tmp_path, 'declared_distributional_scenario')
    with pytest.raises(MIDistributionUpdateError, match='separate project cohort'):
        run(bundle)
    independent = deepcopy(bundle[2]); independent['population_id'] = 'new-project-population'
    independent['data_origin'] = 'declared_scenario_cohort'
    for row in independent['rows']:
        row['features']['CWE-1']['value'] = 0
    result = estimate_mi_u2_distribution(conclusion_path=bundle[0], contract=bundle[1],
                                         reference_dataset=bundle[2], protocol=bundle[3], scenario_dataset=independent)
    assert result['baseline']['probabilities']['marginals']['CWE-1']['event_true'] == pytest.approx(.6)
    assert result['hypothetical']['probabilities']['marginals']['CWE-1']['event_true'] == 0
    assert result['scenario_source']['population_id'] == 'new-project-population'


def test_cli_output_is_create_only(tmp_path, capsys):
    bundle = setup(tmp_path)
    output = tmp_path/'result.json'
    paths = []
    for name, contents in zip(('contract.json','dataset.json','protocol.json'), bundle[1:]):
        p = tmp_path/name
        p.write_text(json.dumps(contents))
        paths.append(str(p))
    argv = [str(bundle[0]), *paths, '--output', str(output)]
    assert main(argv) == 0
    assert json.loads(output.read_text())['schema'] == 'pypique.mi_update.distribution_estimate'
    with pytest.raises(FileExistsError):
        main(argv)


def test_two_feature_joint_cells_consistent_with_marginals():
    from pique_py.mi_distribution_update import _statistics
    features = [{'backing_node_id': 'CWE-1'}, {'backing_node_id': 'CWE-2'}]
    rows = [{'states': {'CWE-1': bool(x), 'CWE-2': bool(y)}} for x,y in
            [(1,1), (1,1), (1,0), (0,1), (0,0), (0,0), (0,0), (0,0)]]
    stats = _statistics(rows, [1]*8, features)
    a = stats['marginals']['CWE-1']['event_true']
    b = stats['marginals']['CWE-2']['event_true']
    cells = stats['joints'][0]['cells']
    assert a == pytest.approx(3/8)
    assert b == pytest.approx(3/8)
    assert cells == pytest.approx({'11': 2/8, '10': 1/8, '01': 1/8, '00': 4/8})
    assert sum(cells.values()) == pytest.approx(1)
    assert cells['10'] + cells['11'] == pytest.approx(a)
    assert cells['01'] + cells['11'] == pytest.approx(b)


def test_sample_mask_exclusion_after_rebuilding_contract(tmp_path):
    bundle = setup(tmp_path)
    # Masking a reference row changes the dataset fingerprint, and is accepted
    # only after rebuilding the U1 contract against the new exact snapshot.
    dataset = bundle[2]
    dataset['rows'][0]['features']['CWE-1'] = {'observed': False, 'value': None}
    path, _, spec, _ = original_fixture(tmp_path/'rebound')
    spec['reference_population']['sample_count'] = len(dataset['rows'])
    spec['reference_population']['snapshot_sha256'] = canonical_sha256(dataset)
    updated_contract = build_mi_u1_contract(conclusion_path=path, specification=spec)
    result = estimate_mi_u2_distribution(conclusion_path=path, contract=updated_contract,
                                          reference_dataset=dataset, protocol=bundle[3])
    assert result['reference']['excluded_missing'] == 1
    assert result['baseline']['support']['project_count'] == 11
    assert result['hypothetical']['support']['project_count'] == 8


def test_native_interval_reference_events(tmp_path):
    path, _, spec, _ = original_fixture(tmp_path)
    rows = [{'project_id': f'p-{i}', 'features': {'CWE-1': {'observed': True, 'value': i/10}}}
            for i in range(20)]
    dataset = {'schema': DATASET_SCHEMA, 'schema_version': 1, 'population_id': 'benchmark-ref-v1',
               'data_origin': 'benchmark_reference', 'sampling_unit': 'project', 'rows': rows}
    spec['model_compatibility']['rbm_family'] = 'gaussian'
    spec['features'][0]['source_unit'] = 'native_value'
    spec['features'][0]['transform'] = {'kind': 'identity'}
    spec['features'][0]['event'] = {'kind': 'numeric_interval', 'lower': 0.0, 'upper': 1.0, 'unit': 'native'}
    spec['features'][0]['baseline']['value'] = 0.5
    spec['features'][0]['hypothetical']['value'] = 1.5
    spec['reference_population']['sample_count'] = 20
    spec['reference_population']['snapshot_sha256'] = canonical_sha256(dataset)
    contract = build_mi_u1_contract(conclusion_path=path, specification=spec)
    result = estimate_mi_u2_distribution(conclusion_path=path, contract=contract,
        reference_dataset=dataset, protocol={'schema': PROTOCOL_SCHEMA, 'schema_version': 1})
    assert result['baseline']['support']['project_count'] == 10
    assert result['hypothetical']['support']['project_count'] == 10
    assert result['baseline']['probabilities']['marginals']['CWE-1']['event_true'] == 1


def test_impossible_calibration_with_correlated_support():
    from pique_py.mi_distribution_update import _rake
    samples = [{'states': {'a':True, 'b':True}}, {'states': {'a':False,'b':False}}]
    with pytest.raises(MIDistributionUpdateError, match='did not converge'):
        _rake(samples, [1.0,1.0], {'a': 0.8, 'b': 0.2}, maximum=30, tolerance=1e-10)
