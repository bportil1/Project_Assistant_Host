"""UCA-00 offline inventory contract tests (no module dependencies)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "uca_baseline.py"
spec = importlib.util.spec_from_file_location("uca_baseline", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UCABaselineTests(unittest.TestCase):
    def test_missing_checkouts_are_not_passed(self):
        with tempfile.TemporaryDirectory() as base:
            roots = {name: Path(base) / name for name in module.CHECKS}
            result = module.inspect_repositories(roots)
            self.assertFalse(result["all_required_present"])
            self.assertEqual(result["repositories"]["pah"]["status"], "missing_checkout")
            self.assertTrue(all(v == "unverified" for v in result["acceptance"].values()))

    def test_fake_roots_only_establish_presence(self):
        with tempfile.TemporaryDirectory() as base:
            roots = {name: Path(base) / name for name in module.CHECKS}
            for name, requirements in module.CHECKS.items():
                for path in requirements.values():
                    f = roots[name] / path
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("placeholder", encoding="utf-8")
            report = module.inspect_repositories(roots)
            self.assertTrue(report["all_required_present"])
            self.assertEqual(report["acceptance"]["flask_browser"], "unverified")

    def test_symlinked_interface_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base) / "pah"
            rel = next(iter(module.CHECKS["pah"].values()))
            f = root / rel
            f.parent.mkdir(parents=True)
            target = Path(base) / "outside.py"
            target.write_text("x", encoding="utf-8")
            f.symlink_to(target)
            status = module._inspect(root, module.CHECKS["pah"], {})
            self.assertEqual(status["status"], "incomplete")

    def test_report_does_not_include_absolute_paths_or_source(self):
        with tempfile.TemporaryDirectory() as base:
            roots = {name: Path(base) / name for name in module.CHECKS}
            rendered = repr(module.inspect_repositories(roots))
            self.assertNotIn(base, rendered)


if __name__ == "__main__":
    unittest.main()
