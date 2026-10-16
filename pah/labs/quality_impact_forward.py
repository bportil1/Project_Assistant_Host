"""QI-3: verified Standard PIQUE native evaluation from an explicit input contract.

This does not infer model-native diagnostic values from SAT counts. A mapping
records every native diagnostic baseline and (optionally) the explicit native
value represented by an additional/missing matched SAT record. pyPIQUE owns
all subsequent normalization, utility, aggregation, and TQI computation.
"""
from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping


class ForwardEvaluationError(ValueError):
    """Native inputs, source lineage, or concluded evaluation are not usable."""


SCHEMA = 'pah.standard_native_diagnostic_mapping'
MAX_BYTES = 1024 * 1024


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key {key!r}')
        result[key] = value
    return result


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForwardEvaluationError(f'{field} must be a finite numeric native model value')
    try:
        number = float(value)
    except OverflowError as exc:
        raise ForwardEvaluationError(f'{field} must be a finite native number') from exc
    if not math.isfinite(number) or number < 0.0:
        raise ForwardEvaluationError(f'{field} must be finite and nonnegative')
    return number


def read_native_mapping(path: str | Path, inspection: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a complete, explicitly sourced map to native diagnostic units.

    Digest binds it to the *selected* finalized model and inspected evidence.
    Full diagnostic coverage blocks accidental implicit zero-filling. A unit
    factor is never guessed: it is declared per diagnostic and only used for
    hypothetical edits of an explicitly SAT-linked input.
    """
    if inspection.get('family') != 'standard_pique' or not inspection.get('selected'):
        raise ForwardEvaluationError('Native forward evaluation requires a selected Standard PIQUE model')
    evidence = inspection.get('evidence', {}).get('source')
    if not evidence:
        raise ForwardEvaluationError('Select matching local SAT evidence before binding native inputs')
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != '.json':
        raise ForwardEvaluationError('Select a local, non-symlink native diagnostic mapping JSON')
    if source.stat().st_size > MAX_BYTES:
        raise ForwardEvaluationError('Native diagnostic mapping exceeds 1 MiB')
    raw = source.read_bytes()
    try:
        document = json.loads(raw, object_pairs_hook=_unique_keys,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError) as exc:
        raise ForwardEvaluationError(f'Invalid native input mapping JSON: {exc}') from exc
    if not isinstance(document, dict) or document.get('schema') != SCHEMA or document.get('schema_version') != 1:
        raise ForwardEvaluationError('Unknown native diagnostic mapping schema/version')
    if document.get('model_manifest_sha256') != inspection['manifest_sha256']:
        raise ForwardEvaluationError('Native mapping model manifest fingerprint differs from selected version')
    if document.get('sat_evidence_sha256') != evidence['sha256']:
        raise ForwardEvaluationError('Native mapping SAT evidence fingerprint differs from inspected evidence')
    records = document.get('diagnostics')
    required = {str(node['id']) for node in inspection['network']['nodes'] if node.get('kind') == 'diagnostic'}
    if not isinstance(records, dict) or set(records) != required or not required:
        missing = sorted(required - set(records)) if isinstance(records, dict) else sorted(required)
        unexpected = sorted(set(records) - required) if isinstance(records, dict) else []
        raise ForwardEvaluationError(f'Native diagnostic mapping must cover all concluded diagnostics; missing={missing}, unexpected={unexpected}')
    inputs = {}
    for identifier, spec in records.items():
        if not isinstance(spec, dict):
            raise ForwardEvaluationError(f'{identifier}: diagnostic mapping must be an object')
        origin = spec.get('provenance')
        if not isinstance(origin, str) or not origin.strip():
            raise ForwardEvaluationError(f'{identifier}: nonempty native-input provenance is required')
        baseline = _number(spec.get('baseline_native_value'), f'{identifier}.baseline_native_value')
        per_finding = spec.get('native_units_per_finding', None)
        if per_finding is not None:
            per_finding = _number(per_finding, f'{identifier}.native_units_per_finding')
        inputs[identifier] = {'baseline_native_value': baseline,
                              'native_units_per_finding': per_finding,
                              'provenance': origin.strip()}
    return {'path': str(source.resolve()), 'sha256': sha256(raw).hexdigest(),
            'schema': SCHEMA, 'schema_version': 1,
            'model_manifest_sha256': inspection['manifest_sha256'],
            'sat_evidence_sha256': evidence['sha256'], 'diagnostics': inputs}


def _native_loader(path: str):
    # Reuse pyPIQUE's MF-5 verifier/loader; do not implement a PAH scorer.
    from pique_py.finalized_model_registry import load_standard_concluded_model
    return load_standard_concluded_model(path)


def native_evaluate(model_path: str, values: Mapping[str, float],
                    *, loader: Callable | None = None) -> dict[str, Any]:
    """Evaluate using actual native ModelNode evaluators and cached-child traversal."""
    try:
        model = (loader or _native_loader)(model_path)
        model.reset()
        nodes = model.all_nodes()
        reachable_diagnostics = model.diagnostics
        if set(reachable_diagnostics) - set(values):
            raise ForwardEvaluationError('Native inputs are missing reachable diagnostics')
        for identifier, node in reachable_diagnostics.items():
            node.value = _number(values[identifier], f'{identifier}.native_value')
        value = model.tqi.get_value(recompute=True)
        if not math.isfinite(value):
            raise ForwardEvaluationError('Native TQI evaluation returned a non-finite value')
        groups = {'diagnostic': {}, 'measure': {}, 'product_factor': {},
                  'quality_aspect': {}, 'tqi': {}}
        for identifier, node in nodes.items():
            evaluated = float(node.get_value())
            if not math.isfinite(evaluated):
                raise ForwardEvaluationError(f'Non-finite native value for {identifier}')
            groups[node.node_type.value][identifier] = evaluated
        return {'unit': 'native_quality_model_value', 'tqi': value,
                'node_values': groups, 'evaluation_engine': 'pique_py.QualityModel',
                'calculation': 'concluded_native_evaluators',
                'note': 'Native pyPIQUE evaluation, not a learned probability or causal inference'}
    except ForwardEvaluationError:
        raise
    except (RuntimeError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise ForwardEvaluationError(f'Native pyPIQUE evaluation failed: {exc}') from exc


def forward_result(inspection: Mapping[str, Any], scenario: Mapping[str, Any],
                   mapping: Mapping[str, Any], *, loader: Callable | None = None) -> dict[str, Any]:
    if inspection['family'] != 'standard_pique':
        raise ForwardEvaluationError('MI information models cannot use the Standard PIQUE evaluator')
    if mapping['model_manifest_sha256'] != inspection['manifest_sha256'] or mapping['sat_evidence_sha256'] != inspection['evidence']['source']['sha256']:
        raise ForwardEvaluationError('Native inputs belong to a different finalized model or evidence')
    baseline_inputs = {key: record['baseline_native_value'] for key, record in mapping['diagnostics'].items()}
    baseline = native_evaluate(inspection['model_path'], baseline_inputs, loader=loader)
    changed = [row for row in scenario['rows'] if row['changed']]
    scenario_inputs = dict(baseline_inputs)
    transformations = []
    for row in changed:
        identifier = row['node_id']
        record = mapping['diagnostics'].get(identifier)
        factor = record.get('native_units_per_finding') if record else None
        if factor is None:
            return {'schema': 'pah.standard_forward_evaluation', 'schema_version': 1,
                    'status': 'scenario_blocked', 'reason': f'{identifier} has no explicitly declared native_units_per_finding; native baseline evaluated, scenario not inferred',
                    'baseline': baseline, 'scenario': None,
                    'mapping_sha256': mapping['sha256'], 'scenario_revision': scenario['revision'],
                    'scenario_id': scenario['scenario_id'], 'read_only_sources': True}
        proposed = baseline_inputs[identifier] + row['delta'] * factor
        if proposed < 0 or not math.isfinite(proposed):
            return {'schema': 'pah.standard_forward_evaluation', 'schema_version': 1,
                    'status': 'scenario_blocked',
                    'reason': f'{identifier} hypothetical input is negative or non-finite in declared native units',
                    'baseline': baseline, 'scenario': None,
                    'mapping_sha256': mapping['sha256'], 'scenario_revision': scenario['revision'],
                    'scenario_id': scenario['scenario_id'], 'read_only_sources': True}
        scenario_inputs[identifier] = proposed
        transformations.append({'diagnostic_id': identifier, 'observed_count_delta': row['delta'],
                                'declared_native_units_per_finding': factor,
                                'baseline_native_value': baseline_inputs[identifier],
                                'hypothetical_native_value': proposed,
                                'assumption': 'operator_supplied_linear_per_finding_conversion',
                                'provenance': record['provenance']})
    evaluated = native_evaluate(inspection['model_path'], scenario_inputs, loader=loader)
    return {'schema': 'pah.standard_forward_evaluation', 'schema_version': 1,
            'status': 'ready', 'baseline': baseline, 'scenario': evaluated,
            'mapping_sha256': mapping['sha256'], 'mapping_path': mapping['path'],
            'manifest_sha256': inspection['manifest_sha256'],
            'evidence_sha256': inspection['evidence']['source']['sha256'],
            'model_version_id': inspection['version_id'],
            'baseline_native_input_provenance': {key: record['provenance'] for key, record in mapping['diagnostics'].items()},
            'scenario_id': scenario['scenario_id'], 'scenario_revision': scenario['revision'],
            'native_input_transformations': transformations, 'read_only_sources': True,
            'note': ('Native outputs use concluded Standard PIQUE normalization, utility, and aggregation. '
                     'Per-finding conversion, when applied, is an explicit hypothetical assumption, not a learned relationship.')}
