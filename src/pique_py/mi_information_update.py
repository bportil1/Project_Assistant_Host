"""MI-U3: signed event-level PMI and MI from *validated* MI-U2 distributions.

These are descriptive associations of empirical binary events. They are NOT
learned RBM weights, latent conditional information, normalized PF shares, or
updated PIQUE scores. The finalized model and U2 records are read-only.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .mi_distribution_update import (MIDistributionUpdateError, RESULT_SCHEMA as U2_SCHEMA,
                                     _verify_contract)
from .research_models import canonical_sha256

POLICY_SCHEMA = 'pypique.mi_update.information_policy'
RESULT_SCHEMA = 'pypique.mi_update.information_estimate'
VERSION = 1
_CELLS = ('00', '01', '10', '11')
_EPS = 1e-8  # validation slack ONLY, never estimator smoothing


class MIInformationUpdateError(MIDistributionUpdateError):
    """Malformed, inconsistent, or unsupported information calculation."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MIInformationUpdateError(f'{label} must be an object')
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MIInformationUpdateError(f'{label} must be a finite numeric value')
    return float(value)


def _prob(value: Any, label: str) -> float:
    v = _number(value, label)
    if v < -_EPS or v > 1 + _EPS:
        raise MIInformationUpdateError(f'{label} is outside [0,1]')
    return min(1., max(0., v))


def _policy(config: Mapping[str, Any]) -> dict[str, Any]:
    p = _object(config, 'MI-U3 policy')
    if (p.get('schema'), p.get('schema_version')) != (POLICY_SCHEMA, VERSION):
        raise MIInformationUpdateError('Unsupported MI-U3 policy schema/version')
    if set(p) - {'schema', 'schema_version', 'zero_probability_policy',
                 'uniform_mixture_strength', 'min_effective_cell_mass'}:
        raise MIInformationUpdateError('Unsupported MI-U3 policy field')
    method = p.get('zero_probability_policy', 'undefined')
    if method not in ('undefined', 'uniform_joint_mixture'):
        raise MIInformationUpdateError('Unknown zero-probability policy')
    strength = p.get('uniform_mixture_strength')
    if method == 'undefined':
        if strength is not None:
            raise MIInformationUpdateError('Smoothing strength requires explicit uniform_joint_mixture policy')
        strength = 0.0
    else:
        strength = _number(strength, 'uniform_mixture_strength')
        if not 0 < strength < 1:
            raise MIInformationUpdateError('Smoothing strength must be strictly between 0 and 1')
    threshold = _number(p.get('min_effective_cell_mass', 5.0), 'min_effective_cell_mass')
    if not 1 <= threshold <= 100000:
        raise MIInformationUpdateError('min_effective_cell_mass must be in [1,100000]')
    return {'zero_probability_policy': method, 'uniform_mixture_strength': strength,
            'min_effective_cell_mass': threshold}


