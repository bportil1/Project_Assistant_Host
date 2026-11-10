"""Network-free contract tests for optional navigation acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'scripts/uca11_source_navigation.py'
spec = importlib.util.spec_from_file_location('uca11_source_navigation', FILE)
nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nav)

FIXTURE = dict(workspace='w', repository='/tmp/work', finding_id='finding-1',
               relative_path='src/a.py', source_sha256='a'*64, start_line=12)

class NavigationAcceptanceTests(unittest.TestCase):
    def test_fixture_validation(self):
        self.assertEqual(nav.fixture_fields(FIXTURE), FIXTURE)
        for broken in ({**FIXTURE, 'relative_path':'../secrets'},
                       {**FIXTURE, 'source_sha256':'f'},
                       {**FIXTURE, 'start_line':True},
                       {**FIXTURE, 'finding_id':''}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                nav.fixture_fields(broken)

    def test_default_does_not_launch_browser(self):
        with patch.object(nav, 'browser_probe', side_effect=AssertionError('browser called')):
            report=nav.assess('http://127.0.0.1:5000/', FIXTURE)
        self.assertEqual(report['result'], 'not_run')
        self.assertTrue(all(x=='unverified' for x in report['gates'].values()))

    def test_observed_navigation_does_not_claim_other_gates(self):
        with patch.object(nav, 'browser_probe', return_value=({'matching_finding':'passed',
                    'verified_navigation_dispatch':'passed','single_editor':'passed'},'observed')):
            report=nav.assess('http://127.0.0.1:5000/',FIXTURE,execute=True)
        self.assertEqual(report['gates']['sat_to_editor'],'navigation_event_observed')
        self.assertEqual(report['gates']['stale_source_rejection'],'unverified')
        self.assertEqual(report['gates']['project_switching'],'unverified')

    def test_rejection_and_failed_browser_not_passed(self):
        with patch.object(nav,'browser_probe',return_value=({'scope':'failed'},'unverified')):
            self.assertEqual(nav.assess('http://127.0.0.1:5000/',FIXTURE,execute=True)['result'],'failed')
        with patch.object(nav,'browser_probe',side_effect=ImportError('playwright')):
            self.assertEqual(nav.assess('http://127.0.0.1:5000/',FIXTURE,execute=True)['result'],'unverified')

    def test_no_external_host_or_overwrite(self):
        with self.assertRaises(ValueError):
            nav.assess('http://example.com:5000/',FIXTURE)
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'fixture.json'
            fixture.write_text(__import__('json').dumps(FIXTURE))
            out=Path(tmp)/'report.json'
            args=['--url','http://127.0.0.1:5000/','--fixture',str(fixture),'--output',str(out)]
            self.assertEqual(nav.main(args),0)
            with self.assertRaises(FileExistsError):nav.main(args)

if __name__=='__main__': unittest.main()
