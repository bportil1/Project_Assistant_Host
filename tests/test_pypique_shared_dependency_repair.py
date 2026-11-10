import importlib.util
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'repair_pypique_shared_dependency.py'
spec = importlib.util.spec_from_file_location('pypique_shared_repair', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = '''[project]\nname = "pyPIQUE"\n[project.optional-dependencies]\nfull = ["Flask>=3", "pah-shared>=0.4,<0.5"]\n[tool.other]\nname="keep"\n'''

def test_local_shared_version_repair_only_changes_full_extra():
    updated = module.repaired_content(BASE, '0.3.0')
    assert '"pah-shared>=0.3,<0.4"' in updated
    assert updated.replace('pah-shared>=0.3,<0.4', 'pah-shared>=0.4,<0.5') == BASE

def test_idempotent():
    updated = module.repaired_content(BASE, '0.3.0')
    assert module.repaired_content(updated, '0.3.0') == updated

@pytest.mark.parametrize('value', ['1.2rc1', 'unknown'])
def test_reject_unstable_version(value):
    with pytest.raises(module.RepairError):
        module.repaired_content(BASE, value)

def test_missing_requirement_not_silently_inserted():
    with pytest.raises(module.RepairError):
        module.repaired_content(BASE.replace('pah-shared>=0.4,<0.5', 'Other'), '0.3.0')
