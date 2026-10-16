"""MI-U1: versioned, non-executing evidence/event protocol for MI Option B.

This validates an explicitly defined *distribution-level* update experiment.
Neither changing a project count nor assembling this contract reestimates a
population distribution, alters a signed PMI, or evaluates PF/TQI. Those
operations begin in MI-U2 through MI-U5, using this contract as input.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .finalized_model_registry import read_conclusion
from .research_models import canonical_sha256

SPEC_SCHEMA = 'pypique.mi_update.evidence_spec'
CONTRACT_SCHEMA = 'pypique.mi_update.evidence_contract'
PAH_SCHEMA = 'pah.mi_inference_request'
VERSION = 1
HEX = re.compile(r'[0-9a-f]{64}\Z')
OBSERVABLE = {'cwe', 'feature', 'measure', 'diagnostic'}
FAMILIES = {'bernoulli', 'gaussian', 'student_t'}
MODES = {'reference_conditioning', 'reference_reweighting', 'declared_distributional_scenario'}
MAX_FEATURES = 4096


class MIUpdateContractError(ValueError):
    """Evidence or event mapping is ambiguous, unsafe, or incompatible."""


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MIUpdateContractError(f'{name} must be an object')
    return value


def _label(value: Any, name: str, limit: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise MIUpdateContractError(f'{name} requires a nonempty string (maximum {limit})')
    return value.strip()


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise MIUpdateContractError(f'{name} requires a lowercase SHA256')
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MIUpdateContractError(f'{name} requires a positive integer')
    return value


def _number(value: Any, name: str, *, count: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MIUpdateContractError(f'{name} must be a finite number')
    if count and (not isinstance(value, int) or value < 0):
        raise MIUpdateContractError(f'{name} must be a nonnegative integer observation count')
    return value


def _latent_info(probability: Mapping[str, Any]) -> tuple[set[str], set[int], set[str]]:
    nodes = probability.get('nodes') or []
    if not isinstance(nodes, list):
        raise MIUpdateContractError('Concluded probability nodes are malformed')
    observables, latent_layers, latent_ids = set(), set(), set()
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        identifier = node.get('id')
        kind = str(node.get('kind') or '').lower()
        if not isinstance(identifier, str) or not identifier:
            continue
        if kind in OBSERVABLE:
            observables.add(identifier)
        if kind in {'latent', 'hidden'}:
            latent_ids.add(identifier)
            layer = node.get('layer')
            if isinstance(layer, int) and not isinstance(layer, bool) and layer >= 1:
                latent_layers.add(layer)
    if not observables or not latent_ids:
        raise MIUpdateContractError('MI backing lacks observable and latent nodes')
    return observables, latent_layers, latent_ids


def _family_info(probability: Mapping[str, Any], declared: Mapping[str, Any], layers: set[int]) -> dict[str, Any]:
    family = _label(declared.get('rbm_family'), 'model_compatibility.rbm_family', 100).lower().replace('-', '_')
    if family not in FAMILIES:
        raise MIUpdateContractError('Unsupported RBM family (expected bernoulli, gaussian or student_t)')
    depth = _positive_int(declared.get('latent_depth'), 'model_compatibility.latent_depth')
    if layers and (depth != max(layers) or layers != set(range(1, depth + 1))):
        raise MIUpdateContractError('Declared latent depth conflicts with recorded latent layers')
    metadata = probability.get('metadata') if isinstance(probability.get('metadata'), Mapping) else {}
    actual = [str(metadata[k]).lower().replace('-', '_') for k in ('rbm_family', 'distribution_family', 'energy_family')
              if isinstance(metadata.get(k), str) and metadata[k].strip()]
    if actual and (len(set(actual)) > 1 or actual[0] != family):
        raise MIUpdateContractError('Declared RBM family conflicts with recorded backing metadata')
    checkpoint = declared.get('checkpoint_sha256')
    if checkpoint is not None:
        _sha(checkpoint, 'model_compatibility.checkpoint_sha256')
    return {'rbm_family': family, 'latent_depth': depth,
            'family_evidence': 'recorded_backing_metadata' if actual else 'operator_declared_unverified',
            'latent_depth_evidence': 'recorded_layer_indices' if layers else 'operator_declared_unverified',
            'checkpoint_sha256': checkpoint}


def _event_transform(row: Mapping[str, Any], *, family: str, label: str) -> tuple[dict, dict]:
    transformation = _object(row.get('transform'), f'{label}.transform')
    event = _object(row.get('event'), f'{label}.event')
    kind = transformation.get('kind')
    if kind == 'presence_threshold':
        if family != 'bernoulli':
            raise MIUpdateContractError(f'{label}: binary presence threshold requires Bernoulli family')
        threshold = _number(transformation.get('threshold'), f'{label}.transform.threshold', count=True)
        if threshold < 1:
            raise MIUpdateContractError(f'{label}: presence threshold must be at least one')
        if event.get('kind') != 'binary_presence' or event.get('positive_state') != 1 or event.get('negative_state') != 0:
            raise MIUpdateContractError(f'{label}: binary event must define present=1 and absent=0')
        return {'kind': kind, 'threshold': threshold}, {'kind': 'binary_presence', 'positive_state': 1, 'negative_state': 0}
    if kind == 'identity':
        if event.get('kind') != 'numeric_interval':
            raise MIUpdateContractError(f'{label}: identity requires a declared numeric_interval event')
        lower = _number(event.get('lower'), f'{label}.event.lower')
        upper = _number(event.get('upper'), f'{label}.event.upper')
        if lower >= upper:
            raise MIUpdateContractError(f'{label}: event interval is empty')
        unit = _label(event.get('unit'), f'{label}.event.unit', 128)
        return {'kind': kind}, {'kind': 'numeric_interval', 'lower': lower, 'upper': upper, 'unit': unit,
                                'inclusive_lower': True, 'exclusive_upper': True}
    raise MIUpdateContractError(f'{label}: unsupported or undefined event transformation')


def _scenario_value(raw: Any, name: str, *, count: bool) -> dict:
    row = _object(raw, name)
    observed = row.get('observed')
    if not isinstance(observed, bool):
        raise MIUpdateContractError(f'{name}.observed must explicitly be true/false')
    value = row.get('value')
    if not observed:
        if value is not None:
            raise MIUpdateContractError(f'{name}: masked observation must have null value')
    else:
        _number(value, f'{name}.value', count=count)
    return {'observed': observed, 'value': value}


def _validate_pah_request(handoff: Mapping[str, Any], concluded: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Optional strict QI-5 import: does NOT promote provider placeholders to feature values."""
    if (handoff.get('schema'), handoff.get('schema_version')) != (PAH_SCHEMA, 1):
        raise MIUpdateContractError('Expected PAH QI-5 inference request version 1')
    digest = handoff.get('request_sha256')
    _sha(digest, 'request_sha256')
    if canonical_sha256({k: v for k, v in handoff.items() if k != 'request_sha256'}) != digest:
        raise MIUpdateContractError('PAH request fingerprint mismatch')
    if handoff.get('status') != 'prepared_not_executed':
        raise MIUpdateContractError('Only unexecuted QI-5 requests can enter MI-U1')
    result = _object(handoff.get('estimation'), 'estimation')
    if result.get('performed') is not False or result.get('results') is not None:
        raise MIUpdateContractError('MI-U1 must not import an asserted estimation')
    network = _object(handoff.get('network'), 'network')
    docs = concluded['manifest']['files']
    fingerprints = {'concluded_family': 'mi_informed_pique', 'concluded_version_id': concluded['version_id'],
                    'archive_sha256': concluded['archive_sha256'], 'manifest_sha256': concluded['manifest_sha256'],
                    'signed_information_topology_sha256': docs['signed_information_topology.json'],
                    'learned_probabilistic_backing_sha256': docs['probabilistic_model.json']}
    if any(network.get(k) != v for k, v in fingerprints.items()):
        raise MIUpdateContractError('QI-5 request is not bound to the selected concluded MI package')
    inputs = handoff.get('inputs')
    if not isinstance(inputs, list) or not inputs or len(inputs) > MAX_FEATURES:
        raise MIUpdateContractError('QI-5 handoff requires bounded modified inputs')
    mapped: dict[str, Mapping[str, Any]] = {}
    for item in inputs:
        item = _object(item, 'QI-5 input')
        name = _label(item.get('source_node_id'), 'QI-5 input.source_node_id')
        if name in mapped or item.get('model_input_value') is not None or item.get('model_input_status') != 'requires_provider_transformation':
            raise MIUpdateContractError('QI-5 input is duplicated or falsely claimed to be transformed')
        mapped[name] = item
    return mapped