def _validate_side(side: Any, feature_ids: list[str], label: str) -> dict[str, Any]:
    side = _object(side, label)
    support = _object(side.get('support'), f'{label}.support')
    count = support.get('project_count')
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise MIInformationUpdateError(f'{label}.support.project_count must be >= 2')
    ess = _number(support.get('effective_sample_size'), f'{label}.effective_sample_size')
    weight = _number(support.get('weight_total'), f'{label}.weight_total')
    if ess < 2 - _EPS or ess > count + _EPS or weight <= 0:
        raise MIInformationUpdateError(f'{label} has invalid sample/ESS support')
    stats = _object(side.get('probabilities'), f'{label}.probabilities')
    if stats.get('estimator') != 'weighted_empirical_complete_case' or stats.get('smoothing') != 'none':
        raise MIInformationUpdateError(f'{label} is not an unsmoothed MI-U2 empirical distribution')
    raw_marg = _object(stats.get('marginals'), f'{label}.marginals')
    if set(raw_marg) != set(feature_ids):
        raise MIInformationUpdateError(f'{label} marginal feature set differs from MI-U1')
    marginals = {}
    for name in feature_ids:
        rec = _object(raw_marg[name], f'{label}.{name}')
        if set(rec) != {'event_true', 'event_false'}:
            raise MIInformationUpdateError(f'{label}.{name} requires both event probabilities')
        true = _prob(rec['event_true'], f'{label}.{name}.true')
        false = _prob(rec['event_false'], f'{label}.{name}.false')
        if abs(true + false - 1) > _EPS:
            raise MIInformationUpdateError(f'{label}.{name} marginal does not sum to one')
        marginals[name] = {'0': false, '1': true}
    joints = stats.get('joints')
    if not isinstance(joints, list) or len(joints) != len(feature_ids) * (len(feature_ids)-1)//2:
        raise MIInformationUpdateError(f'{label} must contain every feature pair exactly once')
    expected = {(a, b) for i, a in enumerate(feature_ids) for b in feature_ids[i+1:]}
    pairs = {}
    for entry in joints:
        entry = _object(entry, f'{label}.joint')
        a, b = entry.get('left'), entry.get('right')
        if not isinstance(a, str) or not isinstance(b, str) or (a, b) not in expected or (a, b) in pairs:
            raise MIInformationUpdateError(f'{label} has an extra, reversed, or duplicated joint pair')
        cells_raw = _object(entry.get('cells'), f'{label}.{a}.{b}.cells')
        if set(cells_raw) != set(_CELLS):
            raise MIInformationUpdateError(f'{label}.{a}.{b} has missing joint states')
        cells = {k: _prob(cells_raw[k], f'{label}.{a}.{b}.{k}') for k in _CELLS}
        if (abs(math.fsum(cells.values()) - 1) > _EPS or
                abs(cells['00'] + cells['01'] - marginals[a]['0']) > _EPS or
                abs(cells['10'] + cells['11'] - marginals[a]['1']) > _EPS or
                abs(cells['00'] + cells['10'] - marginals[b]['0']) > _EPS or
                abs(cells['01'] + cells['11'] - marginals[b]['1']) > _EPS):
            raise MIInformationUpdateError(f'{label}.{a}.{b} joint and marginals are inconsistent')
        pairs[(a, b)] = cells
    if set(pairs) != expected:
        raise MIInformationUpdateError(f'{label} lacks required joint pairs')
    return {'support': dict(support), 'marginals': marginals, 'pairs': pairs,
            'effective_sample_size': ess}


def _cell_information(p: float, px: float, py: float) -> tuple[str, float | None, float | None]:
    """PMI=ln(p/(px*py)); NPMI=PMI/(-ln(p)); no hidden pseudocounts."""
    if p == 0:
        return 'undefined_zero_joint', None, None
    if px == 0 or py == 0:
        raise MIInformationUpdateError('Positive joint mass cannot have zero event marginal')
    if p == 1:
        # Necessarily px=py=1 for a coherent binary joint; PMI=0 by limit.
        if abs(px-1) > _EPS or abs(py-1) > _EPS:
            raise MIInformationUpdateError('Deterministic joint contradicts marginals')
        return 'deterministic_joint', 0., 0.
    pmi = math.log(p) - math.log(px) - math.log(py)  # log-domain: avoid tiny px*py underflow
    npmi = pmi / -math.log(p)
    if not math.isfinite(pmi) or not math.isfinite(npmi) or not -1-_EPS <= npmi <= 1+_EPS:
        raise MIInformationUpdateError('Numerically invalid PMI/NPMI for coherent input')
    return 'defined', pmi, min(1., max(-1., npmi))


def _information_pair(cells: Mapping[str, float], marg_a: Mapping[str, float],
                      marg_b: Mapping[str, float], ess: float, threshold: float) -> dict[str, Any]:
    result = {}; terms = []; rare = 0
    for key in _CELLS:
        p = cells[key]
        status, pmi, npmi = _cell_information(p, marg_a[key[0]], marg_b[key[1]])
        mass = ess * p  # ONLY heuristic effective mass, not observed cell counts
        low = mass < threshold
        rare += int(low)
        if pmi is not None:
            terms.append(p * pmi)
        result[key] = {'joint_probability': p, 'left_event_probability': marg_a[key[0]],
                       'right_event_probability': marg_b[key[1]], 'raw_signed_pmi_nats': pmi,
                       'normalized_pointwise_pmi': npmi, 'status': status,
                       'effective_cell_mass_proxy': mass, 'low_effective_support': low}
    mi = math.fsum(terms)
    if mi < -1e-10 or not math.isfinite(mi):
        raise MIInformationUpdateError('Mutual information is invalid for supplied joint/marginals')
    return {'cells': result, 'mutual_information_nats': max(0., mi),
            'mutual_information_is_signed': False, 'low_support_cell_count': rare,
            'estimation_uncertainty': {'confidence_interval': None,
                                       'reason': 'MI-U2 aggregates cannot provide defensible uncertainty intervals; MI-U7 requires resampling/reference evidence',
                                       'low_support_is_descriptive_only': True}}


