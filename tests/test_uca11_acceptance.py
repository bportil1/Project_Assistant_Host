"""Read-only UCA-11 acceptance inventory tests."""
import importlib.util
import tempfile
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts/uca11_acceptance.py'
spec = importlib.util.spec_from_file_location('uca11_acceptance', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class AcceptanceInventoryTests(unittest.TestCase):
    def test_missing_contracts_are_not_reported_as_passed(self):
        with tempfile.TemporaryDirectory() as d:
            report = module.inventory(Path(d))
            self.assertTrue(report['missing'])
            self.assertTrue(all(s == 'unverified' for s in report['gates'].values()))

    def test_presence_never_implies_browser_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in module.PAH_CONTRACTS.values():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('dummy', encoding='utf-8')
            report = module.inventory(root)
            self.assertEqual(report['missing'], [])
            self.assertEqual(report['gates']['hosted_flask_routes'], 'unverified')

    def test_symlinked_contract_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            rel=next(iter(module.PAH_CONTRACTS.values()))
            p=root/rel
            p.parent.mkdir(parents=True,exist_ok=True)
            outside=root/'outside'
            outside.write_text('dummy')
            p.symlink_to(outside)
            self.assertFalse(module.safe_file(root, rel))

    def test_missing_test_inputs_are_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            result=module.run_local_tests(Path(d))
            self.assertEqual(result['status'],'unverified')

    def test_reports_do_not_disclose_checkout_paths(self):
        with tempfile.TemporaryDirectory() as d:
            report=module.inventory(Path(d))
            self.assertNotIn(d, repr(report))

if __name__ == '__main__': unittest.main()
