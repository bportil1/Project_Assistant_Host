"""Deterministic offline tests for the four-repository acceptance inventory."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/uca11_cross_repository.py"
spec = importlib.util.spec_from_file_location("uca11_cross_repository", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class CrossRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.roots = {name: root / name for name in runner.CHECKS}
        for name, path in self.roots.items():
            path.mkdir()
            for rel in runner.CHECKS[name].values():
                p = path / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture", encoding="utf-8")

    def test_all_interfaces_present_does_not_pass_manual_gates(self):
        result = runner.assess(self.roots)
        self.assertEqual(result["result"], "interface_ready")
        self.assertEqual(set(result["repositories"]), set(runner.CHECKS))
        self.assertTrue(all(s == "unverified" for s in result["gates"].values()))

    def test_missing_provider_detected(self):
        (self.roots["code_analyzer"] / runner.CHECKS["code_analyzer"]["atlas_provider"]).unlink()
        result = runner.assess(self.roots)
        self.assertEqual(result["result"], "incomplete")
        self.assertFalse(result["repositories"]["code_analyzer"]["interfaces"]["atlas_provider"])

    def test_symlinked_contract_rejected(self):
        target = self.roots["pypique"] / runner.CHECKS["pypique"]["finding_projection"]
        target.unlink()
        target.symlink_to(self.roots["pypique"] / runner.CHECKS["pypique"]["finding_tests"])
        self.assertEqual(runner.assess(self.roots)["result"], "incomplete")

    def test_missing_repository_unverified(self):
        self.roots["cps"] = self.roots["cps"] / "does_not_exist"
        result = runner.assess(self.roots)
        self.assertEqual(result["repositories"]["cps"]["status"], "unverified")

    def test_tests_are_never_started_by_default(self):
        with patch.object(runner, "run_selected", side_effect=AssertionError("unexpected run")):
            result = runner.assess(self.roots)
        self.assertTrue(all(x["selected_tests"]["status"] == "not_run" for x in result["repositories"].values()))

    def test_test_failures_never_claim_ready(self):
        with patch.object(runner, "run_selected", return_value={"status": "failed", "exit_code": 1}):
            result = runner.assess(self.roots, run_tests=True)
        self.assertEqual(result["result"], "incomplete")

    def test_missing_selected_tests_unverified(self):
        (self.roots["pypique"] / runner.TESTS["pypique"][0]).unlink()
        self.assertEqual(runner.run_selected(self.roots["pypique"], runner.TESTS["pypique"])["status"], "unverified")

if __name__ == "__main__":
    unittest.main()
