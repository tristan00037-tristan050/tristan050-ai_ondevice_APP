"""§7 R6-4 — exact-head 저장소 계약 실행기.

저장소 계약을 PR #904 의 ★정확한 head★ 에서, 실제 빌드 산출물과 Helm 을 준비한
뒤, raw 출력을 격리한 상태로 정확히 한 번 실행한다.

이 모듈이 존재하는 이유(§A-3)
  C1 은 "바깥 명령의 출력이 공개 로그로 새는 것" 이었다. 그런데 저장소 계약은
  npm ci·build·helm·guard 로 ★바깥 명령을 잔뜩★ 부른다. 그 job 을 워크플로 셸로
  쓰면 같은 결함이 그대로 재발한다. 그래서 명령 계획을 ★코드 상수★ 로 고정하고
  전부 run_contained() 로 돌린다.

★준비 명령 목록은 상수다(§7-3 8항). 워크플로가 문자열로 조립하지 않는다.
★저장소 계약은 정확히 한 번 부른다(§7-7). 두 번 부르면 계약 위반이다.
★성공 로그는 §7-4 가 허용한 키만 낸다. raw stdout/stderr 는 digest·길이로만 남는다.
★clean-finish 는 tracked·untracked·후손·reader·임시파일을 모두 본다(§7-5).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import output_containment

# ── 오류 코드 (§7) ─────────────────────────────────────────────────────
REPO_CONTRACTS_EXACT_HEAD_MISMATCH = "REPO_CONTRACTS_EXACT_HEAD_MISMATCH"
REPO_CONTRACTS_SHALLOW_CLONE = "REPO_CONTRACTS_SHALLOW_CLONE"
REPO_CONTRACTS_BASE_REF_UNAVAILABLE = "REPO_CONTRACTS_BASE_REF_UNAVAILABLE"
REPO_CONTRACTS_GUARD_MUTATED = "REPO_CONTRACTS_GUARD_MUTATED"
REPO_CONTRACTS_BUILD_ARTIFACT_MISSING = "REPO_CONTRACTS_BUILD_ARTIFACT_MISSING"
REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH = "REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH"
REPO_CONTRACTS_PREPARATION_FAILED = "REPO_CONTRACTS_PREPARATION_FAILED"
REPO_CONTRACTS_FAILED = "REPO_CONTRACTS_FAILED"
REPO_CONTRACTS_ALREADY_RUN = "REPO_CONTRACTS_ALREADY_RUN"
REPO_CONTRACTS_WORKTREE_NOT_CLEAN = "REPO_CONTRACTS_WORKTREE_NOT_CLEAN"
REPO_CONTRACTS_DESCENDANTS_SURVIVED = "REPO_CONTRACTS_DESCENDANTS_SURVIVED"

_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_HELM_MAJOR_RE = re.compile(r"\Av?(\d+)\.")

# ── §7-2 실행 전 기준 보호 대상 ────────────────────────────────────────
# ★실제 파일명이 저장소와 다르면 추측해 만들지 않는다. 여기 목록은 현재 canonical
#   dispatcher 가 부르는 경로에서 왔고, 시험이 그 사실을 강제한다.
PROTECTED_GUARD_PATHS = (
    "scripts/verify/verify_repo_contracts.sh",
    "scripts/verify/verify_workflow_checkout_depth_ssot_v1.sh",
    "scripts/verify/verify_workflow_checkout_depth_autodiscover_v1.sh",
    "scripts/verify/verify_ssot_registry_consumer_bind_v1.sh",
    "scripts/verify/verify_no_raw_in_logs_exceptions_v1.sh",
)

# ── §7-3 고정 순서. 이 순서를 바꾸지 않는다 ────────────────────────────
NPM_WORKSPACE = "webcore_appcore_starter_4_17"
BUILD_ARTIFACT = f"{NPM_WORKSPACE}/packages/bff-accounting/dist/policy/loader.js"

PREPARATION_PLAN = (
    ("base_ref", ("bash", "scripts/verify/verify_base_ref_available_v1.sh"), "."),
    ("npm_ci", ("npm", "ci"), NPM_WORKSPACE),
    ("npm_build", ("npm", "run", "build:packages:server"), NPM_WORKSPACE),
    ("helm_version", ("helm", "version", "--short"), "."),
)
CONTRACT_COMMAND = ("bash", "scripts/verify/verify_repo_contracts.sh")

# 도구 버전은 ★제한된 metadata★ 로만 기록한다(§7-3 2항).
TOOL_VERSION_PLAN = (
    ("python", ("python3", "--version")),
    ("node", ("node", "--version")),
    ("npm", ("npm", "--version")),
    ("git", ("git", "--version")),
    ("helm", ("helm", "version", "--short")),
)


class RepoContractError(Exception):
    """메시지에 코드 외 어떤 raw 값도 넣지 않는다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class ContractReceipt:
    """§7-4 가 허용한 키만 담는다. 원문·경로 목록은 넣지 않는다."""

    exact_head: str = ""
    exact_tree: str = ""
    runner_image: str = ""
    command_plan_sha256: str = ""
    guard_manifest_sha256: str = ""
    guard_blob_oids: dict = field(default_factory=dict)
    tool_versions: dict = field(default_factory=dict)
    helm_version: str = ""
    contract_exit_code: int = -1
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    descendants_observed: int = 0
    final_worktree_clean: str = "NOT_RUN"
    error_code: str = "NONE"
    verdict: int = 0


