"""QI-4: read-only comparisons of observations and authentic Standard model outputs.

Recorded graph reachability is an explanation of *possible* propagation through
configured links; it is neither a causal claim nor proof that a value changed.
MI evidence scenarios never trigger a population information update here.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


class ComparisonError(ValueError):
    """An in-memory comparison or export violates revision/source constraints."""


KINDS = ('diagnostic', 'measure', 'product_factor', 'quality_aspect', 'tqi')


def _numeric_delta(left: Any, right: Any) -> float | None:
    if (isinstance(left, bool) or isinstance(right, bool)
            or not isinstance(left, (float, int)) or not isinstance(right, (float, int))):
        return None
    delta = float(right) - float(left)
    return delta if math.isfinite(delta) else None


def observed_rows(reference: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict]:
    """Compare only matching explicitly observed input nodes; never invent zeroes."""
    originals = {row['node_id']: row for row in reference['rows']}
    latest = {row['node_id']: row for row in current['rows']}
    if originals.keys() != latest.keys():
        raise ComparisonError('Scenario inputs differ; comparisons require identical evidence and model')
    rows = []
    for identifier in sorted(originals):
        before, after = originals[identifier], latest[identifier]
        if before['unit'] != after['unit'] or before['evidence_sha256'] != after['evidence_sha256']:
            raise ComparisonError('Scenario observation units or evidence fingerprints differ')
        rows.append({'node_id': identifier, 'kind': before['node_kind'],
                     'baseline': before['scenario_value'], 'scenario': after['scenario_value'],
                     'delta': after['scenario_value'] - before['scenario_value'],
                     'unit': before['unit'], 'origin': 'hypothetical_observation_comparison',
                     'diagnostic_ids': before['diagnostic_ids'], 'measure_ids': before['measure_ids']})
    return rows


def native_rows(reference_forward: Mapping[str, Any] | None,
                current_forward: Mapping[str, Any] | None) -> tuple[list[dict], str]:
    """Allow native numeric deltas only for two successfully evaluated states."""
    before = (reference_forward or {}).get('scenario')
    after = (current_forward or {}).get('scenario')
    if ((reference_forward or {}).get('status') != 'ready'
            or (current_forward or {}).get('status') != 'ready' or not before or not after):
        return [], 'Native deltas unavailable: one or both states lack completed native Standard evaluation'
    if (reference_forward.get('mapping_sha256') != current_forward.get('mapping_sha256')
            or reference_forward.get('manifest_sha256') != current_forward.get('manifest_sha256')
            or reference_forward.get('evidence_sha256') != current_forward.get('evidence_sha256')):
        return [], 'Native deltas unavailable: mapping, concluded model, or evidence fingerprints differ'
    rows = []
    left = before['node_values']
    right = after['node_values']
    for kind in KINDS:
        baseline = left.get(kind) or {}
        scenario = right.get(kind) or {}
        for identifier in sorted(set(baseline) | set(scenario)):
            old, new = baseline.get(identifier), scenario.get(identifier)
            rows.append({'kind': kind, 'node_id': identifier, 'baseline': old, 'scenario': new,
                         'delta': _numeric_delta(old, new), 'unit': 'native_quality_model_value',
                         'origin': 'concluded_native_evaluator'})
    return rows, 'Only authentic concluded Standard PIQUE native values; Δ is scenario minus comparison reference'


def reachable_paths(network: Mapping[str, Any], roots: list[str],
                    evaluated_native_rows: list[dict], *, family: str) -> dict:
    """Highlight *only recorded directed edges*, without fabricating missing links."""
    nodes = {str(node['id']) for node in network['nodes']}
    valid_roots = sorted(set(roots) & nodes)
    adjacency: dict[str, list[tuple[int, str]]] = {}
    for index, edge in enumerate(network['edges']):
        src, dest = str(edge.get('source')), str(edge.get('target'))
        if src in nodes and dest in nodes:
            adjacency.setdefault(src, []).append((index, dest))
    reached = set(valid_roots)
    traversed_edges: set[int] = set()
    pending = list(valid_roots)
    # Reachability is bounded by the number of nodes even in cyclic graphs.
    while pending:
        source = pending.pop(0)
        for index, dest in adjacency.get(source, ()):
            traversed_edges.add(index)
            if dest not in reached:
                reached.add(dest)
                pending.append(dest)
    measured = sorted({row['node_id'] for row in evaluated_native_rows
                       if row['delta'] is not None and row['delta'] != 0})
    return {'source_nodes': valid_roots, 'reachable_nodes': sorted(reached),
            'recorded_edge_indices': sorted(traversed_edges),
            'native_changed_nodes': measured,
            'relationship': ('candidate_native_evaluation_paths' if family == 'standard_pique'
                             else 'recorded_information_topology_context_only'),
            'meaning': ('Directed reachability through recorded graph links, not causal attribution. '
                        'Native changed nodes indicate actual evaluated value differences only. '
                        'MI scenarios do not recompute learned probabilities or information shares.')}


def build_comparison(inspection: Mapping[str, Any], *, reference_scenario: Mapping[str, Any],
                     current_scenario: Mapping[str, Any],
                     reference_forward: Mapping[str, Any] | None,
                     current_forward: Mapping[str, Any] | None,
                     reference_label: str, reference_id: str) -> dict:
    for key in ('scenario_id', 'model_version_id', 'manifest_sha256', 'archive_sha256', 'evidence_sha256'):
        if reference_scenario.get(key) != current_scenario.get(key):
            raise ComparisonError(f'Cannot compare unrelated scenarios: {key} differs')
    observed = observed_rows(reference_scenario, current_scenario)
    native, native_note = native_rows(reference_forward, current_forward)
    changed = [r['node_id'] for r in observed if r['delta'] != 0]
    paths = reachable_paths(inspection['network'], changed, native, family=inspection['family'])
    return {'schema': 'pah.quality_impact_comparison', 'schema_version': 1,
            'status': 'native_ready' if native else 'observation_only',
            'reference_id': reference_id, 'reference_label': reference_label,
            'reference_revision': reference_scenario['revision'],
            'scenario_revision': current_scenario['revision'],
            'scenario_id': current_scenario['scenario_id'],
            'model_version_id': inspection['version_id'],
            'family': inspection['family'],
            'model_manifest_sha256': inspection['manifest_sha256'],
            'evidence_sha256': (inspection['evidence']['source'] or {}).get('sha256'),
            'native_mapping_sha256': ((current_forward or {}).get('mapping_sha256') if native else None),
            'observations': observed, 'native_values': native,
            'network_highlights': paths, 'native_note': native_note,
            'disclaimer': 'Observed counts are SAT records. Native values require explicit conversion and native model evaluation; MI remains read-only.'}
