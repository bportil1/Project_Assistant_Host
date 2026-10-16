"""QI-2: temporary diagnostic evidence scenarios, not model evaluation.

Only explicitly linked SAT observations are editable. Values are *counts of
linked SAT records*, not claims about model-native input domains or scores.
No disk writes, learning, prediction, or source-code alteration occurs here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


class ScenarioError(ValueError):
    """A scenario edit violates evidence, lineage, or revision constraints."""


MAX_EVENTS = 500
MAX_OBSERVED_COUNT = 1_000_000_000
UNITS = 'matched_sat_finding_count'


def editable_observations(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Derive explicitly matched *observed* counts from the inspected evidence.

    The absence of a matching SAT record is *not* asserted to mean a count
    of zero, because the findings source might cover only some diagnostics.
    """
    evidence = snapshot['evidence']
    if not evidence.get('source'):
        return {}
    nodes = snapshot['network']['nodes']
    edges = snapshot['network']['edges']
    family = snapshot['family']
    measures = {str(n['id']) for n in nodes if n.get('kind') == 'measure'}
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        identifier = node.get('id')
        kind = node.get('kind')
        if not isinstance(identifier, str) or not identifier:
            continue
        # Only the input layer, never product factors, latent states or TQI.
        if family == 'standard_pique' and kind != 'diagnostic':
            continue
        if family == 'mi_informed_pique' and kind not in ('cwe', 'feature'):
            continue
        findings = evidence['linked'].get(identifier) or []
        if not findings:
            continue
        diagnostic_ids = sorted({str(f['diagnostic_id']) for f in findings if f.get('diagnostic_id')})
        measure_ids = sorted({str(edge['target']) for edge in edges
                              if edge.get('source') == identifier and edge.get('target') in measures})
        # No guessed conversion from a CWE/feature into a model-native variable.
        result[identifier] = {
            'node_id': identifier, 'node_kind': kind,
            'baseline_value': len(findings), 'unit': UNITS,
            'diagnostic_ids': diagnostic_ids, 'measure_ids': measure_ids,
            'mapping': 'explicit_recorded_identifiers_only',
            'model_input_compatible': False,
            'evidence_sha256': evidence['source']['sha256'],
            'evidence_path': evidence['source']['path'],
            'provenance': 'count_of_explicitly_matched_sat_records',
        }
    return result


def _at() -> str:
    return datetime.now(timezone.utc).isoformat()


