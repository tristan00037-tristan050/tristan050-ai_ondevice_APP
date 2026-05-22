import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest


@pytest.fixture(autouse=True)
def _v15_inject_capability_token(request, monkeypatch):
    """v1.5 integration: TestClient에 capability token 자동 주입.
    tests/auth/ 본문은 middleware 본질 검증이므로 제외."""
    fspath = str(request.fspath)
    if "/tests/auth/" in fspath:
        return
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