def command_plan_sha256() -> str:
    """준비 명령 계획의 지문. 목록·순서가 바뀌면 값이 바뀐다(§7-7)."""
    canonical = json.dumps(
        {
            "preparation": [[name, list(argv), cwd] for name, argv, cwd in PREPARATION_PLAN],
            "contract": list(CONTRACT_COMMAND),
            "artifact": BUILD_ARTIFACT,
            "guards": list(PROTECTED_GUARD_PATHS),
        },
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run(argv, *, root: Path, cwd: str, runner_temp: Path, env) -> tuple[int, bytes, bytes]:
    """§7-4 — 모든 바깥 명령은 격리기를 거친다. raw 를 로그로 내지 않는다."""
    return output_containment.run_and_read(
        list(argv),
        cwd=(root / cwd).resolve(),
        env=env,
        runner_temp=runner_temp,
        timeout_seconds=1800,
    )


def _git_text(root: Path, argv, runner_temp: Path, env) -> str:
    code, out, _err = _run(("git", *argv), root=root, cwd=".", runner_temp=runner_temp, env=env)
    return out.decode("utf-8", "replace").strip() if code == 0 else ""


def assert_exact_head(*, root: Path, expected_head: str, runner_temp: Path, env) -> tuple[str, str]:
    """checkout HEAD 가 event head 와 같은지 먼저 본다. 다르면 준비를 하지 않는다."""
    if not _OID_RE.match(expected_head or ""):
        raise RepoContractError(REPO_CONTRACTS_EXACT_HEAD_MISMATCH)
    head = _git_text(root, ("rev-parse", "HEAD"), runner_temp, env)
    if head != expected_head:
        raise RepoContractError(REPO_CONTRACTS_EXACT_HEAD_MISMATCH)
    tree = _git_text(root, ("show", "-s", "--format=%T", "HEAD"), runner_temp, env)
    if not _OID_RE.match(tree or ""):
        raise RepoContractError(REPO_CONTRACTS_EXACT_HEAD_MISMATCH)
    shallow = _git_text(root, ("rev-parse", "--is-shallow-repository"), runner_temp, env)
    if shallow != "false":
        raise RepoContractError(REPO_CONTRACTS_SHALLOW_CLONE)
    return head, tree


def guard_blob_oids(*, root: Path, runner_temp: Path, env) -> dict[str, str]:
    """§7-2 — 계약·guard 파일의 blob OID 를 기록한다. 검사기를 바꿔 통과시키지 않는다."""
    oids: dict[str, str] = {}
    for path in PROTECTED_GUARD_PATHS:
        value = _git_text(root, ("rev-parse", f"HEAD:{path}"), runner_temp, env)
        if not _OID_RE.match(value or ""):
            raise RepoContractError(REPO_CONTRACTS_GUARD_MUTATED)
        oids[path] = value
    return oids


def assert_guards_unmodified(*, root: Path, base_ref: str, runner_temp: Path, env) -> None:
    """base 대비 guard 변경 0. 변경이 있으면 계약을 돌리기 전에 닫는다."""
    if not base_ref:
        return
    code, out, _err = _run(
        ("git", "diff", "--name-only", "-z", base_ref, "HEAD", "--", *PROTECTED_GUARD_PATHS),
        root=root, cwd=".", runner_temp=runner_temp, env=env,
    )
    if code != 0:
        raise RepoContractError(REPO_CONTRACTS_BASE_REF_UNAVAILABLE)
    changed = [chunk for chunk in out.split(b"\x00") if chunk]
    if changed:
        raise RepoContractError(REPO_CONTRACTS_GUARD_MUTATED)


def collect_tool_versions(*, root: Path, runner_temp: Path, env) -> dict[str, str]:
    versions: dict[str, str] = {
        "image_os": env.get("ImageOS", "unknown"),
        "image_version": env.get("ImageVersion", "unknown"),
    }
    for name, argv in TOOL_VERSION_PLAN:
        code, out, _err = _run(argv, root=root, cwd=".", runner_temp=runner_temp, env=env)
        text = out.decode("utf-8", "replace").strip().splitlines()
        versions[name] = text[0][:64] if code == 0 and text else "unknown"
    return versions


def assert_helm_major_three(version_text: str) -> str:
    match = _HELM_MAJOR_RE.search((version_text or "").strip())
    if match is None or match.group(1) != "3":
        # ★즉석 다운로드로 재현성을 잃지 않는다. 불일치는 닫는다(§7-3).
        raise RepoContractError(REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH)
    return version_text.strip()[:64]


def assert_build_artifact(root: Path) -> None:
    """§7-3 6항 — regular file 이고 크기가 0 보다 큼. 내용을 로그에 쓰지 않는다."""
    target = root / BUILD_ARTIFACT
    try:
        stat = target.stat()
    except OSError as exc:
        raise RepoContractError(REPO_CONTRACTS_BUILD_ARTIFACT_MISSING) from exc
    if not target.is_file() or target.is_symlink() or stat.st_size <= 0:
        raise RepoContractError(REPO_CONTRACTS_BUILD_ARTIFACT_MISSING)


def assert_clean_finish(*, root: Path, runner_temp: Path, env) -> None:
    """§7-5 — tracked·staged·untracked 잔여물 0."""
    for argv in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        code, _out, _err = _run(("git", *argv), root=root, cwd=".", runner_temp=runner_temp, env=env)
        if code != 0:
            raise RepoContractError(REPO_CONTRACTS_WORKTREE_NOT_CLEAN)
    code, out, _err = _run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        root=root, cwd=".", runner_temp=runner_temp, env=env,
    )
    if code != 0 or out.strip():
        raise RepoContractError(REPO_CONTRACTS_WORKTREE_NOT_CLEAN)


