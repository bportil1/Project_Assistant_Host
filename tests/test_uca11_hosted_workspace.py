"""Deterministic, network-free checks for UCA-11's optional local browser runner."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'scripts/uca11_hosted_workspace.py'
spec = importlib.util.spec_from_file_location('uca11_hosted_workspace', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HostedAcceptanceTests(unittest.TestCase):
    def test_all_seven_nonempty_pane_combinations(self):
        combos = module.combinations()
        self.assertEqual(len(combos), 7)
        self.assertEqual(len(set(combos)), 7)
        self.assertIn(('editor', 'pypique', 'analyzer'), combos)

    def test_numeric_loopback_only(self):
        for url in ('http://127.0.0.1:5000/', 'http://[::1]:8080/'):
            self.assertEqual(module.validate_loopback_url(url), url)
        for url in ('https://127.0.0.1:5000/', 'http://localhost:5000/',
                    'http://192.168.1.2:5000/', 'http://8.8.8.8:5000/',
                    'http://user:pass@127.0.0.1:5000/',
                    'http://127.0.0.1:5000/?token=private',
                    'http://127.0.0.1:5000/redirect', 'http://127.0.0.1/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                module.validate_loopback_url(url)

    def test_default_never_launches_browser(self):
        with patch.object(module, 'run_browser', side_effect=AssertionError('called')):
            r = module.assess('http://127.0.0.1:5000/')
        self.assertEqual(r['result'], 'not_run')
        self.assertTrue(all(v == 'unverified' for v in r['gates'].values()))

    def test_success_cannot_pass_scientific_or_provenance_gates(self):
        with patch.object(module, 'run_browser', return_value={'uca_mode': 'passed'}):
            r = module.assess('http://127.0.0.1:5000/', execute=True)
        self.assertEqual(r['result'], 'smoke_passed')
        self.assertEqual(r['gates']['scientific_parity'], 'unverified')
        self.assertEqual(r['gates']['job_artifact_provenance'], 'unverified')

    def test_failure_or_missing_browser_is_not_success(self):
        with patch.object(module, 'run_browser', return_value={'editor_restore': 'failed'}):
            self.assertEqual(module.assess('http://127.0.0.1:5000/', execute=True)['result'], 'failed')
        with patch.object(module, 'run_browser', side_effect=ImportError('playwright')):
            self.assertEqual(module.assess('http://127.0.0.1:5000/', execute=True)['result'], 'unverified')

    def test_output_is_create_only(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'report.json'
            self.assertEqual(module.main(['--url', 'http://127.0.0.1:5000/', '--output', str(out)]), 0)
            self.assertTrue(out.exists())
            with self.assertRaises(FileExistsError):
                module.main(['--url', 'http://127.0.0.1:5000/', '--output', str(out)])


if __name__ == '__main__':
    unittest.main()
