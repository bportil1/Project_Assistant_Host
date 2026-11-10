"""UCA-02 template and standalone JavaScript layout-contract acceptance."""
from pathlib import Path
import subprocess
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LayoutContractTests(unittest.TestCase):
    def test_template_wiring(self):
        text = (ROOT / 'pah/web/templates/index.html').read_text()
        self.assertIn('id="ucaMode"', text)
        self.assertIn('data-mode="uca"', text)
        for pane in ('editor', 'pypique', 'analyzer'):
            self.assertIn(f'data-uca-pane="{pane}"', text)
            self.assertIn(f'data-uca-toggle="{pane}"', text)
            self.assertIn(f'data-uca-width="{pane}"', text)

    def test_host_mode_registration(self):
        source = (ROOT / 'pah/web/static/pah.js').read_text()
        self.assertIn("$('ucaMode')?.classList.toggle('hidden', mode !== 'uca')", source)
        self.assertIn("if (name === 'workspace' || name === 'uca')", source)

    @unittest.skipUnless(shutil.which('node'), 'Node unavailable')
    def test_js_contract(self):
        completed = subprocess.run(['node', '--test', str(ROOT / 'tests/uca_layout.test.mjs')], capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

if __name__ == '__main__':
    unittest.main()
