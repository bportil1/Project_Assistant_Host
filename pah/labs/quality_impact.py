"""QI-1: read-only concluded-model inspection for Code Analysis Lab.

pyPIQUE owns verification and model construction. PAH consumes its explicit
handoff, never reads module-private stores, reevaluates a model, or edits SAT
findings. The selected paths live in memory per workspace, not in artifacts.
"""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping
from threading import RLock

from .quality_impact_scenarios import DiagnosticScenario, ScenarioError
from .quality_impact_forward import (ForwardEvaluationError, read_native_mapping, forward_result)


class QualityImpactError(ValueError):
    """A selected finalized package or evidence document cannot be inspected."""


def _verified_reader() -> Callable[[str | Path], dict]:
    try:
        from pique_py.finalized_model_registry import read_conclusion
    except ImportError as exc:
        # A PAH checkout can contain pyPIQUE as a local, uninstalled submodule.
        # Never fetch dependencies or search arbitrary filesystem locations.
        checkout = Path(__file__).resolve().parents[2] / 'modules' / 'pypique' / 'src'
        if not (checkout / 'pique_py' / 'finalized_model_registry.py').is_file():
            raise QualityImpactError(
                'pyPIQUE finalized-model verifier is not installed; enable the local pyPIQUE module or install it in the PAH environment.'
            ) from exc
        if str(checkout) not in sys.path:
            sys.path.insert(0, str(checkout))
        try:
            from pique_py.finalized_model_registry import read_conclusion
        except ImportError as missing:
            raise QualityImpactError(f'Local pyPIQUE verifier is unavailable: {missing}') from missing
    return read_conclusion


def _standard_network(document: Mapping[str, Any]) -> dict[str, Any]:
    """Copy explicit native graph edges, including recorded child ordering/weights.

    No implicit full connectivity is permitted: MF-5 validation loads the same
    concluded native configuration using implicit_full_connect=False.
    """
    factors = document['factors']
    layers = (
        ('diagnostic', document.get('diagnostics') or {}),
        ('measure', document.get('measures') or {}),
        ('product_factor', factors.get('product_factors') or {}),
        ('quality_aspect', factors.get('quality_aspects') or {}),
        ('tqi', factors['tqi']),
    )
    nodes, edges = [], []
    for kind, records in layers:
        for identifier, spec in records.items():
            nodes.append({'id': identifier, 'kind': kind, 'definition': spec})
            children = spec.get('children')
            weights = spec.get('weights') or {}
            if children is None:
                children = {name: {} for name in weights}
            for child, child_spec in children.items():
                edge = {'source': child, 'target': identifier, 'relationship': 'native_quality_model_child'}
                if child in weights:
                    edge['weight'] = weights[child]
                if isinstance(child_spec, dict) and child_spec:
                    edge['child_configuration'] = child_spec
                edges.append(edge)
    return {'role': 'native_standard_quality_model', 'nodes': nodes, 'edges': edges,
            'semantics': 'Exact configured parent-child graph; not a result of evaluation or a causal graph'}


def _recorded_network(document: Mapping[str, Any], *, role: str, edge_key: str) -> dict[str, Any]:
    return {'role': role, 'nodes': list(document.get('nodes') or []),
            'edges': list(document.get(edge_key) or []),
            'semantics': ('Original signed information relationships; not inferred causal links' if role == 'signed_information_topology'
                          else 'Separate learned probabilistic backing; not a PF/TQI scoring model')}


