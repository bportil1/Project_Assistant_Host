import tempfile
import unittest
from pathlib import Path
from pah.contracts.uca_scope import navigation_scope


class NavigationScopeTests(unittest.TestCase):
    def test_host_ids_are_stable_for_same_root(self):
        with tempfile.TemporaryDirectory() as directory:
            first = navigation_scope('workspace-1', directory, 'token', 2)
            second = navigation_scope('workspace-1', Path(directory), 'token', 2)
            self.assertEqual(first, second)
            self.assertEqual(first['project_id'], 'workspace-1')
            self.assertTrue(first['repository_id'].startswith('repo-'))

    def test_scope_change_changes_identity(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = navigation_scope('ws', d1, 'token', 1)
            b = navigation_scope('ws', d2, 'token', 1)
            self.assertNotEqual(a['repository_id'], b['repository_id'])
            self.assertNotEqual(a['repository_root'], b['repository_root'])

    def test_invalid_scopes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            for ws, token, revision in [(None, 't', 0), ('ws', '', 0), ('ws', 't', -1), ('ws', 't', True)]:
                with self.assertRaises(ValueError):
                    navigation_scope(ws, directory, token, revision)
            with self.assertRaises((ValueError, OSError)):
                navigation_scope('ws', Path(directory)/'missing', 't', 1)
