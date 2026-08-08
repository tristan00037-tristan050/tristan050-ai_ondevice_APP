"""v2.0 §4-2 — `/proc` 가용성 표식이 계약대로 붙어 있는가.

지시서 §4-2
    고칠 것 : 양성 시험에 ★/proc 가용성 표식을 붙여
              쓸 수 없는 환경에서는 ★실행 대상에서 빠지게 한다
    금지    : ★skip 을 도입해 부정 시험까지 건너뛰게 하지 않는다.
              부정 시험(관측 불능 시 닫히는가)은 ★항상 돈다

표식을 붙이는 것은 쉽다. **어려운 것은 부정 시험에 잘못 붙지 않게 하는 것이다.**
그래서 이 파일이 그 경계를 정적으로 못박는다.

★이 파일 자신에는 표식이 없다. 관측 불가 환경에서도 이 계약은 확인돼야 한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_sidecar_token

TEST_DIR = Path(__file__).resolve().parent
CONFTEST = TEST_DIR / "conftest.py"

MARKER = "requires_procfs"

# 관측 불능일 때 ★반드시 도는★ 부정 시험. 표식이 붙으면 계약 위반이다.
FAIL_CLOSED_TESTS = (
    "test_unreadable_stat_is_fail_closed",
    "test_malformed_stat_is_fail_closed",
    "test_proc_enumeration_failure_is_fail_closed",
    "test_lineage_enumeration_propagates_the_failure",
    "test_require_procfs_closes_when_self_stat_is_unreadable",
    "test_require_procfs_closes_when_self_stat_is_malformed",
    "test_require_procfs_closes_when_enumeration_is_blocked",
    "test_supervisor_checks_procfs_before_reading_control",
    "test_identity_unproven_is_a_reportable_code",
    "test_unproven_identity_never_reports_an_empty_group",
)


def _decorated_names(path: Path) -> dict[str, list[str]]:
    """함수 이름 → 그 함수에 붙은 데코레이터 표현식 목록."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = [ast.unparse(d) for d in node.decorator_list]
    return found


def _all_test_files() -> list[Path]:
    return sorted(p for p in TEST_DIR.glob("test_*.py"))


# ══ 표식은 skip 이 아니라 수집 제외로 동작한다 ═════════════════════════
def test_marker_is_registered_and_deselects_rather_than_skips():
    body = CONFTEST.read_text(encoding="utf-8")
    assert 'config.addinivalue_line(' in body
    assert MARKER in body
    # ★수집 제외를 쓴다 — skip 이 아니다
    assert "pytest_deselected" in body
    assert "pytest_collection_modifyitems" in body


def test_marker_never_becomes_a_skipif():
    """표식이 skipif 로 구현되면 skipped 로 집계되고 §E6-4 훅이 실패로 바꾼다."""
    for path in _all_test_files():
        body = path.read_text(encoding="utf-8")
        assert f'skipif(.*{MARKER}' not in body
        if MARKER in body:
            # 표식은 pytest.mark.requires_procfs 형태로만 쓴다
            assert f"pytest.mark.{MARKER}" in body, path.name


def test_skip_is_still_forbidden_in_this_directory():
    """§E6-4 — 건너뛴 시험은 통과가 아니다. 그 훅이 그대로 살아 있어야 한다."""
    body = CONFTEST.read_text(encoding="utf-8")
    assert "SKIP_NOT_ALLOWED" in body
    assert "report.outcome = \"failed\"" in body


# ══ ★부정 시험에는 표식이 붙지 않는다 ═════════════════════════════════
def test_fail_closed_tests_carry_no_procfs_marker():
    """관측 불능일 때 닫히는지 보는 시험은 ★그 환경에서 가장 필요하다.★"""
    decorated: dict[str, list[str]] = {}
    for path in _all_test_files():
        decorated.update(_decorated_names(path))

    missing = [name for name in FAIL_CLOSED_TESTS if name not in decorated]
    assert missing == [], f"부정 시험이 사라졌다: {missing}"

    for name in FAIL_CLOSED_TESTS:
        for decorator in decorated[name]:
            assert MARKER not in decorator, (
                f"{name} 에 {MARKER} 가 붙었다 — 관측 불능 환경에서 빠지면 안 된다"
            )


def test_negative_fact_matrix_is_never_deselected():
    """F-01 여섯 부정 사실 행렬도 표식 없이 항상 돈다."""
    path = TEST_DIR / "test_preflight_negative_facts.py"
    body = path.read_text(encoding="utf-8")
    assert MARKER not in body


def test_transport_policy_tests_are_never_deselected():
    """F-03 우회 부정 시험도 /proc 과 무관하다 — 항상 돈다."""
    path = TEST_DIR / "test_gh_transport_policy.py"
    assert MARKER not in path.read_text(encoding="utf-8")


# ══ 양성 시험에는 표식이 붙어 있다 ═════════════════════════════════════
POSITIVE_TESTS_NEEDING_PROCFS = (
    ("test_output_containment.py", "test_normal_exit_with_persistent_grandchild_is_detected"),
    ("test_output_containment.py", "test_double_fork_setsid_escape_is_detected"),
    ("test_linux_subreaper.py", "test_child_subreaper_can_be_enabled_and_verified"),
    ("test_linux_subreaper.py", "test_pin_process_refuses_a_recycled_pid"),
    ("test_procfs_fail_closed.py", "test_self_is_readable"),
    ("test_procfs_fail_closed.py", "test_require_procfs_passes_when_proc_is_usable"),
)


@pytest.mark.parametrize(("filename", "test_name"), POSITIVE_TESTS_NEEDING_PROCFS)
def test_positive_tests_are_marked(filename, test_name):
    """실제 프로세스를 띄워 후손을 세는 시험은 관측이 돼야 뜻이 있다."""
    decorated = _decorated_names(TEST_DIR / filename)
    assert test_name in decorated, f"{filename}: {test_name} 이 없다"
    assert any(MARKER in d for d in decorated[test_name]), (
        f"{test_name} 에 {MARKER} 표식이 없다"
    )


def test_no_test_file_still_uses_the_old_platform_skip():
    """`skipif(sys.platform != "linux")` 는 skip 을 만든다 — 남아 있으면 안 된다."""
    pattern = "skipif(sys.platform != " + '"linux"'
    for path in _all_test_files():
        if path.name == Path(__file__).name:
            continue  # 이 파일은 그 형태를 ★찾는 쪽★ 이다
        assert pattern not in path.read_text(encoding="utf-8"), path.name


# ══ 표식 판정이 실제 관측 가능성을 본다 ════════════════════════════════
def test_availability_check_looks_at_real_observability():
    """"Linux 면 /proc 이 있다" 를 전제하지 않는다 — 실제로 읽어 본다."""
    body = CONFTEST.read_text(encoding="utf-8")
    assert "/proc/self/stat" in body
    assert 'os.listdir("/proc")' in body
    assert "sys.platform" in body


def test_availability_is_true_here_so_positive_tests_actually_ran():
    """이 환경에서는 관측이 되므로 양성 시험이 ★빠지지 않았다★.

    표식을 넣고 나서 양성 시험이 조용히 사라지면 그것도 결함이다.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_ac25_conftest", CONFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PROCFS_AVAILABLE is True, (
        "이 환경에서 /proc 관측이 불가능하다 — 양성 시험이 수집에서 빠졌다. "
        "회신의 LINUX_TESTS 값에 그 사실을 적어야 한다."
    )
