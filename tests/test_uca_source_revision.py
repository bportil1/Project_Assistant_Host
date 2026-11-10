import tempfile
import unittest
from pathlib import Path
from pah.contracts.uca_source_revision import verified_selection
from pah.labs.source_evidence import SourceEvidenceError

class VerifiedSelectionTests(unittest.TestCase):
    def test_hash_and_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'source.py').write_text('first\nsecond\n',encoding='utf-8')
            result=verified_selection(base,'project','source.py',1,2)
            self.assertEqual(result['schema'],'pah.uca-source-revision@1')
            self.assertEqual(len(result['source_sha256']),64)
    def test_bad_paths_and_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'source.py').write_text('x\n')
            for path in ('../source.py','/tmp/source.py','a//b','source.py/..'):
                with self.assertRaises(SourceEvidenceError):verified_selection(tmp,'project',path,1,1)
            for start,end in ((0,1),(2,2),(1,81),(True,1)):
                with self.assertRaises(SourceEvidenceError):verified_selection(tmp,'project','source.py',start,end)
    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'target.py').write_text('x\n');(root/'link.py').symlink_to(root/'target.py')
            with self.assertRaises(SourceEvidenceError):verified_selection(root,'project','link.py',1,1)