def build_mi_u1_contract(*, conclusion_path: str | Path, specification: Mapping[str, Any],
                         pah_request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate a complete *design*; return immutable source-bound, non-executing contract.

    No dataset is read, no learned model is modified, and no probability or score
    is calculated. A valid design is not an identifiable or fitted distribution.
    """
    spec = _object(specification, 'specification')
    if (spec.get('schema'), spec.get('schema_version')) != (SPEC_SCHEMA, VERSION):
        raise MIUpdateContractError('Unsupported MI-U1 evidence specification/version')
    concluded = read_conclusion(conclusion_path)  # MF-5 verifies exact byte fingerprints
    if concluded['family'] != 'mi_informed_pique':
        raise MIUpdateContractError('MI-U1 requires a concluded MI-Informed PIQUE model')
    expected = _object(spec.get('model'), 'model')
    for name, actual in (('version_id', concluded['version_id']),
                         ('manifest_sha256', concluded['manifest_sha256']),
                         ('archive_sha256', concluded['archive_sha256'])):
        if expected.get(name) != actual:
            raise MIUpdateContractError(f'Model {name} does not match selected concluded package')
    probability = concluded['documents']['probabilistic_model.json']
    topology = concluded['documents']['signed_information_topology.json']
    information = concluded['documents']['information_model.json']
    observable, layers, _ = _latent_info(probability)
    compatibility = _family_info(probability, _object(spec.get('model_compatibility'), 'model_compatibility'), layers)
    known_diag = {r['id']: r for r in topology.get('nodes', []) if isinstance(r, Mapping) and
                  isinstance(r.get('id'), str) and str(r.get('kind') or '').lower() in OBSERVABLE}
    info_measures = {str(r.get('id')) for r in information.get('nodes', []) if isinstance(r, Mapping)}
    if not known_diag or not info_measures:
        raise MIUpdateContractError('Concluded MI topology is missing source diagnostics or measures')
    cohort = _object(spec.get('reference_population'), 'reference_population')
    sampling_unit = _label(cohort.get('sampling_unit'), 'reference_population.sampling_unit', 100)
    if sampling_unit != 'project':
        raise MIUpdateContractError('MI-U1 supports project-level reference sampling only; do not mix findings and projects')
    population = {'id': _label(cohort.get('id'), 'reference_population.id'),
                  'snapshot_sha256': _sha(cohort.get('snapshot_sha256'), 'reference_population.snapshot_sha256'),
                  'sample_count': _positive_int(cohort.get('sample_count'), 'reference_population.sample_count'),
                  'sampling_unit': sampling_unit,
                  'sampling_frame': _label(cohort.get('sampling_frame'), 'reference_population.sampling_frame'),
                  'cohort_rule': _label(cohort.get('cohort_rule'), 'reference_population.cohort_rule'),
                  'data_origin': _label(cohort.get('data_origin'), 'reference_population.data_origin')}
    if population['data_origin'] == 'target_project':
        raise MIUpdateContractError('Target-project-only evidence is not a benchmark/reference population')
    distribution = _object(spec.get('distribution'), 'distribution')
    mode = distribution.get('mode')
    if mode not in MODES:
        raise MIUpdateContractError('Option B needs an explicit reference distribution-update mode; fixed-PMI Mode A is unsupported')
    variables = distribution.get('conditioning_variables')
    if not isinstance(variables, list) or len(variables) > MAX_FEATURES or any(not isinstance(x, str) or not x for x in variables):
        raise MIUpdateContractError('conditioning_variables must be an explicit list of feature IDs (may be empty)')
    if len(set(variables)) != len(variables):
        raise MIUpdateContractError('Duplicate conditioning variables')
    definition = {'mode': mode, 'conditioning_variables': list(variables),
                  'estimand': _label(distribution.get('estimand'), 'distribution.estimand'),
                  'assumptions': _label(distribution.get('assumptions'), 'distribution.assumptions', 4000),
                  'target_population': _label(distribution.get('target_population'), 'distribution.target_population')}
    if mode == 'reference_conditioning' and not variables:
        raise MIUpdateContractError('Reference conditioning must declare observed conditioning variables')
    rows = spec.get('features')
    if not isinstance(rows, list) or not rows or len(rows) > MAX_FEATURES:
        raise MIUpdateContractError('features must be a nonempty bounded list')
    imported = _validate_pah_request(_object(pah_request, 'pah_request'), concluded) if pah_request is not None else None
    out_features, sources, targets = [], set(), set()
    for index, candidate in enumerate(rows):
        row = _object(candidate, f'features[{index}]')
        name = f'features[{index}]'
        src = _label(row.get('diagnostic_node_id'), f'{name}.diagnostic_node_id')
        measure = _label(row.get('measure_id'), f'{name}.measure_id')
        target = _label(row.get('backing_node_id'), f'{name}.backing_node_id')
        if src not in known_diag or measure not in info_measures or target not in observable:
            raise MIUpdateContractError(f'{name}: diagnostic, information-measure, or backing node not recorded in the concluded model')
        feature_id = str(known_diag[src].get('feature_id') or src.removeprefix('feature:'))
        if measure != feature_id:
            raise MIUpdateContractError(f'{name}: measure_id must resolve to the recorded diagnostic feature_id')
        backing_cwe = target.removeprefix('feature:')
        if backing_cwe != feature_id and target != feature_id:
            raise MIUpdateContractError(f'{name}: backing node is not the same recorded diagnostic feature')
        if src in sources or target in targets:
            raise MIUpdateContractError('Duplicate diagnostic/backing mappings would double-count evidence')
        sources.add(src); targets.add(target)
        unit = row.get('source_unit')
        if unit not in {'matched_sat_finding_count', 'native_value'}:
            raise MIUpdateContractError(f'{name}: source unit must be declared as count or native_value')
        transform, event = _event_transform(row, family=compatibility['rbm_family'], label=name)
        if transform['kind'] == 'presence_threshold' and unit != 'matched_sat_finding_count':
            raise MIUpdateContractError(f'{name}: count-threshold transform requires count input')
        if unit == 'native_value' and transform['kind'] != 'identity':
            raise MIUpdateContractError(f'{name}: native values require explicit identity and compatible event semantics')
        missing = _object(row.get('missingness'), f'{name}.missingness')
        if missing.get('policy') != 'mask_and_exclude' or missing.get('mask_field') != 'observed':
            raise MIUpdateContractError(f'{name}: explicitly use observed=false masking, never zero-impute missing data')
        before = _scenario_value(row.get('baseline'), f'{name}.baseline', count=unit == 'matched_sat_finding_count')
        after = _scenario_value(row.get('hypothetical'), f'{name}.hypothetical', count=unit == 'matched_sat_finding_count')
        if not before['observed'] and not after['observed']:
            raise MIUpdateContractError(f'{name}: both scenario observations are missing')
        if imported is not None:
            input_row = imported.get(src)
            if input_row is None or input_row.get('backing_node_id') != target or unit != input_row.get('unit'):
                raise MIUpdateContractError(f'{name}: QI-5 source/backing or source unit does not match mapping')
            if (before != {'observed': True, 'value': input_row.get('baseline_observed_count')}
                    or after != {'observed': True, 'value': input_row.get('hypothetical_observed_count')}):
                raise MIUpdateContractError(f'{name}: hypothesis conflicts with bound QI-5 scenario observations')
        out_features.append({'diagnostic_node_id': src, 'measure_id': measure, 'backing_node_id': target,
                             'source_unit': unit, 'transform': transform, 'event': event,
                             'missingness': {'policy': 'mask_and_exclude', 'mask_field': 'observed'},
                             'baseline': before, 'hypothetical': after,
                             'semantics': 'project observation, not a new population probability'})
    if imported is not None and sources != set(imported):
        raise MIUpdateContractError('Every modified QI-5 diagnostic must be covered exactly once')
    if not set(variables) <= targets:
        raise MIUpdateContractError('Conditioning variables must reference explicitly mapped backing nodes')
    if not any(x['baseline'] != x['hypothetical'] for x in out_features):
        raise MIUpdateContractError('No diagnostic change was declared')
    lineage = {'source': 'qi5_handoff' if imported is not None else 'direct_model_scenario',
               'pah_request_sha256': imported is not None and pah_request['request_sha256'] or None}
    contract = {'schema': CONTRACT_SCHEMA, 'schema_version': VERSION, 'mode': 'distribution_reestimation_only',
                'model': {'family': concluded['family'], 'version_id': concluded['version_id'],
                          'archive_sha256': concluded['archive_sha256'], 'manifest_sha256': concluded['manifest_sha256'],
                          'signed_topology_sha256': concluded['manifest']['files']['signed_information_topology.json'],
                          'probabilistic_backing_sha256': concluded['manifest']['files']['probabilistic_model.json']},
                'model_compatibility': compatibility, 'reference_population': population,
                'distribution': definition, 'features': sorted(out_features, key=lambda r: r['diagnostic_node_id']),
                'lineage': lineage,
                'identifiability': {'status': 'not_established',
                                    'reason': 'Reference dataset observations, actual masks, estimator selection and overlap/support must be checked by MI-U2. Declared cohort size and assumptions are not evidence of identification.'},
                'execution': {'status': 'contract_only_not_executed', 'updated_distribution': None,
                              'updated_marginals': None, 'updated_joints': None,
                              'updated_signed_pmi': None, 'updated_pf_tqi': None,
                              'learned_model_mutated': False}}
    if compatibility['family_evidence'] == 'operator_declared_unverified' or compatibility['latent_depth_evidence'] == 'operator_declared_unverified':
        contract['identifiability']['reason'] += ' RBM family/depth claims also require learned-checkpoint verification.'
    contract['contract_sha256'] = canonical_sha256(contract)
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='MI-U1 contract validation (no inference or model updates)')
    parser.add_argument('concluded_model', help='MF-5 MI model ZIP or verified directory')
    parser.add_argument('specification', help='Explicit evidence/event specification JSON')
    parser.add_argument('--pah-request', help='Optional unexecuted QI-5 request JSON')
    parser.add_argument('--output', help='Write validated contract to this new JSON file (otherwise stdout)')
    args = parser.parse_args(argv)
    spec = json.loads(Path(args.specification).read_text(encoding='utf-8'))
    handoff = json.loads(Path(args.pah_request).read_text(encoding='utf-8')) if args.pah_request else None
    contract = build_mi_u1_contract(conclusion_path=args.concluded_model, specification=spec, pah_request=handoff)
    rendered = json.dumps(contract, indent=2, sort_keys=True, allow_nan=False) + '\n'
    if args.output:
        destination = Path(args.output)
        with destination.open('x', encoding='utf-8') as handle:
            handle.write(rendered)
    else:
        print(rendered, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