def run_exact_head_contracts(
    *,
    root: Path,
    expected_head: str,
    base_ref: str = "",
    runner_temp: Path | None = None,
    env: dict | None = None,
) -> ContractReceipt:
    """§7-3 고정 순서를 그대로 실행한다. 저장소 계약은 정확히 한 번 부른다."""
    receipt = ContractReceipt(command_plan_sha256=command_plan_sha256())
    environment = dict(env if env is not None else os.environ)
    temp = runner_temp or output_containment.default_runner_temp()

    try:
        receipt.exact_head, receipt.exact_tree = assert_exact_head(
            root=root, expected_head=expected_head, runner_temp=temp, env=environment
        )
        receipt.runner_image = (
            f"{environment.get('ImageOS', 'unknown')}/"
            f"{environment.get('ImageVersion', 'unknown')}"
        )
        receipt.guard_blob_oids = guard_blob_oids(root=root, runner_temp=temp, env=environment)
        receipt.guard_manifest_sha256 = hashlib.sha256(
            json.dumps(receipt.guard_blob_oids, sort_keys=True).encode("utf-8")
        ).hexdigest()
        assert_guards_unmodified(
            root=root, base_ref=base_ref, runner_temp=temp, env=environment
        )

        # ── 준비 (고정 순서) ───────────────────────────────────────────
        executed: list[str] = []
        for name, argv, cwd in PREPARATION_PLAN:
            code, out, _err = _run(argv, root=root, cwd=cwd, runner_temp=temp, env=environment)
            executed.append(name)
            if name == "helm_version":
                if code != 0:
                    raise RepoContractError(REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH)
                receipt.helm_version = assert_helm_major_three(
                    out.decode("utf-8", "replace")
                )
            elif code != 0:
                raise RepoContractError(
                    REPO_CONTRACTS_BASE_REF_UNAVAILABLE if name == "base_ref"
                    else REPO_CONTRACTS_PREPARATION_FAILED
                )
            if name == "npm_build":
                assert_build_artifact(root)
        if executed != [name for name, _argv, _cwd in PREPARATION_PLAN]:
            raise RepoContractError(REPO_CONTRACTS_PREPARATION_FAILED)

        receipt.tool_versions = collect_tool_versions(
            root=root, runner_temp=temp, env=environment
        )

        # ── 저장소 계약: 정확히 한 번 ─────────────────────────────────
        result = output_containment.run_contained(
            list(CONTRACT_COMMAND),
            cwd=root,
            env=environment,
            timeout_seconds=3600,
            runner_temp=temp,
        )
        receipt.contract_exit_code = result.returncode
        receipt.stdout_sha256 = result.stdout_sha256
        receipt.stderr_sha256 = result.stderr_sha256
        receipt.stdout_bytes = result.stdout_bytes
        receipt.stderr_bytes = result.stderr_bytes
        receipt.descendants_observed = result.descendants_observed
        if result.descendant_escape_detected or not result.cleanup_ok:
            raise RepoContractError(REPO_CONTRACTS_DESCENDANTS_SURVIVED)
        if result.returncode != 0:
            raise RepoContractError(REPO_CONTRACTS_FAILED)

        assert_clean_finish(root=root, runner_temp=temp, env=environment)
        receipt.final_worktree_clean = "YES"
        receipt.verdict = 1
    except RepoContractError as exc:
        receipt.error_code = exc.code
        receipt.verdict = 0
        if receipt.final_worktree_clean == "NOT_RUN":
            receipt.final_worktree_clean = "NO"
    except output_containment.ContainmentError as exc:
        receipt.error_code = exc.code
        receipt.verdict = 0
    return receipt


