import os
import shutil
import sys
from pathlib import Path

import pytest

# scripts/ci 를 import 경로에 추가(ac25 패키지 로드)
_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
if str(_CI) not in sys.path:
    sys.path.insert(0, str(_CI))


# ══ v2.0 §4-2 — /proc 가용성 표식 ══════════════════════════════════════
def _procfs_available() -> bool:
    """이 환경에서 계보 관측이 실제로 되는지 본다.

    Linux 라고 /proc 이 있는 것은 아니다(컨테이너·hidepid·chroot). 양성 시험은
    실제 프로세스를 띄워 후손을 세므로 관측이 되어야 의미가 있다.
    """
    if sys.platform != "linux":
        return False
    try:
        raw = Path("/proc/self/stat").read_bytes()
        os.listdir("/proc")
    except OSError:
        return False
    return b") " in raw


PROCFS_AVAILABLE = _procfs_available()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_procfs: 실제 /proc 계보 관측이 필요한 ★양성★ 시험. "
        "관측이 불가능한 환경에서는 수집 단계에서 제외한다(skip 이 아니다).",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """★관측할 수 없는 환경에서는 양성 시험을 ★실행 대상에서 뺀다★.

    ★skip 을 쓰지 않는다★. skip 은 "돌렸는데 건너뛴 것" 으로 집계되고, 이
    디렉터리는 아래 훅으로 skip 을 실패로 바꾸기 때문이다(§E6-4). 그래서
    ★수집에서 제외★ 한다 — skipped 는 0 으로 유지된다.

    ★부정 시험에는 이 표식을 붙이지 않는다★. "관측 불능일 때 닫히는가" 는
    관측이 불가능한 바로 그 환경에서 가장 중요한 시험이다(§4-2 금지 항목).
    """
    if PROCFS_AVAILABLE:
        return
    kept, deselected = [], []
    for item in items:
        (deselected if item.get_closest_marker("requires_procfs") else kept).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


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
