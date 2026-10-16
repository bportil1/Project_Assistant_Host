"""MI-U2: reproducible *empirical reference distribution* updates (Option B).

No causal, trained-RBM inference, PMI, latent/PF or TQI update is asserted.
An MI-U1 contract is required, and the reference projects must actually be
provided and fingerprinted. All joint/marginal estimates share one complete-
case cohort, preventing inconsistent pairwise-denominator artifacts.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .finalized_model_registry import read_conclusion
from .mi_update_contract import CONTRACT_SCHEMA, MIUpdateContractError
from .research_models import canonical_sha256

DATASET_SCHEMA = 'pypique.mi_update.reference_dataset'
PROTOCOL_SCHEMA = 'pypique.mi_update.estimation_protocol'
RESULT_SCHEMA = 'pypique.mi_update.distribution_estimate'
VERSION = 1
MAX_ROWS = 100000
MAX_FEATURES = 256
MAX_ITERATIONS = 5000


class MIDistributionUpdateError(MIUpdateContractError):
    """Reference sample, estimator assumptions, or statistical support invalid."""


def _obj(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MIDistributionUpdateError(f'{label} must be an object')
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MIDistributionUpdateError(f'{label} must be a finite number')
    return float(value)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MIDistributionUpdateError(f'{label} must be a positive integer')
    return value


def _verify_digest(data: Mapping[str, Any], label: str) -> str:
    digest = data.get('contract_sha256')
    if not isinstance(digest, str) or digest != canonical_sha256({k: v for k, v in data.items() if k != 'contract_sha256'}):
        raise MIDistributionUpdateError(f'{label} fingerprint mismatch')
    return digest


def _verify_contract(contract: Mapping[str, Any], conclusion_path: str | Path) -> tuple[list[dict], dict]:
    c = _obj(contract, 'MI-U1 contract')
    if (c.get('schema'), c.get('schema_version'), c.get('mode')) != (CONTRACT_SCHEMA, 1, 'distribution_reestimation_only'):
        raise MIDistributionUpdateError('Unsupported MI-U1 contract/version/mode')
    _verify_digest(c, 'MI-U1 contract')
    execution = _obj(c.get('execution'), 'MI-U1 execution')
    if (execution.get('status') != 'contract_only_not_executed'
            or execution.get('learned_model_mutated') is not False
            or any(execution.get(k) is not None for k in ('updated_distribution', 'updated_marginals',
                                                         'updated_joints', 'updated_signed_pmi', 'updated_pf_tqi'))):
        raise MIDistributionUpdateError('Input must be an unexecuted MI-U1 contract')
    concluded = read_conclusion(conclusion_path)  # file bytes + manifest validated by MF-5
    model = _obj(c.get('model'), 'contract.model')
    recorded = concluded['manifest']['files']
    expected = {'family': 'mi_informed_pique', 'version_id': concluded['version_id'],
                'archive_sha256': concluded['archive_sha256'], 'manifest_sha256': concluded['manifest_sha256'],
                'signed_topology_sha256': recorded.get('signed_information_topology.json'),
                'probabilistic_backing_sha256': recorded.get('probabilistic_model.json')}
    if concluded['family'] != 'mi_informed_pique' or any(model.get(k) != v for k, v in expected.items()):
        raise MIDistributionUpdateError('Concluded model identity/topology/backing fingerprint mismatch')
    features = c.get('features')
    if not isinstance(features, list) or not features or len(features) > MAX_FEATURES:
        raise MIDistributionUpdateError('MI-U2 requires 1–256 explicitly mapped features')
    ids = []
    for f in features:
        f = _obj(f, 'mapped feature')
        name = f.get('backing_node_id')
        if not isinstance(name, str) or not name or name in ids:
            raise MIDistributionUpdateError('Feature mapping has missing or duplicated backing node')
        ids.append(name)
        if _obj(f.get('missingness'), f'{name}.missingness') != {'policy': 'mask_and_exclude', 'mask_field': 'observed'}:
            raise MIDistributionUpdateError(f'{name} does not declare mask-and-exclude missingness')
        transform = _obj(f.get('transform'), f'{name}.transform')
        event = _obj(f.get('event'), f'{name}.event')
        if transform.get('kind') == 'presence_threshold':
            if (f.get('source_unit') != 'matched_sat_finding_count' or event.get('kind') != 'binary_presence'
                    or event.get('positive_state') != 1 or event.get('negative_state') != 0
                    or not isinstance(transform.get('threshold'), int) or isinstance(transform['threshold'], bool)
                    or transform['threshold'] < 1):
                raise MIDistributionUpdateError(f'{name} has incompatible count event definition')
        elif transform.get('kind') == 'identity':
            if f.get('source_unit') != 'native_value' or event.get('kind') != 'numeric_interval':
                raise MIDistributionUpdateError(f'{name} has incompatible numeric event definition')
            lo = _finite(event.get('lower'), f'{name}.lower'); hi = _finite(event.get('upper'), f'{name}.upper')
            if not lo < hi or event.get('inclusive_lower') is not True or event.get('exclusive_upper') is not True:
                raise MIDistributionUpdateError(f'{name} has an incompatible numeric interval')
        else:
            raise MIDistributionUpdateError(f'{name} uses an unsupported transformation')
    return [dict(f) for f in features], expected


def _event(value: Any, feature: Mapping[str, Any]) -> bool:
    name = feature['backing_node_id']
    v = _finite(value, f'{name}.value')
    if feature['transform']['kind'] == 'presence_threshold':
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise MIDistributionUpdateError(f'{name} requires a nonnegative integer project finding count')
        return v >= feature['transform']['threshold']
    return feature['event']['lower'] <= v < feature['event']['upper']


def _read_dataset(dataset: Mapping[str, Any], *, population: Mapping[str, Any] | None,
                  features: list[dict], scenario: bool = False) -> tuple[list[dict], dict]:
    data = _obj(dataset, 'reference sample' if not scenario else 'scenario sample')
    if (data.get('schema'), data.get('schema_version'), data.get('sampling_unit')) != (DATASET_SCHEMA, VERSION, 'project'):
        raise MIDistributionUpdateError('Dataset requires pypique.mi_update.reference_dataset@1 project units')
    population_id = data.get('population_id')
    if not isinstance(population_id, str) or not population_id.strip():
        raise MIDistributionUpdateError('Dataset population_id is required')
    if population is not None and population_id != population.get('id'):
        raise MIDistributionUpdateError('Reference population_id does not match MI-U1 contract')
    if data.get('data_origin') == 'target_project' or not isinstance(data.get('data_origin'), str) or not data['data_origin']:
        raise MIDistributionUpdateError('Cannot estimate reference distribution from a target project alone')
    if population is not None and data['data_origin'] != population.get('data_origin'):
        raise MIDistributionUpdateError('Reference data origin does not match contract')
    rows = data.get('rows')
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        raise MIDistributionUpdateError('Dataset rows must be nonempty (up to 100000 projects)')
    if population is not None and len(rows) != population.get('sample_count'):
        raise MIDistributionUpdateError('Reference sample_count does not match supplied dataset')
    digest = canonical_sha256(data)
    if population is not None and digest != population.get('snapshot_sha256'):
        raise MIDistributionUpdateError('Reference snapshot SHA256 mismatch')
    ids = [f['backing_node_id'] for f in features]
    seen = set(); valid = []; excluded = 0
    for idx, row in enumerate(rows):
        row = _obj(row, f'rows[{idx}]')
        project = row.get('project_id')
        if not isinstance(project, str) or not project or project in seen:
            raise MIDistributionUpdateError('Missing/duplicate project_id in reference sample')
        seen.add(project)
        weight = _finite(row.get('base_weight', 1), f'{project}.base_weight')
        if weight <= 0:
            raise MIDistributionUpdateError('Reference base weights must be positive')
        values = _obj(row.get('features'), f'{project}.features')
        if set(values) != set(ids):
            raise MIDistributionUpdateError(f'{project} must explicitly report every mapped feature (possibly masked)')
        states = {}
        complete = True
        for f in features:
            name = f['backing_node_id']
            obs = _obj(values[name], f'{project}.{name}')
            if not isinstance(obs.get('observed'), bool):
                raise MIDistributionUpdateError(f'{project}.{name}.observed must be boolean')
            if not obs['observed']:
                if obs.get('value') is not None:
                    raise MIDistributionUpdateError(f'{project}.{name} masked observation must have null value')
                complete = False
            else:
                states[name] = _event(obs.get('value'), f)
        if complete:
            valid.append({'project_id': project, 'states': states, 'weight': weight})
        else:
            excluded += 1
    return valid, {'population_id': population_id, 'source_sha256': digest, 'total_projects': len(rows),
                   'complete_cases': len(valid), 'excluded_missing': excluded, 'data_origin': data['data_origin'],
                   'sampling_unit': 'project'}


def _ess(weights: list[float]) -> float:
    total = math.fsum(weights)
    sq = math.fsum(w*w for w in weights)
    return total*total/sq if sq > 0 else 0.0


def _support(rows: list[dict], weights: list[float], minimum: int, minimum_ess: float, side: str) -> dict:
    if len(rows) < minimum or _ess(weights) + 1e-9 < minimum_ess:
        raise MIDistributionUpdateError(f'{side} has insufficient complete-case/effective sample support')
    return {'project_count': len(rows), 'weight_total': math.fsum(weights),
            'effective_sample_size': _ess(weights)}


def _statistics(rows: list[dict], weights: list[float], features: list[dict]) -> dict:
    ids = sorted(f['backing_node_id'] for f in features)
    denominator = math.fsum(weights)
    if denominator <= 0:
        raise MIDistributionUpdateError('Empty probability mass')
    marginals = {}
    for feature in ids:
        p = math.fsum(w for row, w in zip(rows, weights) if row['states'][feature])/denominator
        marginals[feature] = {'event_true': p, 'event_false': 1-p}
    joints = []
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            p11 = math.fsum(w for row, w in zip(rows, weights) if row['states'][a] and row['states'][b])/denominator
            p10 = marginals[a]['event_true'] - p11
            p01 = marginals[b]['event_true'] - p11
            p00 = 1 - marginals[a]['event_true'] - marginals[b]['event_true'] + p11
            cells = {'00': p00, '01': p01, '10': p10, '11': p11}
            if any(v < -1e-10 or v > 1+1e-10 for v in cells.values()):
                raise MIDistributionUpdateError('Inconsistent empirical joint/marginal probabilities')
            joints.append({'left': a, 'right': b,
                           'cells': {key: max(0.0, min(1.0, value)) for key, value in cells.items()}})
    return {'marginals': marginals, 'joints': joints, 'estimator': 'weighted_empirical_complete_case',
            'smoothing': 'none', 'zero_probability_policy': 'retain_exact_zero_for_MI_U3_handling'}


def _condition(rows: list[dict], features: list[dict], names: list[str], side: str) -> list[dict]:
    mapped = {f['backing_node_id']: f for f in features}
    desired = {}
    for name in names:
        f = mapped[name]
        obs = _obj(f[side], f'{name}.{side}')
        if obs.get('observed') is not True:
            raise MIDistributionUpdateError(f'Conditioning {name} requires observed {side} event')
        desired[name] = _event(obs.get('value'), f)
    return [row for row in rows if all(row['states'][name] == state for name, state in desired.items())]


def _rake(rows: list[dict], base: list[float], targets: Mapping[str, float], *, maximum: int,
          tolerance: float) -> tuple[list[float], dict]:
    """Positive empirical exponential tilt via iterative proportional fitting."""
    for feature, target in targets.items():
        present = sum(1 for r in rows if r['states'][feature])
        if not (0 < present < len(rows)):
            raise MIDistributionUpdateError(f'Reweighting {feature} requires both event states in reference support')
        if not (0 < target < 1):
            raise MIDistributionUpdateError(f'Reweighting {feature} target prevalence must be strictly between 0 and 1')
    weights = list(base)
    for iteration in range(1, maximum+1):
        for name, target in sorted(targets.items()):
            denom = math.fsum(weights)
            positive = math.fsum(w for r, w in zip(rows, weights) if r['states'][name])
            if denom <= 0 or not 0 < positive < denom:
                raise MIDistributionUpdateError('Reweighting lost overlap/positive mass')
            current = positive/denom
            t_scale = target/current
            f_scale = (1-target)/(1-current)
            weights = [w*(t_scale if r['states'][name] else f_scale) for r, w in zip(rows, weights)]
            renorm = math.fsum(weights)
            if not math.isfinite(renorm) or renorm <= 0:
                raise MIDistributionUpdateError('Unstable calibration weights')
            weights = [w/renorm for w in weights]
        errors = {name: abs(math.fsum(w for r,w in zip(rows, weights) if r['states'][name])-target)
                  for name, target in targets.items()}
        if max(errors.values()) <= tolerance:
            return weights, {'iterations': iteration, 'max_absolute_prevalence_error': max(errors.values()),
                             'target_event_prevalences': dict(sorted(targets.items())),
                             'algorithm': 'iterative_proportional_fitting_positive_event_weights'}
    raise MIDistributionUpdateError('Reweighting did not converge: target marginals lack joint support or are incompatible')


def estimate_mi_u2_distribution(*, conclusion_path: str | Path, contract: Mapping[str, Any],
                                reference_dataset: Mapping[str, Any], protocol: Mapping[str, Any],
                                scenario_dataset: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Estimate two associational event distributions; never modify the model/dataset."""
    features, model = _verify_contract(contract, conclusion_path)
    cfg = _obj(protocol, 'MI-U2 estimation protocol')
    if (cfg.get('schema'), cfg.get('schema_version')) != (PROTOCOL_SCHEMA, VERSION):
        raise MIDistributionUpdateError('Unsupported MI-U2 estimation protocol/version')
    min_cases = _positive_int(cfg.get('min_complete_cases', 5), 'min_complete_cases')
    min_ess = _finite(cfg.get('min_effective_sample_size', 5.0), 'min_effective_sample_size')
    if min_ess < 2 or min_cases < 2:
        raise MIDistributionUpdateError('At least two independent/effective reference projects are required')
    pop = _obj(contract.get('reference_population'), 'reference_population')
    reference, ref_info = _read_dataset(reference_dataset, population=pop, features=features)
    dist = _obj(contract.get('distribution'), 'distribution')
    mode = dist.get('mode')
    base_rows, new_rows = reference, reference
    base_weights = [r['weight'] for r in reference]
    new_weights = list(base_weights)
    details: dict[str, Any] = {}
    new_source = ref_info
    if mode == 'reference_conditioning':
        if cfg.get('target_event_prevalences') is not None or scenario_dataset is not None:
            raise MIDistributionUpdateError('Conditioning does not accept prevalence targets or a scenario cohort')
        names = dist.get('conditioning_variables')
        if not isinstance(names, list) or not names or len(set(names)) != len(names) or any(
                name not in {f['backing_node_id'] for f in features} for name in names):
            raise MIDistributionUpdateError('Conditioning variables must be mapped observable features')
        base_rows = _condition(reference, features, names, 'baseline')
        new_rows = _condition(reference, features, names, 'hypothetical')
        if {k: _event(f['baseline']['value'], f) for f in features for k in [f['backing_node_id']] if k in names} == {
                k: _event(f['hypothetical']['value'], f) for f in features for k in [f['backing_node_id']] if k in names}:
            raise MIDistributionUpdateError('Edited diagnostic did not change any declared conditioning event')
        base_weights = [r['weight'] for r in base_rows]
        new_weights = [r['weight'] for r in new_rows]
        details = {'conditioning_variables': sorted(names),
                   'interpretation': 'separate empirical reference subpopulations, not a project intervention'}
    elif mode == 'reference_reweighting':
        if scenario_dataset is not None:
            raise MIDistributionUpdateError('Reweighting does not accept an external scenario sample')
        if cfg.get('target_event_prevalences') is None:
            raise MIDistributionUpdateError('Reweighting requires explicit population-level prevalence targets')
        raw = _obj(cfg.get('target_event_prevalences'), 'target_event_prevalences')
        if not raw:
            raise MIDistributionUpdateError('Reweighting requires explicit population-level prevalence targets')
        changed = {f['backing_node_id'] for f in features if f['baseline'] != f['hypothetical']}
        if not set(raw) <= changed or any(name not in {f['backing_node_id'] for f in features} for name in raw):
            raise MIDistributionUpdateError('Reweighting targets must name modified mapped diagnostics')
        targets = {name: _finite(value, f'{name}.target_event_prevalence') for name, value in raw.items()}
        maximum = _positive_int(cfg.get('max_iterations', 500), 'max_iterations')
        if maximum > MAX_ITERATIONS:
            raise MIDistributionUpdateError('max_iterations exceeds safety bound')
        tolerance = _finite(cfg.get('tolerance', 1e-8), 'tolerance')
        if not 0 < tolerance <= 1e-3:
            raise MIDistributionUpdateError('tolerance must be in (0, 0.001]')
        new_weights, details = _rake(reference, base_weights, targets, maximum=maximum, tolerance=tolerance)
        details['interpretation'] = 'declared population event-prevalence constraints, NOT inferred from an edited project count'
    elif mode == 'declared_distributional_scenario':
        if cfg.get('target_event_prevalences') is not None or scenario_dataset is None:
            raise MIDistributionUpdateError('Declared scenario requires separate project cohort, not prevalence targets')
        new_rows, new_source = _read_dataset(scenario_dataset, population=None, features=features, scenario=True)
        if new_source['source_sha256'] == ref_info['source_sha256'] or new_source['population_id'] == ref_info['population_id']:
            raise MIDistributionUpdateError('Scenario requires an independently declared population/cohort')
        new_weights = [r['weight'] for r in new_rows]
        details = {'interpretation': 'comparison of two observed declared cohorts, no counterfactual intervention'}
    else:
        raise MIDistributionUpdateError('Unknown MI-U1 distribution update mode')
    base_support = _support(base_rows, base_weights, min_cases, min_ess, 'Baseline')
    new_support = _support(new_rows, new_weights, min_cases, min_ess, 'Hypothetical')
    baseline = {'support': base_support, 'probabilities': _statistics(base_rows, base_weights, features)}
    updated = {'support': new_support, 'probabilities': _statistics(new_rows, new_weights, features)}
    result = {'schema': RESULT_SCHEMA, 'schema_version': VERSION,
              'status': 'empirical_event_distributions_estimated', 'distribution_mode': mode,
              'contract_sha256': contract['contract_sha256'], 'concluded_model': model,
              'reference': ref_info, 'scenario_source': new_source if mode == 'declared_distributional_scenario' else None,
              'protocol_sha256': canonical_sha256(cfg), 'protocol_details': details,
              'baseline': baseline, 'hypothetical': updated,
              'limits': {'statistical_interpretation': 'associational reference event estimates only',
                         'complete_case_policy': 'exclude entire reference project if any mapped feature masked',
                         'learned_backing_updated': False, 'trained_rbm_inference_performed': False,
                         'updated_pmi': None, 'latent_information_attribution': None,
                         'pf_tqi': None, 'uncertainty_intervals': None,
                         'causal_or_single_project_population_claim': False}}
    result['result_sha256'] = canonical_sha256(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='MI-U2 reference distribution estimator; no PMI/PF/TQI updates')
    parser.add_argument('concluded_model', help='verified finalized MI package ZIP or version folder')
    parser.add_argument('contract', help='validated MI-U1 contract JSON')
    parser.add_argument('reference_dataset', help='project-level reference sample JSON')
    parser.add_argument('protocol', help='MI-U2 estimation protocol JSON')
    parser.add_argument('--scenario-dataset', help='independent cohort for declared_distributional_scenario')
    parser.add_argument('--output', help='write a new immutable result JSON (never overwrite)')
    args = parser.parse_args(argv)
    def load(p: str) -> dict:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    result = estimate_mi_u2_distribution(conclusion_path=args.concluded_model,
                contract=load(args.contract), reference_dataset=load(args.reference_dataset),
                protocol=load(args.protocol),
                scenario_dataset=load(args.scenario_dataset) if args.scenario_dataset else None)
    encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if args.output:
        with Path(args.output).open('x', encoding='utf-8') as destination:
            destination.write(encoded)
    else:
        print(encoded, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
