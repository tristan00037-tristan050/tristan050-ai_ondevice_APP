import sys
import importlib
import importlib.util
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "active_policy: install ACTIVE company policy before butler_sidecar import",
    )
    config.addinivalue_line(
        "markers",
        "no_sidecar_token: skip automatic TestClient capability-token injection for tests that do not import the sidecar",
    )
    config.addinivalue_line(
        "markers",
        "requires_llama_grammar: needs the optional llama-cpp grammar runtime "
        "(absent from requirements-firstscreen-ci.lock)",
    )


def _llama_grammar_available() -> bool:
    return importlib.util.find_spec("llama_cpp") is not None


def pytest_collection_modifyitems(config, items):
    """Skip (with a visible reason) tests that require the optional llama-cpp
    grammar runtime when it is not installed. This does NOT mark them passed —
    they show as skipped with the reason below, and still run in an environment
    that has llama-cpp (see the proposed repository-python-grammar job)."""
    if _llama_grammar_available():
        return
    skip = pytest.mark.skip(
        reason="LLAMA_GRAMMAR_IMPORT_FAILED: llama-cpp-python is an optional runtime "
        "absent from requirements-firstscreen-ci.lock"
    )
    for item in items:
        if item.get_closest_marker("requires_llama_grammar"):
            item.add_marker(skip)


def _install_active_policy(tmp_path, monkeypatch):
    """Install a test-only ACTIVE policy before sidecar import.

    The sidecar PolicyGate owns a PolicyStore created at import time, rooted at
    the current working directory. The cwd therefore has to be fixed before
    importing or reloading butler_sidecar.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BUTLER_APP_DATA_DIR", str(tmp_path / "app-data"))

    from butler_pc_core.company_policy.contracts import (
        AccessRule,
        AdminContext,
        make_company_policy,
        sha256_text,
    )
    from butler_pc_core.company_policy import admin_auth
    from butler_pc_core.company_policy.role_registry import RoleRegistryStore
    from butler_pc_core.company_policy.storage import PolicyStore

    admin = AdminContext(
        admin_id_digest=sha256_text("test-admin"),
        role="admin",
        admin_session_digest=sha256_text("test-session"),
        auth_method="tauri_secure_invoke",
    )
    registry = RoleRegistryStore(root=tmp_path / ".butler_role_registry_store")
    registry.bootstrap_self_admin(admin)
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: registry)
    rule = AccessRule(
        dept_digest=sha256_text("dept-unknown"),
        role="employee",
        doc_grade="restricted",
        decision="allow",
        reason_code="TEST_DEFAULT_ALLOW",
    )
    policy = make_company_policy(
        registered_by_digest=admin.admin_id_digest,
        access_rules=[rule],
        status="ACTIVE",
    )
    PolicyStore().save_policy(policy, admin)


@pytest.fixture(autouse=True)
def _v15_inject_capability_token(request, monkeypatch, tmp_path):
    """v1.5 integration: TestClient에 capability token 자동 주입.
    tests/auth/ 본문은 middleware 본질 검증이므로 제외."""
    fspath = str(request.fspath)
    if "/tests/auth/" in fspath:
        return
    if request.node.get_closest_marker("no_sidecar_token"):
        return
    if request.node.get_closest_marker("active_policy"):
        _install_active_policy(tmp_path, monkeypatch)
        if "butler_sidecar" in sys.modules:
            importlib.reload(sys.modules["butler_sidecar"])
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        return
    try:
        import butler_sidecar
    except ImportError:
        return
    manager = getattr(butler_sidecar, "_TOKEN_MANAGER", None)
    if manager is None:
        return
    if not manager.token:
        manager.generate()
    token = manager.token
    if not token:
        return
    orig_init = TestClient.__init__

    def _patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        if "Authorization" not in self.headers:
            self.headers["Authorization"] = f"Bearer {token}"

    monkeypatch.setattr(TestClient, "__init__", _patched_init)
