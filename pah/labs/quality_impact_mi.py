"""QI-5: versioned, read-only MI evidence -> inference-provider handoff.

This module assembles and validates a *request*, never runs inference. PAH
cannot infer a new reference population, distribution, PMI, PF or TQI from
hypothetical SAT counts. A future MI-U provider must implement and document
its own distribution-update protocol and output verification.
"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

SCHEMA = 'pah.mi_inference_adapter'
REQUEST_SCHEMA = 'pah.mi_inference_request'
VERSION = 1
MAX_BYTES = 1024 * 1024
HEX_SHA = re.compile(r'[0-9a-f]{64}\Z')
PROVIDER_ID = re.compile(r'[a-z][a-z0-9_.-]{1,127}\Z')


class MIContractError(ValueError):
    """Explicit MI mapping/provider contract is incomplete or mismatched."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _nonempty(value: Any, label: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise MIContractError(f'{label} must be a nonempty string (at most {limit} characters)')
    return value.strip()


def _fingerprint(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX_SHA.fullmatch(value) is None:
        raise MIContractError(f'{label} must be a lowercase SHA256 fingerprint')
    return value


def read_mi_adapter(path: str | Path, inspection: Mapping[str, Any]) -> dict[str, Any]:
    """Read a user-declared binding; never discover/guess feature mappings."""
    if not inspection.get('selected') or inspection.get('family') != 'mi_informed_pique':
        raise MIContractError('MI adapter requires a verified MI-Informed PIQUE conclusion')
    evidence = inspection.get('evidence', {}).get('source')
    if not evidence:
        raise MIContractError('MI adapter requires explicitly linked local SAT evidence')
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != '.json':
        raise MIContractError('Select a local non-symlink MI adapter JSON')
    if source.stat().st_size > MAX_BYTES:
        raise MIContractError('MI adapter JSON exceeds the 1 MiB limit')
    raw = source.read_bytes()
    try:
        document = json.loads(raw, object_pairs_hook=_unique_pairs,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeError) as exc:
        raise MIContractError(f'Invalid MI adapter JSON: {exc}') from exc
    if not isinstance(document, dict) or (document.get('schema'), document.get('schema_version')) != (SCHEMA, VERSION):
        raise MIContractError('Unsupported MI adapter schema/version')
    for field, expected in (('model_manifest_sha256', inspection['manifest_sha256']),
                            ('sat_evidence_sha256', evidence['sha256']),
                            ('signed_network_sha256', inspection['mi_signed_network_sha256']),
                            ('backing_model_sha256', inspection['mi_backing_model_sha256'])):
        if _fingerprint(document.get(field), field) != expected:
            raise MIContractError(f'{field} does not match the selected verified model/evidence')
    provider = document.get('provider')
    if not isinstance(provider, dict):
        raise MIContractError('A declared inference provider is required')
    provider_id = _nonempty(provider.get('id'), 'provider.id', 128)
    if not PROVIDER_ID.fullmatch(provider_id):
        raise MIContractError('provider.id has an invalid identifier')
    provider_version = _nonempty(provider.get('version'), 'provider.version', 100)
    if provider.get('capability') != 'mi.distribution_reestimation@1':
        raise MIContractError('Provider must declare the versioned distribution-reestimation capability')
    owner = _nonempty(provider.get('owner'), 'provider.owner')
    # This is a *declaration* of a target provider, not confirmation that
    # it is installed, running, scientifically calibrated, or authenticated.
    metadata = {'id': provider_id, 'version': provider_version,
                'capability': provider['capability'], 'owner': owner,
                'connection_status': 'declared_not_connected'}
    protocol = document.get('protocol')
    if not isinstance(protocol, dict) or protocol.get('mode') != 'distribution_reestimation':
        raise MIContractError('Only explicit distribution_reestimation is supported (no fixed-PMI posterior Mode A)')
    reference_population = _nonempty(protocol.get('reference_population'), 'protocol.reference_population')
    conditioning = _nonempty(protocol.get('conditioning_context'), 'protocol.conditioning_context')
    assumptions = _nonempty(protocol.get('assumptions'), 'protocol.assumptions', 2000)
    rows = document.get('feature_mappings')
    if not isinstance(rows, list) or not rows or len(rows) > 4096:
        raise MIContractError('feature_mappings must be a nonempty bounded array')
    allowed = {r['node_id']: r for r in inspection['scenario']['rows']}
    backing = inspection.get('probabilistic_backing') or {}
    backing_nodes = {str(n['id']) for n in backing.get('nodes', []) if isinstance(n, dict) and n.get('id')}
    if not backing_nodes:
        raise MIContractError('Verified concluded probabilistic backing has no observable nodes')
    mapped, seen_sources, seen_targets = [], set(), set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MIContractError(f'feature_mappings[{i}] must be an object')
        src = _nonempty(row.get('source_node_id'), f'feature_mappings[{i}].source_node_id')
        target = _nonempty(row.get('backing_node_id'), f'feature_mappings[{i}].backing_node_id')
        if src not in allowed:
            raise MIContractError(f'{src} is not an explicitly SAT-linked editable MI feature')
        if target not in backing_nodes:
            raise MIContractError(f'{target} is not present in the concluded probabilistic backing')
        if src in seen_sources or target in seen_targets:
            raise MIContractError('Duplicated MI source or probabilistic backing node mapping is ambiguous')
        seen_sources.add(src); seen_targets.add(target)
        transformation = row.get('transformation')
        if not isinstance(transformation, dict) or transformation.get('kind') != 'provider_defined':
            raise MIContractError('A provider_defined transformation is required; PAH never infers it')
        if transformation.get('source_unit') != 'matched_sat_finding_count':
            raise MIContractError('Only explicit matched SAT finding count sources are supported in QI-5')
        event = _nonempty(transformation.get('target_event'), f'{src}.target_event')
        target_unit = _nonempty(transformation.get('target_unit'), f'{src}.target_unit')
        provenance = _nonempty(transformation.get('provenance'), f'{src}.provenance', 2000)
        mapped.append({'source_node_id': src, 'backing_node_id': target,
                       'transformation': {'kind': 'provider_defined',
                                          'source_unit': 'matched_sat_finding_count',
                                          'target_unit': target_unit, 'target_event': event,
                                          'provenance': provenance,
                                          'execution': 'not_performed_by_pah'}})
    return {'schema': SCHEMA, 'schema_version': VERSION,
            'path': str(source.resolve()), 'sha256': sha256(raw).hexdigest(),
            'model_manifest_sha256': inspection['manifest_sha256'],
            'sat_evidence_sha256': evidence['sha256'],
            'signed_network_sha256': inspection['mi_signed_network_sha256'],
            'backing_model_sha256': inspection['mi_backing_model_sha256'],
            'provider': metadata,
            'protocol': {'mode': 'distribution_reestimation',
                         'reference_population': reference_population,
                         'conditioning_context': conditioning,
                         'assumptions': assumptions,
                         'estimator': 'provider_owned_not_executed'},
            'feature_mappings': mapped}


def build_mi_request(inspection: Mapping[str, Any], mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic request snapshot; never compute probability/PMI."""
    if inspection.get('family') != 'mi_informed_pique' or not inspection.get('selected'):
        raise MIContractError('Only a verified concluded MI model can be used')
    scenario = inspection['scenario']
    if mapping['model_manifest_sha256'] != inspection['manifest_sha256'] or mapping['sat_evidence_sha256'] != inspection['evidence']['source']['sha256']:
        raise MIContractError('Adapter belongs to another concluded model or SAT evidence snapshot')
    if mapping['signed_network_sha256'] != inspection['mi_signed_network_sha256'] or mapping['backing_model_sha256'] != inspection['mi_backing_model_sha256']:
        raise MIContractError('MI network/backing version does not match the bound adapter')
    changed = {row['node_id']: row for row in scenario['rows'] if row['changed']}
    by_source = {row['source_node_id']: row for row in mapping['feature_mappings']}
    if not changed:
        raise MIContractError('Make a hypothetical diagnostic change before preparing an MI inference request')
    if not set(changed) <= set(by_source):
        raise MIContractError('All modified MI features require an explicit provider input mapping: '
                              + ', '.join(sorted(set(changed) - set(by_source))))
    inputs = []
    for src in sorted(changed):
        obs, declared = changed[src], by_source[src]
        inputs.append({'source_node_id': src, 'backing_node_id': declared['backing_node_id'],
                       'baseline_observed_count': obs['baseline_value'],
                       'hypothetical_observed_count': obs['scenario_value'],
                       'observation_delta': obs['delta'], 'unit': obs['unit'],
                       'transformation': declared['transformation'],
                       'model_input_value': None,
                       'model_input_status': 'requires_provider_transformation'})
    request = {
        'schema': REQUEST_SCHEMA, 'schema_version': VERSION,
        'status': 'prepared_not_executed',
        'provider': mapping['provider'], 'protocol': mapping['protocol'],
        'network': {'concluded_family': inspection['family'],
                    'concluded_version_id': inspection['version_id'],
                    'manifest_sha256': inspection['manifest_sha256'],
                    'archive_sha256': inspection['archive_sha256'],
                    'signed_information_topology_sha256': inspection['mi_signed_network_sha256'],
                    'learned_probabilistic_backing_sha256': inspection['mi_backing_model_sha256'],
                    'signed_topology_role': 'recorded_reference_not_recomputed',
                    'backing_role': 'learned_probabilistic_model_not_pf_tqi_score'},
        'evidence': {'sha256': mapping['sat_evidence_sha256'],
                     'source_unit': 'matched_sat_finding_count',
                     'kind': 'hypothetical_observation_overlay'},
        'scenario_lineage': {'scenario_id': scenario['scenario_id'],
                             'revision': scenario['revision'],
                             'events': [row for row in scenario['history']],
                             'read_only_sources': True},
        'adapter_sha256': mapping['sha256'], 'inputs': inputs,
        'estimation': {'performed': False, 'results': None,
                       'provider_execution': 'not_connected',
                       'updated_distributions': None, 'updated_signed_information': None,
                       'pf_tqi': None},
        'limitations': [
            'Counts are hypothetical SAT observation counts, not learned-model feature values.',
            'Provider-defined transformations and event definitions require independent scientific validation.',
            'No reference-population reweighting, conditioning, inference or distribution updating has run.',
            'No updated marginals, joints, signed PMI, latent attribution or PF/TQI are available.',
            'Recorded graph reachability is associational, not a causal remediation prediction.',
            'Provider identity is operator-declared, not proof of provider availability or authentication.',
        ],
    }
    canonical = json.dumps(request, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    request['request_sha256'] = sha256(canonical).hexdigest()
    return request
