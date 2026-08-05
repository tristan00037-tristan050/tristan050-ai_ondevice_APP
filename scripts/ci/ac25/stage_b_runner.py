"""§5-3 M-1 — 보호된 runner.

워크플로가 pip·pytest·vitest 문자열을 직접 조립하지 않는다. 조립하면 그 문자열이
워크플로를 고칠 수 있는 자의 손에 있고, 후보가 검사 도구를 가로챌 수 있다.

★실행 모듈은 항상 보호된 쪽(ac25-trusted)에서 온다. 후보는 작업 트리에만 둔다.
  두 자리를 나누지 않으면 후보 checkout 의 설정 파일·플러그인·runner 가 검사
  자체를 바꿀 수 있다.

★모든 하위 프로세스는 argv 배열과 shell=False 로 부른다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .dependency_manifest import DependencyManifestError, resolve_manifest
from .designated_checks import designated_js_tests, designated_python_tests

STAGE_B_RUNNER_INSTALL_FAILED = "STAGE_B_RUNNER_INSTALL_FAILED"
STAGE_B_RUNNER_TESTS_FAILED = "STAGE_B_RUNNER_TESTS_FAILED"
STAGE_B_RUNNER_PLAN_INVALID = "STAGE_B_RUNNER_PLAN_INVALID"
STAGE_B_RUNNER_WORKTREE_INVALID = "STAGE_B_RUNNER_WORKTREE_INVALID"

# 후보가 심을 수 있는 실행 경로를 차단한다
_SAFE_ENV = {
    "PYTHONNOUSERSITE": "1",
    "PIP_CONFIG_FILE": os.devnull,
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
}


class StageBRunnerError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class StageBPlan:
    trusted_root: Path
    worktree: Path
    manifest_path: Path
    manifest_sha256: str
    python_tests: tuple[str, ...]
    javascript_tests: tuple[str, ...]
    python_executable: str


def _lock(trusted_root: Path):
    from . import anchors, lock_verifier

    return lock_verifier.load_candidate_lock(
        (trusted_root / anchors.CANDIDATE_LOCK_PATH).read_bytes()
    )


def build_plan(
    *, trusted_root: Path, worktree: Path, require_separate_roots: bool = True
) -> StageBPlan:
    """검사 계획을 ★보호된 쪽★ 에서 만든다. 후보는 목록을 고르지 못한다.

    require_separate_roots 는 단계 B 전용이다. 단계 B 에서는 실행 모듈이 오는
    자리(ac25-trusted)와 검사 대상 자리(ac25-worktree)가 반드시 달라야 한다.
    단계 A smoke 는 후보 자신을 시험하므로 두 자리가 같다.
    """
    if not trusted_root.is_dir():
        raise StageBRunnerError(STAGE_B_RUNNER_PLAN_INVALID, "trusted_root 없음")
    if not worktree.is_dir():
        raise StageBRunnerError(STAGE_B_RUNNER_WORKTREE_INVALID, "worktree 없음")
    if require_separate_roots and trusted_root.resolve() == worktree.resolve():
        raise StageBRunnerError(
            STAGE_B_RUNNER_WORKTREE_INVALID, "trusted_root 와 worktree 가 같다"
        )

    # manifest 는 ★검사 대상 트리★ 에서 읽는다. 시험 목록은 보호된 잠금에서 온다.
    try:
        resolved = resolve_manifest(
            repo_root=worktree, test_root=trusted_root / "tests" / "box5_ac25"
        )
    except DependencyManifestError:
        raise

    lock = _lock(trusted_root)
    return StageBPlan(
        trusted_root=trusted_root,
        worktree=worktree,
        manifest_path=worktree / resolved.relative_path,
        manifest_sha256=resolved.sha256,
        python_tests=tuple(designated_python_tests(lock)),
        javascript_tests=tuple(designated_js_tests(lock)),
        python_executable=sys.executable,
    )


def _environment(plan: StageBPlan) -> dict:
    env = dict(os.environ)
    env.update(_SAFE_ENV)
    # ★실행 모듈은 언제나 보호된 쪽에서 온다
    env["PYTHONPATH"] = str(plan.trusted_root / "scripts" / "ci")
    return env


def _run(argv: list[str], *, cwd: Path, env: dict, code: str) -> None:
    # ★argv 배열 · shell=False
    done = subprocess.run(argv, cwd=str(cwd), env=env, check=False)
    if done.returncode != 0:
        raise StageBRunnerError(code, f"exit={done.returncode}")


def install(plan: StageBPlan) -> None:
    """해시 고정 manifest 로만 설치한다."""
    _run(
        [
            plan.python_executable, "-m", "pip", "install",
            "--require-hashes", "--no-deps",
            "-r", str(plan.manifest_path),
        ],
        cwd=plan.worktree,
        env=_environment(plan),
        code=STAGE_B_RUNNER_INSTALL_FAILED,
    )


def run_checks(plan: StageBPlan) -> None:
    """지정 검사를 돈다. 목록은 보호된 잠금에서 온 것이며 여기서 고르지 않는다."""
    if not plan.python_tests:
        raise StageBRunnerError(STAGE_B_RUNNER_PLAN_INVALID, "python 검사 목록이 비었다")
    if not plan.javascript_tests:
        raise StageBRunnerError(STAGE_B_RUNNER_PLAN_INVALID, "javascript 검사 목록이 비었다")
    env = _environment(plan)

    _run(
        [plan.python_executable, "-m", "pytest", "-q", *plan.python_tests],
        cwd=plan.worktree,
        env=env,
        code=STAGE_B_RUNNER_TESTS_FAILED,
    )

    relative = [
        path[len("butler-desktop/"):] if path.startswith("butler-desktop/") else path
        for path in plan.javascript_tests
    ]
    _run(
        ["npm", "--prefix", "butler-desktop", "ci"],
        cwd=plan.worktree, env=env, code=STAGE_B_RUNNER_INSTALL_FAILED,
    )
    _run(
        ["npm", "--prefix", "butler-desktop", "exec", "--", "vitest", "run", *relative],
        cwd=plan.worktree, env=env, code=STAGE_B_RUNNER_TESTS_FAILED,
    )


SELFTEST_SUMMARY_FILENAME = "ac25-selftest.json"
JUNIT_FILENAME = "ac25-junit.xml"

STAGE_B_SELFTEST_SKIPPED_NOT_ZERO = "STAGE_B_SELFTEST_SKIPPED_NOT_ZERO"
STAGE_B_SELFTEST_FAILED = "STAGE_B_SELFTEST_FAILED"
STAGE_B_SELFTEST_NO_TESTS = "STAGE_B_SELFTEST_NO_TESTS"
STAGE_B_SELFTEST_JUNIT_UNREADABLE = "STAGE_B_SELFTEST_JUNIT_UNREADABLE"


def _report_directory() -> Path:
    runner_temp = os.environ.get("RUNNER_TEMP")
    return Path(runner_temp) if runner_temp else Path(tempfile.gettempdir())


def run_selftest(plan: StageBPlan) -> dict:
    """검증기 자신의 시험을 돌리고 ★JUnit 으로 독립 확인★ 한다(§12).

    시험 설정 파일의 skip 금지 장치만으로 skipped 0 을 주장하지 않는다.
    그 장치가 지워져도 여기서 잡혀야 한다.
    """
    import hashlib
    import xml.etree.ElementTree as ElementTree

    reports = _report_directory()
    reports.mkdir(parents=True, exist_ok=True)
    junit = reports / JUNIT_FILENAME

    subprocess.run(
        [
            plan.python_executable, "-m", "pytest",
            str(plan.trusted_root / "tests" / "box5_ac25"),
            f"--junitxml={junit}", "-q",
        ],
        cwd=str(plan.trusted_root),
        env=_environment(plan),
        check=False,
    )

    if not junit.is_file():
        raise StageBRunnerError(STAGE_B_SELFTEST_JUNIT_UNREADABLE, str(junit.name))
    raw = junit.read_bytes()
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise StageBRunnerError(STAGE_B_SELFTEST_JUNIT_UNREADABLE, type(exc).__name__) from exc

    suites = list(root.iter("testsuite")) if root.tag == "testsuites" else [root]
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, "0") or 0)

    summary = {
        "tests_total": totals["tests"],
        "tests_failed": totals["failures"] + totals["errors"],
        "tests_skipped": totals["skipped"],
        "tests_passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"],
        "junit_sha256": hashlib.sha256(raw).hexdigest(),
    }
    (reports / SELFTEST_SUMMARY_FILENAME).write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    if totals["tests"] <= 0:
        raise StageBRunnerError(STAGE_B_SELFTEST_NO_TESTS, "0")
    if totals["skipped"] != 0:
        raise StageBRunnerError(STAGE_B_SELFTEST_SKIPPED_NOT_ZERO, str(totals["skipped"]))
    if summary["tests_failed"] != 0:
        raise StageBRunnerError(STAGE_B_SELFTEST_FAILED, str(summary["tests_failed"]))
    return summary


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AC-25 단계 B 보호 runner")
    parser.add_argument("--trusted-root", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument(
        "--mode", required=True,
        choices=("plan", "install", "test", "install-and-test", "smoke"),
    )
    args = parser.parse_args(argv)

    try:
        plan = build_plan(
            trusted_root=Path(args.trusted_root),
            worktree=Path(args.worktree),
            # ★단계 B 는 두 자리를 반드시 나눈다. smoke 만 자기시험이라 같다.
            require_separate_roots=args.mode != "smoke",
        )
        if args.mode in ("install", "install-and-test", "smoke"):
            install(plan)
        if args.mode in ("test", "install-and-test"):
            run_checks(plan)
        if args.mode == "smoke":
            run_selftest(plan)
    except (StageBRunnerError, DependencyManifestError) as exc:
        # ★meta-only(§9): 코드 하나만 낸다
        print("VERDICT=0")
        print(f"ERROR_CODE={exc.code}")
        return 1
    print("VERDICT=1")
    print("ERROR_CODE=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "JUNIT_FILENAME",
    "SELFTEST_SUMMARY_FILENAME",
    "STAGE_B_RUNNER_INSTALL_FAILED",
    "STAGE_B_RUNNER_PLAN_INVALID",
    "STAGE_B_RUNNER_TESTS_FAILED",
    "STAGE_B_RUNNER_WORKTREE_INVALID",
    "StageBPlan",
    "StageBRunnerError",
    "build_plan",
    "install",
    "run_checks",
    "run_selftest",
]