def _normalize_cwe(value: Any) -> str | None:
    """Convert an explicitly typed CWE field; no heuristic rule matching."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    name = str(value).strip()
    if name.isdecimal():
        return f'CWE-{int(name)}'
    if name.upper().startswith('CWE-') and name[4:].isdecimal():
        return f'CWE-{int(name[4:])}'
    return None


def _evidence_ids(row: Mapping[str, Any]) -> list[str]:
    # One SAT finding can explicitly carry multiple CWE IDs. Preserve all of
    # those mappings, with one evidence record linked to each listed CWE.
    explicit = row.get('diagnostic_id', row.get('diagnostic'))
    if isinstance(explicit, str) and explicit.strip():
        return [explicit.strip()]
    cwes = row.get('cwes')
    if isinstance(cwes, list):
        return sorted({_normalize_cwe(cwe) for cwe in cwes} - {None})
    for key in ('cwe', 'cwe_id'):
        if key in row:
            normalized = _normalize_cwe(row.get(key))
            if normalized:
                return [normalized]
    return []


def _finding(row: Mapping[str, Any], identifier: str) -> dict[str, Any]:
    location = row.get('location') if isinstance(row.get('location'), dict) else {}
    result = {'diagnostic_id': identifier}
    for source, target in (('file_path', 'file_path'), ('file', 'file_path'),
                           ('path', 'file_path'), ('line', 'line'), ('line_number', 'line'),
                           ('character', 'column'), ('column', 'column'),
                           ('message', 'message'), ('severity', 'severity'),
                           ('provider', 'provider'), ('tool', 'provider')):
        value = row.get(source, location.get(source))
        if target not in result and isinstance(value, (str, int, float)) and not isinstance(value, bool):
            result[target] = value
    return result


def _read_evidence(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != '.json':
        raise QualityImpactError('Select a local JSON SAT findings document (not a symbolic link)')
    if source.stat().st_size > 24 * 1024 * 1024:
        raise QualityImpactError('SAT findings JSON exceeds the 24 MiB inspection limit')
    raw = source.read_bytes()
    try:
        document = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError) as exc:
        raise QualityImpactError(f'Invalid SAT evidence JSON: {exc}') from exc
    if not isinstance(document, dict):
        raise QualityImpactError('SAT findings must be a JSON object')
    findings = []
    if isinstance(document.get('diagnostics'), dict):
        for identifier, rows in document['diagnostics'].items():
            if not isinstance(rows, list):
                raise QualityImpactError('SAT diagnostics map contains a non-list observation')
            for row in rows:
                if not isinstance(row, dict):
                    raise QualityImpactError('SAT diagnostic observation must be an object')
                findings.append(_finding(row, str(identifier)))
    elif isinstance(document.get('findings'), list):
        for row in document['findings']:
            if not isinstance(row, dict):
                raise QualityImpactError('SAT finding must be an object')
            identifiers = _evidence_ids(row)
            for identifier in identifiers:
                findings.append(_finding(row, identifier))
            if not identifiers:
                findings.append(_finding(row, 'unmapped') | {'diagnostic_id': None, 'unmapped': True})
    else:
        raise QualityImpactError('SAT findings must contain a diagnostics map or findings array')
    return {'path': str(source.resolve()), 'sha256': sha256(raw).hexdigest(), 'findings': findings}


def _link_evidence(network: Mapping[str, Any], evidence: dict | None) -> dict:
    nodes = network['nodes']
    aliases: dict[str, set[str]] = {}
    for node in nodes:
        identifier = str(node.get('id') or '')
        if not identifier:
            continue
        # Native Standard graph uses diagnostic nodes, MI graph uses recorded
        # CWE/feature nodes; linked identifiers must be explicit in artifacts.
        if node.get('kind') == 'diagnostic':
            aliases.setdefault(identifier, set()).add(identifier)
        elif str(node.get('kind') or '').lower() in {'cwe', 'feature', 'measure'}:
            for name in (node.get('cwe_id'), node.get('feature_id'), identifier if node.get('kind') == 'cwe' else None):
                if isinstance(name, str) and name:
                    aliases.setdefault(name, set()).add(identifier)
    linked: dict[str, list[dict]] = {}
    unmatched: list[dict] = []
    for finding in evidence['findings'] if evidence else []:
        ids = aliases.get(finding.get('diagnostic_id'), set())
        if not ids:
            unmatched.append(finding)
        for identifier in ids:
            linked.setdefault(identifier, []).append(finding)
    return {'source': ({'path': evidence['path'], 'sha256': evidence['sha256'],
                         'observation_count': len(evidence['findings'])} if evidence else None),
            'linked': linked, 'unmatched': unmatched, 'linked_observations': sum(len(rows) for rows in linked.values()),
            'note': ('Explicit native diagnostic/CWE matches only; location paths are display-only and not checked against the current repository. '
                     'Unmatched findings are retained, not reclassified. No evidence has been changed.')}


class QualityImpactInspector:
    """Workspace-scoped, verified model view with separate hypothetical overlays."""

    def __init__(self, reader: Callable | None = None, summarizer: Callable | None = None,
                 native_loader: Callable | None = None) -> None:
        self._reader = reader
        self._summarizer = summarizer
        self._native_loader = native_loader
        self._selections: dict[str, dict[str, Any]] = {}
        self._scenarios: dict[str, DiagnosticScenario] = {}
        self._native_mappings: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def select(self, workspace: str, path: str, findings_path: str | None = None) -> dict:
        if not isinstance(path, str) or not path.strip():
            raise QualityImpactError('A concluded model directory or ZIP must be selected')
        if findings_path is not None and not isinstance(findings_path, str):
            raise QualityImpactError('SAT findings path must be a string')
        # Verify all sources before replacing anything, including the scenario.
        result = self._inspect(path, findings_path or None)
        with self._lock:
            self._selections[workspace] = {
                'path': str(Path(path).expanduser().resolve()),
                'findings_path': str(Path(findings_path).expanduser().resolve()) if findings_path else None,
                'version_id': result['version_id'],
                'archive_sha256': result['archive_sha256'],
                'manifest_sha256': result['manifest_sha256'],
                'evidence_sha256': (result['evidence']['source'] or {}).get('sha256'),
            }
            self._scenarios.pop(workspace, None)
            self._native_mappings.pop(workspace, None)
            return self._attach_scenario(workspace, result)

    def clear(self, workspace: str) -> None:
        with self._lock:
            self._selections.pop(workspace, None)
            self._scenarios.pop(workspace, None)
            self._native_mappings.pop(workspace, None)

    def _attach_scenario(self, workspace: str, result: dict) -> dict:
        scenario = self._scenarios.get(workspace)
        if scenario is None or not scenario.matches(result):
            scenario = DiagnosticScenario(result)
            self._scenarios[workspace] = scenario
        result['scenarios_enabled'] = bool(scenario.observations)
        result['scenario'] = scenario.to_dict()
        result['forward_evaluation'] = self._forward_snapshot(workspace, result)
        return result

    def bind_native_inputs(self, workspace: str, path: Any) -> dict:
        """Attach explicitly sourced native diagnostic inputs without editing QI-2 state."""
        if not isinstance(path, str) or not path.strip():
            raise ForwardEvaluationError('A local native input mapping JSON path is required')
        with self._lock:
            snapshot = self.snapshot(workspace)
            if not snapshot.get('selected'):
                raise ForwardEvaluationError('Select and verify a Standard model with SAT evidence first')
            mapping = read_native_mapping(path, snapshot)
            # The validated mapping belongs to one immutable model/evidence pair.
            self._native_mappings[workspace] = mapping
            return self._attach_scenario(workspace, snapshot)

    def clear_native_inputs(self, workspace: str) -> dict:
        with self._lock:
            self._native_mappings.pop(workspace, None)
            return self.snapshot(workspace)

    def _forward_snapshot(self, workspace: str, result: dict) -> dict:
        status = {'schema': 'pah.standard_forward_evaluation', 'schema_version': 1}
        if result.get('family') != 'standard_pique':
            return {**status, 'status': 'not_applicable',
                    'reason': 'MI requires its separate distribution/inference protocol, not native Standard forward evaluation'}
        mapping = self._native_mappings.get(workspace)
        if mapping is None:
            return {**status, 'status': 'needs_mapping',
                    'reason': 'Bind a complete native diagnostic mapping for this model and SAT evidence; counts alone cannot be evaluated'}
        try:
            current = read_native_mapping(mapping['path'], result)
            if current['sha256'] != mapping['sha256']:
                raise ForwardEvaluationError('Bound native mapping JSON changed on disk')
            return forward_result(result, result['scenario'], mapping, loader=self._native_loader)
        except (ForwardEvaluationError, OSError, ImportError, ValueError, TypeError, KeyError) as exc:
            # Do not invalidate a valid QI-2 hypothetical edit just because its
            # optional QI-3 native input mapping was changed or became unreadable.
            self._native_mappings.pop(workspace, None)
            return {**status, 'status': 'blocked', 'reason': str(exc),
                    'native_mapping_invalidated': True}

    def snapshot(self, workspace: str) -> dict:
        with self._lock:
            selected = self._selections.get(workspace)
            if selected is None:
                return {'schema': 'pah.quality_impact_inspection', 'schema_version': 1, 'selected': False,
                        'read_only': True, 'scenarios_enabled': False}
            try:
                result = self._inspect(selected['path'], selected['findings_path'])
                for key in ('version_id', 'archive_sha256', 'manifest_sha256'):
                    if result[key] != selected[key]:
                        raise QualityImpactError(f'The selected concluded package changed its {key}')
                if (result['evidence']['source'] or {}).get('sha256') != selected['evidence_sha256']:
                    raise QualityImpactError('The selected SAT findings changed on disk')
                return self._attach_scenario(workspace, result)
            except (QualityImpactError, OSError, ValueError) as exc:
                # A changed source clears the selection AND the hypothetical edits.
                self.clear(workspace)
                return {'schema': 'pah.quality_impact_inspection', 'schema_version': 1, 'selected': False,
                        'read_only': True, 'scenarios_enabled': False,
                        'diagnostic': f'Selected model or evidence no longer verifies: {exc}'}

    def scenario_action(self, workspace: str, action: Any, *, node_id: Any = None,
                        value: Any = None, expected_revision: Any = None) -> dict:
        if action not in ('set', 'undo', 'reset'):
            raise ScenarioError('Action must be set, undo, or reset')
        with self._lock:
            snapshot = self.snapshot(workspace)
            if not snapshot['selected']:
                raise ScenarioError('A verified finalized model and SAT evidence must be selected')
            scenario = self._scenarios[workspace]
            if not scenario.observations:
                raise ScenarioError('No explicitly SAT-linked input observations are available for editing')
            if action == 'set':
                scenario.set_value(node_id, value, expected_revision=expected_revision)
            elif action == 'undo':
                scenario.undo(expected_revision=expected_revision)
            else:
                scenario.reset(expected_revision=expected_revision)
            return self._attach_scenario(workspace, snapshot)

    def _inspect(self, path: str, findings_path: str | None) -> dict:
        try:
            concluded = (self._reader or _verified_reader())(path)
            if self._summarizer is None:
                from pique_py.finalized_model_registry import conclusion_summary
                summary = conclusion_summary(concluded)
            else:
                summary = self._summarizer(concluded)
        except (OSError, ImportError, ValueError, KeyError, TypeError) as exc:
            raise QualityImpactError(f'Concluded model verification failed: {exc}') from exc
        family = concluded['family']
        docs = concluded['documents']
        if family == 'standard_pique':
            network = _standard_network(docs['model.json'])
            backing = None
        elif family == 'mi_informed_pique':
            network = _recorded_network(docs['signed_information_topology.json'],
                                        role='signed_information_topology', edge_key='edges')
            backing = _recorded_network(docs['probabilistic_model.json'],
                                        role='learned_probabilistic_backing', edge_key='relationships')
        else:
            raise QualityImpactError('Unsupported concluded model family')
        evidence = _read_evidence(findings_path) if findings_path else None
        return {'schema': 'pah.quality_impact_inspection', 'schema_version': 1,
                'selected': True, 'read_only': True, 'scenarios_enabled': False,
                'family': family, 'version_id': concluded['version_id'],
                'model_path': str(Path(path).expanduser().resolve()),
                'archive_sha256': concluded['archive_sha256'],
                'manifest_sha256': concluded['manifest_sha256'],
                'choice': concluded['manifest']['choice'],
                'network': network, 'probabilistic_backing': backing,
                'evidence': _link_evidence(network, evidence),
                'acceptance': summary['comparison'],
                'notice': 'The concluded network and historical acceptance remain immutable. QI-2 SAT count scenarios are separate from QI-3 native Standard evaluation, which requires an explicit mapping. No MI inference, causal claims or source modifications.'}
