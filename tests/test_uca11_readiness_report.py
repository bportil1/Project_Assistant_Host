"""Non-destructive readiness aggregation, not a hosted acceptance test."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from uca11_readiness_report import INPUTS, consolidate, _load


class ReadinessReportTests(unittest.TestCase):
    def test_no_evidence_leaves_all_gates_unverified(self):
        report = consolidate({name: None for name in INPUTS})
        self.assertEqual(report["assessment"], "awaiting_installed_hosted_acceptance")
        self.assertTrue(all(v == "unverified" for v in report["acceptance_gates"].values()))
        self.assertEqual(report["legacy_retirement"], "not_authorized")

    def test_static_interfaces_are_not_signoff(self):
        report = consolidate({"baseline": {"schema": INPUTS["baseline"], "interfaces": {"a": True}, "local_tests": {"status": "passed"}},
                              "cross_repository": None, "hosted_layout": None, "source_navigation": None})
        self.assertEqual(report["reports"]["baseline"]["selected_tests"], "passed")
        self.assertEqual(report["production_deployment_signoff"], "not_granted")

    def test_incomplete_cross_repository_blocks(self):
        report = consolidate({"baseline": None, "cross_repository": {"repositories": {"pah": {"status": "present"}}},
                              "hosted_layout": None, "source_navigation": None})
        self.assertEqual(report["assessment"], "blocked_by_observed_failure")

    def test_failed_browser_check_blocks(self):
        report = consolidate({"baseline": None, "cross_repository": None,
                              "hosted_layout": {"result": "failed", "checks": {"editor_unique": "failed"}},
                              "source_navigation": None})
        self.assertEqual(report["assessment"], "blocked_by_observed_failure")

    def test_invalid_schema_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "e.json"
            path.write_text('{"schema":"untrusted"}')
            with self.assertRaises(ValueError):
                _load(path, INPUTS["baseline"])

    def test_symlink_report_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real.json"
            real.write_text(json.dumps({"schema": INPUTS["baseline"]}))
            link = Path(td) / "link.json"
            link.symlink_to(real)
            with self.assertRaises(ValueError):
                _load(link, INPUTS["baseline"])

    def test_cli_creates_new_report_only(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "readiness.json"
            command = [sys.executable, str(ROOT / "scripts/uca11_readiness_report.py"), "--output", str(out)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(out.read_text())["legacy_retirement"], "not_authorized")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
