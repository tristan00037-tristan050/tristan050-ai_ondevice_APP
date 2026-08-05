import shutil
import sys
from pathlib import Path

import pytest

# scripts/ci 를 import 경로에 추가(ac25 패키지 로드)
_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
if str(_CI) not in sys.path:
    sys.path.insert(0, str(_CI))


@pytest.fixture(scope="session")
def require_ssh_keygen() -> str:
    """서명 검증에 ssh-keygen 이 필요하다.

    ★없으면 건너뛰지 않고 실패한다. 검증을 못 한 것은 통과가 아니다.
    """
    path = shutil.which("ssh-keygen")
    if path is None:
        pytest.fail(
            "SSH_KEYGEN_NOT_AVAILABLE: 서명을 검증할 수 없다(fail-closed). "
            "이 시험을 건너뛰면 서명 신뢰원이 확인되지 않은 채 통과로 집계된다."
        )
    return path


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """★§E6-4 skipped=0 강제.

    건너뛴 시험은 '안 돌린 것'이며 통과로 셀 수 없다. 이 디렉터리 안에서
    skip 이 발생하면 실패로 바꾼다. xfail 은 명시적 기대이므로 제외한다.
    (conftest 는 이 디렉터리에만 적용되므로 다른 시험군에는 영향이 없다.)
    """
    outcome = yield
    report = outcome.get_result()
    if report.skipped and not hasattr(report, "wasxfail"):
        report.outcome = "failed"
        report.longrepr = (
            f"SKIP_NOT_ALLOWED: 건너뛴 시험은 통과가 아니다 (§E6-4) — {report.longrepr}"
        )
