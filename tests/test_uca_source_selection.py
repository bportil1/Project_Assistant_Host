"""UCA-01 contract tests: pure Python; no Flask, browser or filesystem access."""
import unittest
from pah.contracts.source_selection import (
    SCHEMA, SourceSelection, SourceSelectionCoordinator, SourceSelectionError,
)

SHA = "a" * 64


def payload(**changes):
    value = {"schema": SCHEMA, "workspace_id": "workspace-1", "project_id": "project-1",
             "repository_id": "repo-1", "relative_path": "src/main.py", "source_sha256": SHA,
             "producer": "pypique", "start_line": 4, "end_line": 5}
    value.update(changes)
    return value


class SourceSelectionTests(unittest.TestCase):
    def test_roundtrip_and_optional_spans(self):
        s = SourceSelection.from_mapping(payload(start_column=2, end_column=8,
                                                 artifact_id="finding-17", semantic_node_id="fn:main"))
        self.assertEqual(s, SourceSelection.from_mapping(s.to_dict()))

    def test_rejects_unsafe_paths(self):
        for path in ("../src/a.py", "/tmp/a.py", "src/../a.py", "src//a.py",
                     "src/./a.py", "C:/src/a.py", "src\\a.py", "src/%2e%2e/a.py"):
            with self.subTest(path=path), self.assertRaises(SourceSelectionError):
                SourceSelection.from_mapping(payload(relative_path=path))

    def test_invalid_or_missing_hash_is_not_navigation_evidence(self):
        for sha in (None, "", "A" * 64, "a" * 63):
            with self.subTest(sha=sha), self.assertRaises(SourceSelectionError):
                SourceSelection.from_mapping(payload(source_sha256=sha))

    def test_invalid_spans_and_types(self):
        for variant in ({"start_line": True}, {"start_line": 0}, {"end_line": 2},
                        {"start_column": 1}, {"start_column": 7, "end_column": 3,
                                              "start_line": 4, "end_line": 4}):
            with self.subTest(variant=variant), self.assertRaises(SourceSelectionError):
                SourceSelection.from_mapping(payload(**variant))

    def test_rejects_bad_producer_and_unrecognized_metadata(self):
        for changes in ({"producer": "unknown"}, {"password": "value"}):
            with self.assertRaises(SourceSelectionError):
                SourceSelection.from_mapping(payload(**changes))

    def test_event_dispatched_once_and_not_echoed(self):
        coordinator = SourceSelectionCoordinator("workspace-1", "project-1", "repo-1")
        epoch, _ = coordinator.snapshot()
        event = coordinator.publish(SourceSelection.from_mapping(payload()), expected_epoch=epoch)
        self.assertTrue(coordinator.accepts(event, consumer="editor"))
        self.assertFalse(coordinator.accepts(event, consumer="pypique"))
        self.assertFalse(coordinator.accepts(event, consumer="editor", last_event_id=event.event_id))
        self.assertEqual(event.sequence, 1)
        self.assertEqual(event.to_dict()["selection"]["source_sha256"], SHA)

    def test_cross_project_rejected(self):
        coordinator = SourceSelectionCoordinator("workspace-1", "project-1", "repo-1")
        for changes in ({"project_id": "project-2"}, {"repository_id": "repo-2"},
                        {"workspace_id": "workspace-2"}):
            with self.assertRaises(SourceSelectionError):
                coordinator.publish(SourceSelection.from_mapping(payload(**changes)), expected_epoch=0)

    def test_switch_clears_and_rejects_old_epoch(self):
        coordinator = SourceSelectionCoordinator("workspace-1", "project-1", "repo-1")
        event = coordinator.publish(SourceSelection.from_mapping(payload()), expected_epoch=0)
        self.assertEqual(coordinator.switch_scope("workspace-1", "project-2", "repo-2"), 1)
        self.assertEqual(coordinator.snapshot(), (1, None))
        self.assertFalse(coordinator.accepts(event, consumer="editor"))
        with self.assertRaises(SourceSelectionError):
            coordinator.publish(SourceSelection.from_mapping(payload()), expected_epoch=0)
        new = SourceSelection.from_mapping(payload(project_id="project-2", repository_id="repo-2"))
        self.assertEqual(coordinator.publish(new, expected_epoch=1).sequence, 1)

    def test_same_scope_retains_current_selection(self):
        coordinator = SourceSelectionCoordinator("workspace-1", "project-1", "repo-1")
        event = coordinator.publish(SourceSelection.from_mapping(payload()), expected_epoch=0)
        self.assertEqual(coordinator.switch_scope("workspace-1", "project-1", "repo-1"), 0)
        self.assertIs(coordinator.snapshot()[1], event)

    def test_stale_events_cannot_replace_recent_events(self):
        coordinator = SourceSelectionCoordinator("workspace-1", "project-1", "repo-1")
        first = coordinator.publish(SourceSelection.from_mapping(payload()), expected_epoch=0)
        second = coordinator.publish(SourceSelection.from_mapping(payload(start_line=6, end_line=7)), expected_epoch=0)
        self.assertFalse(coordinator.accepts(first, consumer="editor"))
        self.assertTrue(coordinator.accepts(second, consumer="editor"))
        self.assertEqual(second.sequence, 2)


if __name__ == "__main__":
    unittest.main()