def _side_information(side: dict[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    strength = config['uniform_mixture_strength']
    raw_pairs = []
    regularized_pairs = []
    rare_pairs = 0
    undefined = 0
    for (a, b), cells in sorted(side['pairs'].items()):
        raw = _information_pair(cells, side['marginals'][a], side['marginals'][b],
                                side['effective_sample_size'], config['min_effective_cell_mass'])
        raw_pairs.append({'left': a, 'right': b, **raw})
        rare_pairs += int(raw['low_support_cell_count'] > 0)
        undefined += sum(v['status'] == 'undefined_zero_joint' for v in raw['cells'].values())
        if strength:
            # Explicit convex mixture of *joint* with a uniform four-cell reference.
            # Marginals are derived from the SAME regularized joint; no pseudo-ESS or
            # implied Dirichlet posterior is claimed. Source MI-U2 data stay intact.
            mixed = {k: (1-strength)*p + strength/4 for k, p in cells.items()}
            ma = {'0': mixed['00']+mixed['01'], '1': mixed['10']+mixed['11']}
            mb = {'0': mixed['00']+mixed['10'], '1': mixed['01']+mixed['11']}
            regularized_pairs.append({'left': a, 'right': b,
                  **_information_pair(mixed, ma, mb, side['effective_sample_size'],
                                       config['min_effective_cell_mass'])})
    return {'support': side['support'], 'marginals': side['marginals'],
            'raw_pairwise_information': raw_pairs,
            'regularized_pairwise_information': regularized_pairs if strength else None,
            'diagnostics': {'pairs_with_low_support_cells': rare_pairs,
                            'undefined_raw_zero_joint_cells': undefined,
                            'confidence_intervals_estimated': False}}


def _comparison(base: dict[str, Any], new: dict[str, Any], *, regularized: bool) -> list[dict[str, Any]]:
    name = 'regularized_pairwise_information' if regularized else 'raw_pairwise_information'
    before = base[name] or []
    after = new[name] or []
    rows = []
    for a, b in zip(before, after):
        if a['left'] != b['left'] or a['right'] != b['right']:
            raise MIInformationUpdateError('Comparison pair identities differ')
        cells = {}
        for state in _CELLS:
            x = a['cells'][state]['raw_signed_pmi_nats']
            y = b['cells'][state]['raw_signed_pmi_nats']
            cells[state] = {'delta_signed_pmi_nats': y-x if x is not None and y is not None else None,
                            'delta_joint_probability': b['cells'][state]['joint_probability']-a['cells'][state]['joint_probability'],
                            'comparable_pmi': x is not None and y is not None}
        rows.append({'left': a['left'], 'right': a['right'],
                     'delta_mutual_information_nats': b['mutual_information_nats']-a['mutual_information_nats'],
                     'cells': cells})
    return rows


def recalculate_mi_u3_information(*, conclusion_path: str | Path, contract: Mapping[str, Any],
                                  distribution_estimate: Mapping[str, Any],
                                  policy: Mapping[str, Any]) -> dict[str, Any]:
    """Recalculate *event-level* signed PMI/MI without changing saved models."""
    cfg = _policy(policy)
    # Validates the concluded ZIP/folder through MF-5 and the U1 model linkage.
    features, model = _verify_contract(contract, conclusion_path)
    estimate = _object(distribution_estimate, 'MI-U2 estimate')
    if (estimate.get('schema'), estimate.get('schema_version'), estimate.get('status')) != (
            U2_SCHEMA, 1, 'empirical_event_distributions_estimated'):
        raise MIInformationUpdateError('Expected completed MI-U2 distribution_estimate@1')
    if estimate.get('result_sha256') != canonical_sha256({k: v for k, v in estimate.items() if k != 'result_sha256'}):
        raise MIInformationUpdateError('MI-U2 distribution fingerprint mismatch')
    if estimate.get('contract_sha256') != contract.get('contract_sha256') or estimate.get('concluded_model') != model:
        raise MIInformationUpdateError('MI-U2 distribution model/contract provenance mismatch')
    if estimate.get('distribution_mode') != contract.get('distribution', {}).get('mode'):
        raise MIInformationUpdateError('MI-U2 distribution mode mismatch')
    source = _object(estimate.get('reference'), 'MI-U2 reference provenance')
    reference = _object(contract.get('reference_population'), 'MI-U1 population')
    if (source.get('source_sha256') != reference.get('snapshot_sha256') or
            source.get('population_id') != reference.get('id') or
            source.get('total_projects') != reference.get('sample_count')):
        raise MIInformationUpdateError('Reference population snapshot mismatch')
    limits = _object(estimate.get('limits'), 'MI-U2 limits')
    if (limits.get('learned_backing_updated') is not False or
            limits.get('trained_rbm_inference_performed') is not False or
            limits.get('updated_pmi') is not None or limits.get('pf_tqi') is not None):
        raise MIInformationUpdateError('Expected MI-U2 empirical-only results without model/PMI updates')
    feature_ids = sorted(f['backing_node_id'] for f in features)
    baseline = _side_information(_validate_side(estimate.get('baseline'), feature_ids, 'baseline'), cfg)
    hypothetical = _side_information(_validate_side(estimate.get('hypothetical'), feature_ids, 'hypothetical'), cfg)
    regularized = cfg['zero_probability_policy'] == 'uniform_joint_mixture'
    result = {'schema': RESULT_SCHEMA, 'schema_version': VERSION,
        'status': 'empirical_event_information_recalculated',
        'concluded_model': model, 'contract_sha256': contract['contract_sha256'],
        'mi_u2_result_sha256': estimate['result_sha256'],
        'mi_u2_protocol_sha256': estimate.get('protocol_sha256'),
        'distribution_mode': estimate['distribution_mode'],
        'policy': cfg, 'policy_sha256': canonical_sha256(policy),
        'baseline': baseline, 'hypothetical': hypothetical,
        'delta_raw': _comparison(baseline, hypothetical, regularized=False),
        'delta_regularized': _comparison(baseline, hypothetical, regularized=True) if regularized else None,
        'semantics': {'raw_signed_pmi': 'natural log [p(x,y) / (p(x)p(y))], signed per event state',
          'normalized_pointwise_pmi': 'PMI / -ln(p(x,y)); bounded [-1,1] when defined',
          'mutual_information': 'sum over observed states p(x,y) PMI(x,y); nonnegative nats; NOT signed',
          'standardized_pmi': None, 'normalized_joint_index_score': None,
          'original_hsqa_normalized_pmi_weights': 'unchanged and NOT replaced by event-level NPMI',
          'regularization': 'optional convex mixture of joint probabilities with uniform reference; reported separately, not a posterior',
          'trained_rbm_weights_changed': False, 'learned_latent_distributions_reestimated': False,
          'latent_pf_information_attribution': None, 'pf_tqi': None, 'causal_effect_claim': False,
          'inference_limits': 'association of reference-cohort events only, not single-project intervention; intervals unavailable from aggregate MI-U2 result'}}
    result['result_sha256'] = canonical_sha256(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='MI-U3: signed event PMI/MI from verified MI-U2 estimates')
    parser.add_argument('concluded_model', help='existing finalized MI model ZIP or folder')
    parser.add_argument('contract', help='MI-U1 evidence contract JSON')
    parser.add_argument('distribution_estimate', help='MI-U2 estimated distribution JSON')
    parser.add_argument('policy', help='MI-U3 policy JSON')
    parser.add_argument('--output', help='create a new result file without overwriting')
    args = parser.parse_args(argv)
    def load(path: str) -> dict:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    result = recalculate_mi_u3_information(conclusion_path=args.concluded_model, contract=load(args.contract),
                 distribution_estimate=load(args.distribution_estimate), policy=load(args.policy))
    encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if args.output:
        with Path(args.output).open('x', encoding='utf-8') as output:
            output.write(encoded)
    else:
        print(encoded, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
