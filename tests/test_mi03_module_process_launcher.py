"""MI-03: generic local subprocess isolation, no scientific modules required."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time

import pytest

from pah.instance_runtime import InstanceRuntime
from pah.module_processes import ModuleProcessError, ModuleProcessLauncher
from pah.runtime import RuntimeRegistry, RuntimeRegistryError


# The child records the PAH-assigned scope and stays alive for lifecycle tests.
# No networking, external services, or scientific module imports are involved.
CHILD = (
    "import json, os, pathlib, time; "
    "pathlib.Path('marker.json').write_text(json.dumps({"
    "'id': os.environ['PAH_MODULE_INSTANCE_ID'], "
    "'module': os.environ['PAH_MODULE_ID'], "
    "'runtime': os.environ['PAH_MODULE_RUNTIME_DIR'], "
    "'tmp': os.environ['TMPDIR'], "
    "'port': os.environ.get('PAH_MODULE_PORT'), "
    "'secret_override': os.environ.get('PAH_TEST_PUBLIC_VALUE')})); "
    "print('started', flush=True); time.sleep(25)"
)


def wait_for(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.03)
    raise AssertionError(f"Timed out waiting for local child output: {path}")


def test_three_independent_processes_have_distinct_runtime_scope_and_targeted_stop(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / 'state', instance_id='host-1')
    launcher = ModuleProcessLauncher(runtime)
    try:
        children = [
            launcher.launch('ml_lab', [sys.executable, '-c', CHILD], env={'PAH_TEST_PUBLIC_VALUE': 'test'})
            for _ in range(3)
        ]
        assert len({item['module_instance_id'] for item in children}) == 3
        assert len({item['pid'] for item in children}) == 3
        assert len({item['metadata']['port'] for item in children}) == 3
        assert all(item['metadata']['port'] not in runtime.ports.values() for item in children)
        assert len(runtime.module_instances('ml_lab')) == 3

        markers = []
        for item in children:
            run_dir = Path(item['metadata']['runtime_dir'])
            marker = run_dir / 'marker.json'
            wait_for(marker)
            markers.append(json.loads(marker.read_text()))
            assert (run_dir / 'logs' / 'process.log').exists()
            assert (run_dir / 'tmp').is_dir()
            assert (run_dir / 'cache').is_dir()
            assert marker.parent == run_dir  # cwd defaults to private runtime directory
        assert {marker['id'] for marker in markers} == {item['module_instance_id'] for item in children}
        assert {marker['runtime'] for marker in markers} == {item['metadata']['runtime_dir'] for item in children}
        assert {marker['tmp'] for marker in markers} == {str(Path(item['metadata']['runtime_dir']) / 'tmp') for item in children}
        assert {marker['port'] for marker in markers} == {str(item['metadata']['port']) for item in children}

        assert launcher.stop(children[1]['module_instance_id'])
        assert set(runtime.module_instances('ml_lab')) == {
            children[0]['module_instance_id'], children[2]['module_instance_id']
        }
        assert launcher._owned[children[0]['module_instance_id']].process.poll() is None
        assert launcher._owned[children[2]['module_instance_id']].process.poll() is None
        assert Path(children[1]['metadata']['log_file']).is_file()  # logs retained
        with pytest.raises(ModuleProcessError, match='not owned'):
            launcher.stop(children[1]['module_instance_id'])
    finally:
        launcher.stop_all()
        assert not runtime.module_instances('ml_lab')
        runtime.stop()


def test_registry_uses_generic_launcher_without_changing_legacy_adapter_contract(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / 'state', instance_id='host-2')
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        record = registry.launch_process('pypique', [sys.executable, '-c', CHILD], requested_port=None)
        wait_for(Path(record['metadata']['runtime_dir']) / 'marker.json')
        assert record['metadata']['port'] is None
        assert registry.module_ids() == ()  # module discovery is still separate
        assert set(registry.instances('pypique')) == {record['module_instance_id']}
        assert registry.stop_process(record['module_instance_id'])
        assert registry.instances('pypique') == {}
        assert registry.process_launcher is not None
    finally:
        registry.shutdown_all()
        runtime.stop()

    with pytest.raises(RuntimeRegistryError, match='host InstanceRuntime'):
        RuntimeRegistry().launch_process('pypique', [sys.executable, '-c', CHILD])


def test_missing_port_legacy_values_and_duplicate_id_are_rejected(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / 'state', instance_id='host-3')
    launcher = ModuleProcessLauncher(runtime)
    try:
        with pytest.raises(ModuleProcessError, match='argv'):
            launcher.launch('demo', f'{sys.executable} -c pass')
        with pytest.raises(ModuleProcessError, match='identifier'):
            launcher.launch('../demo', [sys.executable, '-c', CHILD])
        with pytest.raises(ModuleProcessError, match='requested_port'):
            launcher.launch('demo', [sys.executable, '-c', CHILD], requested_port=-2)
        first = launcher.launch('demo', [sys.executable, '-c', CHILD], module_instance_id='host-3:demo:first')
        with pytest.raises(ModuleProcessError, match='already exists'):
            launcher.launch('demo', [sys.executable, '-c', CHILD], module_instance_id='host-3:demo:first')
        with pytest.raises(ModuleProcessError, match='already in use'):
            launcher.launch('demo', [sys.executable, '-c', CHILD], requested_port=first['metadata']['port'])
        with pytest.raises(ModuleProcessError, match='not owned'):
            ModuleProcessLauncher(runtime).stop(first['module_instance_id'])
        assert first['module_instance_id'] in runtime.module_instances()
    finally:
        launcher.stop_all()
        runtime.stop()


def test_expired_child_reap_preserves_siblings_and_output(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / 'state', instance_id='host-4')
    registry = RuntimeRegistry(instance_runtime=runtime)
    try:
        quick = registry.launch_process('demo', [sys.executable, '-c', "print('done')"], requested_port=None)
        slow = registry.launch_process('demo', [sys.executable, '-c', CHILD], requested_port=None)
        assert registry.process_launcher is not None
        wait_for(Path(slow['metadata']['runtime_dir']) / 'marker.json')
        registry.process_launcher._owned[quick['module_instance_id']].process.wait(timeout=5)
        assert registry.process_launcher.reap_exited() == [quick['module_instance_id']]
        assert set(registry.instances('demo')) == {slow['module_instance_id']}
        assert Path(quick['metadata']['log_file']).read_text().strip() == 'done'
    finally:
        registry.shutdown_all()
        runtime.stop()


def test_failed_spawn_cannot_pollute_registry(tmp_path: Path):
    runtime = InstanceRuntime(state_dir=tmp_path / 'state', instance_id='host-5')
    launcher = ModuleProcessLauncher(runtime)
    try:
        with pytest.raises(ModuleProcessError, match='Could not launch'):
            launcher.launch('demo', [str(tmp_path / 'does-not-exist')])
        assert runtime.module_instances() == {}
        assert launcher._owned == {}
    finally:
        runtime.stop()


def test_two_host_instances_avoid_another_host_child_port(tmp_path: Path):
    shared = tmp_path / 'state'
    first = InstanceRuntime(state_dir=shared, instance_id='first')
    second = InstanceRuntime(state_dir=shared, instance_id='second')
    a, b = ModuleProcessLauncher(first), ModuleProcessLauncher(second)
    try:
        one = a.launch('demo', [sys.executable, '-c', CHILD])
        two = b.launch('demo', [sys.executable, '-c', CHILD])
        assert one['metadata']['port'] != two['metadata']['port']
        with pytest.raises(ModuleProcessError, match='already in use'):
            b.launch('demo', [sys.executable, '-c', CHILD], requested_port=one['metadata']['port'])
        wait_for(Path(one['metadata']['runtime_dir']) / 'marker.json')
        wait_for(Path(two['metadata']['runtime_dir']) / 'marker.json')
    finally:
        a.stop_all()
        b.stop_all()
        first.stop()
        second.stop()
