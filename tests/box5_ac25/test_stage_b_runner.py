"""§15 M-1 — 보호 runner 시험.

★워크플로가 설치·검사 명령 문자열을 조립하지 않는다.
★실행 모듈은 항상 보호된 쪽에서 온다. 후보가 검사 도구를 가로채지 못한다.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from ac25 import stage_b_runner as sbr

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
AC25_WORKFLOWS = (
    WORKFLOW_DIR / "box5-ac25-trusted-verification.yml",
    WORKFLOW_DIR / "box5-ac25-stage-a-smoke.yml",
)

LOCK_BODY = (
    "pytest==9.1.1 \\\n    --hash=sha256:" + "1" * 64 + "\n"
    "PyYAML==6.0.3 \\\n    --hash=sha256:" + "2" * 64 + "\n"
)


@pytest.fixture
def trusted(tmp_path: Path) -> Path:
    """보호된 쪽 — 잠금과 시험 트리를 갖는다."""
    root = tmp_path / "ac25-trusted"
    (root / "tests" / "box5_ac25").mkdir(parents=True)
    (root / "tests" / "box5_ac25" / "test_x.py").write_text(
        "import pytest\nimport yaml\n", encoding="utf-8"
    )
    lock = root / ".github" / "box5" / "ac25"
    lock.mkdir(parents=True)
    (lock / "pr903_candidate_lock.json").write_text(
        (REPO_ROOT / ".github" / "box5" / "ac25" / "pr903_candidate_lock.json").read_text(),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """검사 대상 쪽 — manifest 를 갖는다."""
    root = tmp_path / "ac25-worktree"
    root.mkdir()
    (root / "requirements-firstscreen-ci.lock").write_text(LOCK_BODY, encoding="utf-8")
    return root


# ══ 계획 수립 ══════════════════════════════════════════════════════════
def test_plan_is_built_from_the_protected_lock(trusted, worktree):
    plan = sbr.build_plan(trusted_root=trusted, worktree=worktree)
    assert plan.manifest_path == worktree / "requirements-firstscreen-ci.lock"
    assert len(plan.manifest_sha256) == 64
    # ★검사 목록은 후보가 아니라 보호된 잠금에서 온다
    assert len(plan.python_tests) == 19
    assert len(plan.javascript_tests) == 2
    assert all(path.startswith("tests/") for path in plan.python_tests)


def test_stage_b_requires_two_separate_roots(trusted):
    """후보 checkout 이 실행 모듈 자리와 같으면 검사 도구를 가로챌 수 있다."""
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.build_plan(trusted_root=trusted, worktree=trusted)
    assert caught.value.code == sbr.STAGE_B_RUNNER_WORKTREE_INVALID


def test_smoke_may_use_a_single_root(trusted):
    """단계 A smoke 는 후보 자신을 시험하므로 두 자리가 같다."""
    (trusted / "requirements-firstscreen-ci.lock").write_text(LOCK_BODY, encoding="utf-8")
    plan = sbr.build_plan(
        trusted_root=trusted, worktree=trusted, require_separate_roots=False
    )
    assert plan.trusted_root == plan.worktree


def test_missing_manifest_in_worktree_is_rejected(trusted, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    from ac25.dependency_manifest import (
        STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND,
        DependencyManifestError,
    )

    with pytest.raises(DependencyManifestError) as caught:
        sbr.build_plan(trusted_root=trusted, worktree=empty)
    assert caught.value.code == STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND


def test_missing_roots_are_rejected(trusted, worktree, tmp_path):
    absent = tmp_path / "absent"
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.build_plan(trusted_root=absent, worktree=worktree)
    assert caught.value.code == sbr.STAGE_B_RUNNER_PLAN_INVALID
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.build_plan(trusted_root=trusted, worktree=absent)
    assert caught.value.code == sbr.STAGE_B_RUNNER_WORKTREE_INVALID


# ══ 명령 조립 ══════════════════════════════════════════════════════════
def _captured(monkeypatch, returncode: int = 0):
    """★격리기 경유 호출을 가로챈다. sbr 은 subprocess 를 직접 부르지 않는다."""
    calls = []

    def fake_run_and_read(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return returncode, b"", b""

    monkeypatch.setattr(sbr.output_containment, "run_and_read", fake_run_and_read)
    return calls


def test_install_uses_require_hashes_and_no_deps(trusted, worktree, monkeypatch):
    calls = _captured(monkeypatch)
    sbr.install(sbr.build_plan(trusted_root=trusted, worktree=worktree))
    argv, kwargs = calls[0]
    assert "--require-hashes" in argv
    assert "--no-deps" in argv
    assert argv[-1] == str(worktree / "requirements-firstscreen-ci.lock")
    assert kwargs.get("shell") is not True
    assert isinstance(argv, list)


def test_runner_never_uses_a_shell(trusted, worktree, monkeypatch):
    calls = _captured(monkeypatch)
    plan = sbr.build_plan(trusted_root=trusted, worktree=worktree)
    sbr.install(plan)
    sbr.run_checks(plan)
    for argv, kwargs in calls:
        assert isinstance(argv, list), argv
        assert kwargs.get("shell") is not True
        assert "shell" not in kwargs


def test_checks_run_the_lock_derived_lists(trusted, worktree, monkeypatch):
    calls = _captured(monkeypatch)
    plan = sbr.build_plan(trusted_root=trusted, worktree=worktree)
    sbr.run_checks(plan)
    joined = [argv for argv, _ in calls]
    pythonish = next(a for a in joined if "-m" in a and "pytest" in a)
    assert set(plan.python_tests) <= set(pythonish)
    vitestish = next(a for a in joined if "vitest" in a)
    assert "AccountingReviewPage.test.tsx" in " ".join(vitestish)


def test_execution_modules_always_come_from_the_trusted_root(trusted, worktree, monkeypatch):
    """★PYTHONPATH 는 언제나 보호된 쪽을 가리킨다."""
    calls = _captured(monkeypatch)
    plan = sbr.build_plan(trusted_root=trusted, worktree=worktree)
    sbr.install(plan)
    _argv, kwargs = calls[0]
    env = kwargs["env"]
    assert env["PYTHONPATH"] == str(trusted / "scripts" / "ci")
    assert str(worktree) not in env["PYTHONPATH"]
    assert env["PYTHONNOUSERSITE"] == "1"


def test_candidate_runner_shadowing_is_blocked(trusted, worktree, monkeypatch):
    """후보가 자기 ac25 패키지를 심어도 PYTHONPATH 가 보호된 쪽을 가리킨다."""
    shadow = worktree / "scripts" / "ci" / "ac25"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text("raise SystemExit('pwned')\n", encoding="utf-8")
    calls = _captured(monkeypatch)
    plan = sbr.build_plan(trusted_root=trusted, worktree=worktree)
    sbr.install(plan)
    env = calls[0][1]["env"]
    assert str(shadow.parent) not in env["PYTHONPATH"]
    assert env["PYTHONPATH"].startswith(str(trusted))


def test_empty_designated_list_is_not_success(trusted, worktree, monkeypatch):
    plan = sbr.build_plan(trusted_root=trusted, worktree=worktree)
    from dataclasses import replace

    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.run_checks(replace(plan, python_tests=()))
    assert caught.value.code == sbr.STAGE_B_RUNNER_PLAN_INVALID
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.run_checks(replace(plan, javascript_tests=()))
    assert caught.value.code == sbr.STAGE_B_RUNNER_PLAN_INVALID


def test_install_failure_propagates(trusted, worktree, monkeypatch):
    _captured(monkeypatch, returncode=1)
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.install(sbr.build_plan(trusted_root=trusted, worktree=worktree))
    assert caught.value.code == sbr.STAGE_B_RUNNER_INSTALL_FAILED


# ══ selftest — JUnit 독립 확인 ═════════════════════════════════════════
def _junit(path: Path, *, tests=5, failures=0, errors=0, skipped=0) -> None:
    path.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite name="p" tests="{tests}" '
        f'failures="{failures}" errors="{errors}" skipped="{skipped}"/></testsuites>',
        encoding="utf-8",
    )


@pytest.fixture
def selftest_plan(trusted, worktree, tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    return sbr.build_plan(trusted_root=trusted, worktree=worktree)


def test_selftest_reads_junit_independently(selftest_plan, tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        _junit(Path(tmp_path / "runner") / sbr.JUNIT_FILENAME, tests=184)
        return 0, b"", b""

    monkeypatch.setattr(sbr.output_containment, "run_and_read", fake_run)
    (tmp_path / "runner").mkdir(parents=True, exist_ok=True)
    summary = sbr.run_selftest(selftest_plan)
    assert summary["tests_total"] == 184
    assert summary["tests_skipped"] == 0
    assert len(summary["junit_sha256"]) == 64


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"skipped": 1}, sbr.STAGE_B_SELFTEST_SKIPPED_NOT_ZERO),
        ({"failures": 1}, sbr.STAGE_B_SELFTEST_FAILED),
        ({"errors": 1}, sbr.STAGE_B_SELFTEST_FAILED),
        ({"tests": 0}, sbr.STAGE_B_SELFTEST_NO_TESTS),
    ],
)
def test_selftest_rejects_bad_totals(selftest_plan, tmp_path, monkeypatch, kwargs, code):
    def fake_run(argv, **_kwargs):
        _junit(Path(tmp_path / "runner") / sbr.JUNIT_FILENAME, **kwargs)
        return 0, b"", b""

    monkeypatch.setattr(sbr.output_containment, "run_and_read", fake_run)
    (tmp_path / "runner").mkdir(parents=True, exist_ok=True)
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.run_selftest(selftest_plan)
    assert caught.value.code == code


def test_selftest_without_junit_is_fail_closed(selftest_plan, monkeypatch):
    monkeypatch.setattr(
        sbr.output_containment, "run_and_read", lambda argv, **kw: (0, b"", b"")
    )
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.run_selftest(selftest_plan)
    assert caught.value.code == sbr.STAGE_B_SELFTEST_JUNIT_UNREADABLE


def test_selftest_does_not_trust_conftest_alone(selftest_plan, tmp_path, monkeypatch):
    """conftest 의 skip 금지 장치가 지워져도 JUnit 에서 잡힌다."""
    def fake_run(argv, **_kwargs):
        # 검사는 0 으로 끝났다고 치자(= skip 금지 장치가 없는 상황)
        _junit(Path(tmp_path / "runner") / sbr.JUNIT_FILENAME, tests=10, skipped=3)
        return 0, b"", b""

    monkeypatch.setattr(sbr.output_containment, "run_and_read", fake_run)
    (tmp_path / "runner").mkdir(parents=True, exist_ok=True)
    with pytest.raises(sbr.StageBRunnerError) as caught:
        sbr.run_selftest(selftest_plan)
    assert caught.value.code == sbr.STAGE_B_SELFTEST_SKIPPED_NOT_ZERO


def test_selftest_writes_meta_only_summary(selftest_plan, tmp_path, monkeypatch):
    def fake_run(argv, **_kwargs):
        _junit(Path(tmp_path / "runner") / sbr.JUNIT_FILENAME, tests=184)
        return 0, b"", b""

    monkeypatch.setattr(sbr.output_containment, "run_and_read", fake_run)
    (tmp_path / "runner").mkdir(parents=True, exist_ok=True)
    sbr.run_selftest(selftest_plan)
    written = json.loads(
        (tmp_path / "runner" / sbr.SELFTEST_SUMMARY_FILENAME).read_text()
    )
    assert set(written) == {
        "tests_total", "tests_failed", "tests_skipped", "tests_passed", "junit_sha256"
    }
    for value in written.values():
        assert isinstance(value, (int, str))


# ══ 워크플로가 명령을 조립하지 않는다 ══════════════════════════════════
FORBIDDEN_IN_WORKFLOWS = (
    "pip install",
    "requirements.txt",
    "requirements-firstscreen-ci.lock",
    "pytest tests/",
    "vitest run",
)


@pytest.mark.parametrize("path", AC25_WORKFLOWS, ids=lambda p: p.name)
@pytest.mark.parametrize("forbidden", FORBIDDEN_IN_WORKFLOWS)
def test_workflows_do_not_assemble_commands(path, forbidden):
    assert forbidden not in path.read_text(encoding="utf-8"), forbidden


@pytest.mark.parametrize("path", AC25_WORKFLOWS, ids=lambda p: p.name)
def test_workflows_enter_through_the_protected_runner(path):
    body = path.read_text(encoding="utf-8")
    assert "ac25.stage_b_runner" in body or "stage_b_runner" in body


@pytest.mark.parametrize("path", AC25_WORKFLOWS, ids=lambda p: p.name)
def test_python_312_is_pinned(path):
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    setups = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "setup-python" in str(step.get("uses", ""))
    ]
    assert setups, f"{path.name} 에 setup-python 이 없다"
    for step in setups:
        assert step["with"]["python-version"] == "3.12"
        assert len(str(step["uses"]).split("@")[1]) == 40
