"""MI-U3: raw signed PMI, unsigned mutual information and fail-closed provenance."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from pique_py.mi_information_update import (
    MIInformationUpdateError, POLICY_SCHEMA, RESULT_SCHEMA,
    _cell_information, _information_pair, _side_information,
    _validate_side, recalculate_mi_u3_information, main)
from pique_py.mi_distribution_update import estimate_mi_u2_distribution, DATASET_SCHEMA
from pique_py.research_models import canonical_sha256
from test_mi_u2_distribution_protocol import setup as u2_setup, run as u2_run


def policy(**kwargs):
    return {'schema': POLICY_SCHEMA, 'schema_version': 1, **kwargs}


def evaluate(bundle, *, override=None):
    dist = u2_run(bundle) if override is None else override
    return recalculate_mi_u3_information(conclusion_path=bundle[0], contract=bundle[1],
                                         distribution_estimate=dist, policy=policy())


def paired(cells, ess=50, threshold=5):
    a = {'0': cells['00'] + cells['01'], '1': cells['10'] + cells['11']}
    b = {'0': cells['00'] + cells['10'], '1': cells['01'] + cells['11']}
    return _information_pair(cells, a, b, ess, threshold)


def test_known_joint_signed_pmi_nonnegative_mutual_information():
    cells = {'00': .4, '01': .1, '10': .1, '11': .4}
    p = paired(cells)
    assert p['cells']['11']['raw_signed_pmi_nats'] == pytest.approx(math.log(1.6))
    assert p['cells']['10']['raw_signed_pmi_nats'] == pytest.approx(math.log(.4))
    assert p['cells']['11']['normalized_pointwise_pmi'] == pytest.approx(math.log(1.6)/(-math.log(.4)))
    expected = 2*.4*math.log(1.6) + 2*.1*math.log(.4)
    assert p['mutual_information_nats'] == pytest.approx(expected)
    assert p['mutual_information_is_signed'] is False
    assert p['low_support_cell_count'] == 0


def test_negative_presence_pmi_is_not_negative_mutual_information():
    cells = {'00': .1, '01': .4, '10': .4, '11': .1}
    p = paired(cells)
    assert p['cells']['11']['raw_signed_pmi_nats'] == pytest.approx(math.log(.4))
    assert p['cells']['10']['raw_signed_pmi_nats'] > 0
    assert p['mutual_information_nats'] > 0


def test_independent_and_deterministic_events():
    p = paired({'00': .25, '01': .25, '10': .25, '11': .25})
    assert p['mutual_information_nats'] == pytest.approx(0.)
    assert all(x['raw_signed_pmi_nats'] == pytest.approx(0.) for x in p['cells'].values())
    status, raw, norm = _cell_information(1., 1., 1.)
    assert (status, raw, norm) == ('deterministic_joint', 0., 0.)


def test_exact_zero_joint_returns_undefined_not_infinity():
    p = paired({'00': 0., '01': .5, '10': .5, '11': 0.})
    assert p['cells']['00']['raw_signed_pmi_nats'] is None
    assert p['cells']['11']['normalized_pointwise_pmi'] is None
    assert p['cells']['11']['status'] == 'undefined_zero_joint'
    assert p['cells']['11']['low_effective_support'] is True
    assert p['mutual_information_nats'] == pytest.approx(math.log(2))


def test_uniform_mixture_is_separate_and_explicit():
    cells = {'00': .5, '01': 0., '10': 0., '11': .5}
    side = {'pairs': {('a', 'b'): cells}, 'support': {'project_count': 20},
            'marginals': {'a': {'0': .5, '1': .5}, 'b': {'0': .5, '1': .5}},
            'effective_sample_size': 20.}
    result = _side_information(side, {'uniform_mixture_strength': .2,
                 'min_effective_cell_mass': 5., 'zero_probability_policy': 'uniform_joint_mixture'})
    raw = result['raw_pairwise_information'][0]
    smooth = result['regularized_pairwise_information'][0]
    assert raw['cells']['01']['raw_signed_pmi_nats'] is None
    assert smooth['cells']['01']['joint_probability'] == pytest.approx(.05)
    assert smooth['cells']['01']['raw_signed_pmi_nats'] == pytest.approx(math.log(.05/.25))
    assert raw['cells']['11']['joint_probability'] == .5
    assert smooth['mutual_information_nats'] < raw['mutual_information_nats']


def test_real_concluded_model_to_u2_to_u3_roundtrip(tmp_path):
    bundle = u2_setup(tmp_path)
    old = Path(bundle[0]).read_bytes()
    dist = u2_run(bundle)
    first = evaluate(bundle, override=dist)
    assert first == evaluate(bundle, override=dist)
    assert first['schema'] == RESULT_SCHEMA
    assert first['result_sha256'] == canonical_sha256({k: v for k, v in first.items() if k != 'result_sha256'})
    assert first['mi_u2_result_sha256'] == dist['result_sha256']
    assert first['semantics']['learned_latent_distributions_reestimated'] is False
    assert first['semantics']['pf_tqi'] is None
    assert first['baseline']['raw_pairwise_information'] == []  # single mapped feature
    assert first['delta_raw'] == []
    assert Path(bundle[0]).read_bytes() == old


def test_reweighting_and_declared_cohort_methods_are_accepted(tmp_path):
    bundle = u2_setup(tmp_path, 'reference_reweighting')
    bundle[3]['target_event_prevalences'] = {'CWE-1': .2}
    result = evaluate(bundle)
    assert result['hypothetical']['marginals']['CWE-1']['1'] == pytest.approx(.2)
    assert result['distribution_mode'] == 'reference_reweighting'


def test_reject_changed_estimate_and_mismatched_contract(tmp_path):
    bundle = u2_setup(tmp_path)
    dist = u2_run(bundle)
    corrupt = deepcopy(dist)
    corrupt['baseline']['probabilities']['marginals']['CWE-1']['event_true'] = .5
    with pytest.raises(MIInformationUpdateError, match='fingerprint mismatch'):
        evaluate(bundle, override=corrupt)
    corrupt['result_sha256'] = canonical_sha256({k: v for k, v in corrupt.items() if k != 'result_sha256'})
    with pytest.raises(MIInformationUpdateError, match='sum to one|inconsistent'):
        evaluate(bundle, override=corrupt)
    bad = deepcopy(dist)
    bad['contract_sha256'] = '0'*64
    bad['result_sha256'] = canonical_sha256({k: v for k, v in bad.items() if k != 'result_sha256'})
    with pytest.raises(MIInformationUpdateError, match='provenance mismatch'):
        evaluate(bundle, override=bad)


def test_reject_invalid_pair_shape_probabilities_duplicates_and_inconsistency():
    exemplar = {'support': {'project_count': 20, 'weight_total': 20., 'effective_sample_size': 20.},
                'probabilities': {'estimator': 'weighted_empirical_complete_case', 'smoothing': 'none',
                                  'marginals': {'a': {'event_true': .5, 'event_false': .5},
                                                'b': {'event_true': .5, 'event_false': .5}},
                                  'joints': [{'left': 'a', 'right': 'b',
                                              'cells': {'00': .25, '01': .25, '10': .25, '11': .25}}]}}
    assert len(_validate_side(exemplar, ['a', 'b'], 'side')['pairs']) == 1
    for mutation, error in [
        (lambda d: d['probabilities']['joints'].append(deepcopy(d['probabilities']['joints'][0])), 'every feature pair'),
        (lambda d: d['probabilities']['joints'][0]['cells'].update({'11': .9}), 'inconsistent'),
        (lambda d: d['probabilities']['joints'][0]['cells'].update({'11': -0.2}), 'outside'),
        (lambda d: d['probabilities']['marginals']['a'].update({'event_false': .6}), 'sum to one'),
        (lambda d: d['probabilities'].update({'smoothing': 'implicit'}), 'unsmoothed'),
        (lambda d: d['probabilities']['joints'][0].update({'left': 'b', 'right': 'a'}), 'reversed'),
    ]:
        bad = deepcopy(exemplar); mutation(bad)
        with pytest.raises(MIInformationUpdateError, match=error):
            _validate_side(bad, ['a', 'b'], 'side')


@pytest.mark.parametrize('extra,reason', [
    ({'zero_probability_policy': 'forbidden'}, 'Unknown'),
    ({'uniform_mixture_strength': .2}, 'requires explicit'),
    ({'zero_probability_policy': 'uniform_joint_mixture', 'uniform_mixture_strength': 0}, 'strictly'),
    ({'zero_probability_policy': 'uniform_joint_mixture', 'uniform_mixture_strength': 1}, 'strictly'),
    ({'min_effective_cell_mass': 0}, 'min_effective_cell_mass must be'),
    ({'unknown_switch': True}, 'Unsupported'),
])
def test_fail_closed_configuration(tmp_path, extra, reason):
    bundle = u2_setup(tmp_path)
    with pytest.raises(MIInformationUpdateError, match=reason):
        recalculate_mi_u3_information(conclusion_path=bundle[0], contract=bundle[1],
                          distribution_estimate=u2_run(bundle), policy=policy(**extra))


def test_cli_create_only(tmp_path, capsys):
    bundle = u2_setup(tmp_path)
    paths = []
    for name, payload in [('u1.json', bundle[1]), ('u2.json', u2_run(bundle)), ('u3_policy.json', policy())]:
        path = tmp_path/name; path.write_text(json.dumps(payload), encoding='utf-8'); paths.append(str(path))
    destination = tmp_path/'information.json'
    assert main([str(bundle[0]), *paths, '--output', str(destination)]) == 0
    assert json.loads(destination.read_text())['schema'] == RESULT_SCHEMA
    with pytest.raises(FileExistsError):
        main([str(bundle[0]), *paths, '--output', str(destination)])


def test_two_feature_end_to_end_actual_concluded_mi_and_distribution(tmp_path):
    # Extend the real MF-4 fixture's learned backing with a second observable.
    # This proves that both U2 and U3 pairwise calculations use actual finalized
    # model identity, not an invented pair disconnected from the package.
    from test_mf4_mi_model_conclusion import _setup as source_project, _provenance
    from pique_py.research_models import build_probabilistic_model_artifact
    from pique_py.visualizer import conclude_project_mi_model
    from pique_py.finalized_model_registry import read_conclusion
    from pique_py.mi_update_contract import build_mi_u1_contract
    from pique_py.mi_distribution_update import estimate_mi_u2_distribution, PROTOCOL_SCHEMA
    from test_mi_u1_evidence_event_contract import fixture as example_contract

    target, files = source_project(tmp_path/'new_model')
    backing = build_probabilistic_model_artifact(
        nodes=[{'id':'CWE-1','kind':'cwe','probability_present':.5},
               {'id':'CWE-2','kind':'cwe','probability_present':.5},
               {'id':'latent:1:0','kind':'latent','layer':1,'marginal_probability':.4}],
        relationships=[{'source':'CWE-1','target':'latent:1:0','relationship':'learned_rbm_connection',
                        'weight':-.6,'joint_probability':.16},
                       {'source':'CWE-2','target':'latent:1:0','relationship':'learned_rbm_connection',
                        'weight':.2,'joint_probability':.2}],
        provenance=_provenance(), population={'name':'fixture'},
        metadata={'learned_latent_model':True})
    files['probability'].write_text(json.dumps(backing), encoding='utf-8')
    archive = conclude_project_mi_model(target=target, choice='configured')['archive_path']
    verified = read_conclusion(archive)
    _, _, spec, _ = example_contract(tmp_path/'contract_seed')
    spec['model'].update(version_id=verified['version_id'],
                         archive_sha256=verified['archive_sha256'],
                         manifest_sha256=verified['manifest_sha256'])
    spec['distribution']['mode'] = 'reference_reweighting'
    spec['distribution']['conditioning_variables'] = []
    second = deepcopy(spec['features'][0])
    second.update(diagnostic_node_id='feature:CWE-2', measure_id='CWE-2', backing_node_id='CWE-2')
    second['baseline'] = {'observed':True, 'value':1}
    second['hypothetical'] = {'observed':True, 'value':1}
    spec['features'].append(second)
    # 8/2/2/8 binary cells, in order 11, 10, 01, 00.
    states = [(1,1)]*8 + [(1,0)]*2 + [(0,1)]*2 + [(0,0)]*8
    dataset = {'schema':DATASET_SCHEMA,'schema_version':1,
               'population_id':'benchmark-ref-v1','sampling_unit':'project',
               'data_origin':'benchmark_reference',
               'rows':[{'project_id':str(i), 'features':{
                   'CWE-1':{'observed':True, 'value':int(a)},
                   'CWE-2':{'observed':True, 'value':int(b)}}}
                   for i,(a,b) in enumerate(states)]}
    spec['reference_population']['sample_count'] = 20
    spec['reference_population']['snapshot_sha256'] = canonical_sha256(dataset)
    contract = build_mi_u1_contract(conclusion_path=archive, specification=spec)
    estimate = estimate_mi_u2_distribution(conclusion_path=archive, contract=contract,
            reference_dataset=dataset,
            protocol={'schema':PROTOCOL_SCHEMA,'schema_version':1,
                      'target_event_prevalences':{'CWE-1':.3}})
    before = Path(archive).read_bytes()
    result = recalculate_mi_u3_information(conclusion_path=archive, contract=contract,
                                             distribution_estimate=estimate, policy=policy())
    base = result['baseline']['raw_pairwise_information'][0]
    updated = result['hypothetical']['raw_pairwise_information'][0]
    assert (base['left'],base['right']) == ('CWE-1','CWE-2')
    assert base['cells']['11']['joint_probability'] == pytest.approx(.4)
    assert base['cells']['11']['raw_signed_pmi_nats'] == pytest.approx(math.log(1.6))
    assert updated['cells']['11']['joint_probability'] == pytest.approx(.24)
    assert updated['cells']['11']['raw_signed_pmi_nats'] == pytest.approx(math.log(.24/(.3*.38)))
    assert result['delta_raw'][0]['cells']['11']['delta_signed_pmi_nats'] == pytest.approx(
        updated['cells']['11']['raw_signed_pmi_nats'] - base['cells']['11']['raw_signed_pmi_nats'])
    assert Path(archive).read_bytes() == before


def test_tiny_joint_log_domain_remains_finite():
    p = 1e-300
    status, pmi, npmi = _cell_information(p, p, p)
    assert status == 'defined'
    assert pmi == pytest.approx(-math.log(p))
    assert npmi == pytest.approx(1.0)