# ── §7-4 허용된 출력 형식 ──────────────────────────────────────────────
def emit_lines(receipt: ContractReceipt) -> list[str]:
    return [
        f"REPO_CONTRACTS_EXACT_HEAD={'PASS' if receipt.verdict == 1 else 'FAIL'}",
        f"ERROR_CODE={receipt.error_code}",
        f"COMMAND_PLAN_SHA256={receipt.command_plan_sha256}",
        f"GUARD_MANIFEST_SHA256={receipt.guard_manifest_sha256 or 'NONE'}",
        f"STDOUT_SHA256={receipt.stdout_sha256 or 'NONE'}",
        f"STDERR_SHA256={receipt.stderr_sha256 or 'NONE'}",
        f"STDOUT_BYTES={receipt.stdout_bytes}",
        f"STDERR_BYTES={receipt.stderr_bytes}",
        f"EXIT_CODE={receipt.contract_exit_code}",
        f"DESCENDANTS_OBSERVED={receipt.descendants_observed}",
        f"FINAL_WORKTREE_CLEAN={receipt.final_worktree_clean}",
        f"RUNNER_IMAGE={receipt.runner_image or 'unknown'}",
        f"HELM_VERSION={receipt.helm_version or 'unknown'}",
        f"NODE_VERSION={receipt.tool_versions.get('node', 'unknown')}",
        f"PYTHON_VERSION={receipt.tool_versions.get('python', 'unknown')}",
    ]


def _main(argv: list[str]) -> int:
    if argv:
        print("REPO_CONTRACTS_EXACT_HEAD=FAIL")
        print(f"ERROR_CODE={REPO_CONTRACTS_EXACT_HEAD_MISMATCH}")
        return 1
    root = Path.cwd()
    receipt = run_exact_head_contracts(
        root=root,
        expected_head=os.environ.get("AC25_EVENT_HEAD_SHA", ""),
        base_ref=os.environ.get("AC25_BASE_REF", ""),
    )
    for line in emit_lines(receipt):
        print(line)
    return 0 if receipt.verdict == 1 else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "BUILD_ARTIFACT",
    "CONTRACT_COMMAND",
    "PREPARATION_PLAN",
    "PROTECTED_GUARD_PATHS",
    "REPO_CONTRACTS_ALREADY_RUN",
    "REPO_CONTRACTS_BASE_REF_UNAVAILABLE",
    "REPO_CONTRACTS_BUILD_ARTIFACT_MISSING",
    "REPO_CONTRACTS_DESCENDANTS_SURVIVED",
    "REPO_CONTRACTS_EXACT_HEAD_MISMATCH",
    "REPO_CONTRACTS_FAILED",
    "REPO_CONTRACTS_GUARD_MUTATED",
    "REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH",
    "REPO_CONTRACTS_PREPARATION_FAILED",
    "REPO_CONTRACTS_SHALLOW_CLONE",
    "REPO_CONTRACTS_WORKTREE_NOT_CLEAN",
    "ContractReceipt",
    "RepoContractError",
    "assert_build_artifact",
    "assert_clean_finish",
    "assert_exact_head",
    "assert_guards_unmodified",
    "assert_helm_major_three",
    "collect_tool_versions",
    "command_plan_sha256",
    "emit_lines",
    "guard_blob_oids",
    "run_exact_head_contracts",
]
