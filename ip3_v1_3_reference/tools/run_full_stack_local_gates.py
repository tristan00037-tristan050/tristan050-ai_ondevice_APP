#!/usr/bin/env python3
from __future__ import annotations
import os, runpy, shutil, sys, unittest
from pathlib import Path

sys.dont_write_bytecode = True

def clean_pycache(root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        if '.git' in dirnames:
            dirnames.remove('.git')
        for d in list(dirnames):
            if d == '__pycache__':
                shutil.rmtree(Path(dirpath) / d, ignore_errors=True)
                dirnames.remove(d)
        for name in filenames:
            if name.endswith('.pyc'):
                try:
                    (Path(dirpath) / name).unlink()
                except FileNotFoundError:
                    pass

def run_tests(root: Path) -> None:
    loader = unittest.TestLoader()
    suite = loader.discover(str(root / 'tests'), pattern='test*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(2)
    print('UNIT_TESTS_OK')

def run_tool(root: Path, rel: str, args: list[str] | None = None) -> None:
    args = args or []
    old_argv = sys.argv[:]
    old_cwd = Path.cwd()
    try:
        os.chdir(root)
        sys.argv = [str(root / rel)] + args
        try:
            runpy.run_path(str(root / rel), run_name='__main__')
            code = 0
        except SystemExit as exc:
            code = int(exc.code or 0) if isinstance(exc.code, int) or exc.code is None else 1
        if code != 0:
            raise SystemExit(code)
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    run_tests(root)
    tools = [
        ('tools/routing_schema_gate.py', ['.']),
        ('tools/threat_model_gate.py', ['.']),
        ('tools/claim_guard.py', ['.']),
        ('tools/raw_content_scan_gate.py', ['.']),
        ('tools/evidence_taxonomy_gate.py', ['.']),
        ('tools/live_app_hook_replay.py', ['.', '120']),
        ('tools/ip2_pep_live_bridge_gate.py', ['.']),
        ('tools/ip1_model_status_bridge_gate.py', ['.']),
        ('tools/routing_latency_gate.py', ['.', '200']),
        ('tools/failsafe_live_injection_gate.py', ['.']),
        ('tools/product_candidate_full_replay_gate.py', ['.', '300']),
        ('tools/local_all_platform_failclosed_gate.py', ['.']),
    ]
    for rel, args in tools:
        run_tool(root, rel, args)
    clean_pycache(root)
    for rel, args in [
        ('tools/claim_guard.py', ['.']),
        ('tools/clean_package_gate.py', ['.']),
        ('tools/sha256_manifest.py', ['.']),
    ]:
        run_tool(root, rel, args)
    print('SHA256_SEAL_OK')
    print('IP3_V1_3_FULL_STACK_LOCAL_GATES_OK')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
