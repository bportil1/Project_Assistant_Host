import unittest
from pathlib import Path


class ProviderNavigationRouteContractTests(unittest.TestCase):
    def test_route_is_explicit_and_project_scoped(self):
        src=(Path(__file__).resolve().parents[1]/'pah/app.py').read_text()
        start=src.index('@app.post("/api/uca/analyzer/provider-navigation")')
        end=src.index('@app.get("/api/analyzer/status")',start)
        route=src[start:end]
        self.assertIn('workspaces.is_module_enabled("code_analyzer")',route)
        self.assertIn('build_navigation_snapshot',route)
        self.assertIn('context_selection()',route)
        self.assertIn('"no-store"',route)
        self.assertNotIn('write_text(',route)


if __name__ == '__main__':
    unittest.main()
