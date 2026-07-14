"""Shared builder for the P0-1 entrypoint-owner blob-in-tree attacks (ATK-061..063).

Not collected as tests (module name does not match the ``test_*.py`` discovery
pattern). Used by both the attack matrix dispatch and the dedicated P0 tests.

Each scenario builds a real throwaway git repo whose committed facade module
re-exports all six required entrypoints (plus the adapter) from a helper module,
then applies a variant that must be blocked by ``validate_product_module``:

- ``clean``               : nothing tampered — must PASS (baseline).
- ``tamper_after_commit`` : helper owner file modified after commit (ATK-061).
- ``untracked_owner``     : one entrypoint owned by an untracked module (ATK-062).
- ``runtime_rebind``      : an entrypoint rebound to an untracked-owned callable (ATK-063).

The committed facade carries a placeholder commit constant; the test injects the
real HEAD oid onto the imported module attribute (simulating deploy-time identity
injection) so the module-level checks pass and the *owner* verification is what the
scenario exercises.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

from butler_bench.canonical import sha256_file
from butler_bench.product_bridge import validate_product_module

_ENTRYPOINTS = (
    "Box3ProductPipelineRuntime",
    "run_product_matrix",
    "run_cold_worker_handshake",
    "measure_dual_resident_pressure",
    "verify_samples_first",
    "butler_bench_run_v2",
)

_HELPER_SOURCE = "\n".join(
    f"def {name}(*args, **kwargs):\n    return {name!r}\n" for name in _ENTRYPOINTS
) + "\n"

_UNTRACKED_SOURCE = "def verify_samples_first(*args, **kwargs):\n    return 'untracked'\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "bench@butler.local")
    _git(root, "config", "user.name", "bench")


def _facade_source(imports_from: dict[str, str]) -> str:
    # No self-declared commit constant (R2-P0-002): identity is proven from the Git
    # object database by verify_blob_in_commit_tree, not from a module attribute.
    lines = [f"from {imports_from[name]} import {name}" for name in _ENTRYPOINTS]
    return "\n".join(lines) + "\n"


def build_and_validate(root: Path, variant: str) -> dict[str, object]:
    """Build the scenario under ``root`` and run validate_product_module.

    Returns the product identity on success; raises GateError on a blocked scenario.
    Cleans up sys.path/sys.modules regardless of outcome.
    """
    root = root.resolve()
    _init_repo(root)
    facade_name = f"prod_facade_{variant}"
    helper_name = f"prod_helper_{variant}"

    (root / f"{helper_name}.py").write_text(_HELPER_SOURCE, encoding="utf-8")
    imports = {name: helper_name for name in _ENTRYPOINTS}

    if variant == "untracked_owner":
        untracked_name = f"prod_untracked_{variant}"
        (root / f"{untracked_name}.py").write_text(_UNTRACKED_SOURCE, encoding="utf-8")
        imports["verify_samples_first"] = untracked_name  # committed facade imports an untracked owner

    facade_path = root / f"{facade_name}.py"
    facade_path.write_text(_facade_source(imports), encoding="utf-8")

    _git(root, "add", f"{facade_name}.py", f"{helper_name}.py")
    _git(root, "commit", "-qm", "approved product module")
    commit = _git(root, "rev-parse", "HEAD^{commit}")

    if variant == "tamper_after_commit":
        (root / f"{helper_name}.py").write_text(_HELPER_SOURCE + "TAMPERED = True\n", encoding="utf-8")

    added = None
    try:
        sys.path.insert(0, str(root))
        module = importlib.import_module(facade_name)
        added = facade_name

        if variant == "runtime_rebind":
            rebind_name = f"prod_rebind_{variant}"
            (root / f"{rebind_name}.py").write_text(_UNTRACKED_SOURCE, encoding="utf-8")
            rebind_module = importlib.import_module(rebind_name)
            module.verify_samples_first = rebind_module.verify_samples_first  # owner is untracked

        return validate_product_module(
            facade_name,
            approved_product_root=root,
            expected_module_sha256=sha256_file(facade_path),
            expected_commit_oid=commit,
        )
    finally:
        if str(root) in sys.path:
            sys.path.remove(str(root))
        for name in list(sys.modules):
            if name in {facade_name, helper_name} or name.startswith(("prod_untracked_", "prod_rebind_")):
                sys.modules.pop(name, None)


ATK_VARIANT = {
    "entrypoint_owner_tamper_after_commit": "tamper_after_commit",
    "entrypoint_owner_untracked_file": "untracked_owner",
    "entrypoint_rebound_at_runtime": "runtime_rebind",
}


def run_entrypoint_owner_attack(name: str, root: Path) -> None:
    """Matrix dispatch entry: builds the scenario and lets the GateError propagate."""
    build_and_validate(root, ATK_VARIANT[name])