class DiagnosticScenario:
    """One workspace/model/evidence-scoped reversible, in-memory overlay."""

    def __init__(self, inspection: Mapping[str, Any]) -> None:
        self.scenario_id = str(uuid4())
        self.version_id = str(inspection['version_id'])
        self.family = str(inspection['family'])
        self.manifest_sha256 = str(inspection['manifest_sha256'])
        self.archive_sha256 = str(inspection['archive_sha256'])
        self.evidence_sha256 = str((inspection['evidence'].get('source') or {}).get('sha256') or '')
        self.observations = editable_observations(inspection)
        self.revision = 0
        self.overrides: dict[str, int] = {}
        self.undo_stack: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.created_at = _at()

    def matches(self, inspection: Mapping[str, Any]) -> bool:
        source = inspection['evidence'].get('source') or {}
        return (str(inspection['version_id']) == self.version_id
                and inspection['family'] == self.family
                and inspection['manifest_sha256'] == self.manifest_sha256
                and inspection['archive_sha256'] == self.archive_sha256
                and (source.get('sha256') or '') == self.evidence_sha256)

    def _revision(self, expected_revision: Any) -> None:
        if (isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
                or expected_revision != self.revision):
            raise ScenarioError('Scenario revision is missing or stale; refresh before editing')

    def _record(self, action: str, *, node_id: str | None = None,
                old: int | None = None, new: int | None = None) -> None:
        self.revision += 1
        self.events.append({'revision': self.revision, 'action': action, 'node_id': node_id,
                            'old_value': old, 'new_value': new, 'unit': UNITS,
                            'recorded_at': _at(), 'origin': 'hypothetical_user_edit',
                            'scenario_id': self.scenario_id,
                            'model_manifest_sha256': self.manifest_sha256,
                            'sat_evidence_sha256': self.evidence_sha256})

    def set_value(self, node_id: Any, value: Any, *, expected_revision: Any) -> None:
        self._revision(expected_revision)
        if not isinstance(node_id, str) or node_id not in self.observations:
            raise ScenarioError('Select an explicitly SAT-linked diagnostic/CWE input node')
        if (isinstance(value, bool) or not isinstance(value, int)
                or not 0 <= value <= MAX_OBSERVED_COUNT):
            raise ScenarioError('Scenario SAT finding counts must be nonnegative integers')
        old = self.overrides.get(node_id, self.observations[node_id]['baseline_value'])
        if old == value:
            raise ScenarioError('No change to the observed count; scenario was not modified')
        if len(self.events) >= MAX_EVENTS:
            raise ScenarioError('Scenario event capacity reached; reset to start a fresh scenario')
        self.undo_stack.append({'node_id': node_id, 'old_value': old, 'new_value': value})
        baseline = self.observations[node_id]['baseline_value']
        if value == baseline:
            self.overrides.pop(node_id, None)
        else:
            self.overrides[node_id] = value
        self._record('set', node_id=node_id, old=old, new=value)

    def undo(self, *, expected_revision: Any) -> None:
        self._revision(expected_revision)
        if not self.undo_stack:
            raise ScenarioError('There is no scenario edit to undo')
        if len(self.events) >= MAX_EVENTS:
            raise ScenarioError('Scenario event capacity reached; reset to start a fresh scenario')
        last = self.undo_stack.pop()
        node_id, previous = last['node_id'], last['old_value']
        current = self.overrides.get(node_id, self.observations[node_id]['baseline_value'])
        if previous == self.observations[node_id]['baseline_value']:
            self.overrides.pop(node_id, None)
        else:
            self.overrides[node_id] = previous
        self._record('undo', node_id=node_id, old=current, new=previous)

    def reset(self, *, expected_revision: Any) -> None:
        self._revision(expected_revision)
        # Reset is always available even at the audit capacity ceiling.
        # Record which hypothetical counts were discarded. A reset clears the
        # undo stack but retains audit history within the bounded session.
        cleared = [
            {'node_id': node_id, 'old_value': value,
             'new_value': self.observations[node_id]['baseline_value']}
            for node_id, value in sorted(self.overrides.items())
        ]
        self.overrides.clear()
        self.undo_stack.clear()
        if len(self.events) >= MAX_EVENTS:
            # A capped, in-memory audit cannot grow without bound. Explicit
            # reset starts a new trail and discloses that earlier events expired.
            self.events.clear()
            self._record('reset')
            self.events[-1]['prior_events_expired'] = True
        else:
            self._record('reset')
        self.events[-1]['discarded_overrides'] = cleared

    def to_dict(self) -> dict[str, Any]:
        rows = []
        for identifier, source in self.observations.items():
            row = deepcopy(source)
            row['scenario_value'] = self.overrides.get(identifier, source['baseline_value'])
            row['delta'] = row['scenario_value'] - source['baseline_value']
            row['changed'] = identifier in self.overrides
            rows.append(row)
        return {
            'schema': 'pah.quality_impact_diagnostic_scenario', 'schema_version': 1,
            'scenario_id': self.scenario_id, 'revision': self.revision,
            'model_version_id': self.version_id, 'model_family': self.family,
            'manifest_sha256': self.manifest_sha256,
            'archive_sha256': self.archive_sha256,
            'evidence_sha256': self.evidence_sha256,
            'created_at': self.created_at, 'rows': rows,
            'changed_count': len(self.overrides), 'undo_available': bool(self.undo_stack),
            'history': deepcopy(self.events),
            'read_only_sources': True, 'evaluation_performed': False,
            'units': UNITS,
            'warning': ('A hypothetical change to matched SAT record counts, NOT a computed model-native input, '
                        'quality score, causal intervention or prediction. QI-3 will define authentic forward evaluation.'),
        }
