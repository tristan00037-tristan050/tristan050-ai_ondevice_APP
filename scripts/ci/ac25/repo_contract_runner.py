"""R6-4 — exact-head 저장소 계약 실행기. v3.1 §3·§4·§5 판.

이전 판에서 무엇이 틀렸었나(v3.1 §1)

    · 계약이 실패하면 clean 검사를 ★실행하기 전에★ 예외 처리에서 `NOT_RUN` 을
      일괄 `NO` 로 바꿨다. 그 `NO` 는 "더러웠다" 가 아니라 "재지 않았다" 였다.
      재지 않은 값이 원인 단정의 근거가 됐다.
    · canonical 비교가 누락만 찾고 추가를 허용했다. 상위집합이 통과했다.
    · canonical 에 없는 npm ci·build·helm 세 명령을 준비에 더했다.

이 판

    · 준비는 canonical 추출 ★그대로★ 다. 추가 명령 0(§3-4).
    · 동등성은 다섯 축(missing·extra·reordered·mutated·unsupported) 전부 0
      일 때만 성립하고, 아니면 계약을 실행하지 않는다.
    · clean 은 ★실측 tri-state★ 다 — YES/NO/NOT_EVALUATED 를 서로 바꾸지
      않는다(§2·§4). P0~P3 시점마다 재고, 정리로 통과시키지 않는다(§4-3).
    · 계약 출력은 contract_parse 가 손실 없이 구조화한다(§5).

★저장소 계약은 정확히 한 번 부른다. raw stdout/stderr 는 지문·길이로만 남는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

from . import canonical_plan, contract_parse, contract_state, output_containment

# ── 오류 코드 ──────────────────────────────────────────────────────────
REPO_CONTRACTS_EXACT_HEAD_MISMATCH = "REPO_CONTRACTS_EXACT_HEAD_MISMATCH"
REPO_CONTRACTS_SHALLOW_CLONE = "REPO_CONTRACTS_SHALLOW_CLONE"
REPO_CONTRACTS_BASE_REF_UNAVAILABLE = "REPO_CONTRACTS_BASE_REF_UNAVAILABLE"
REPO_CONTRACTS_GUARD_MUTATED = "REPO_CONTRACTS_GUARD_MUTATED"
REPO_CONTRACTS_PREPARATION_FAILED = "REPO_CONTRACTS_PREPARATION_FAILED"
REPO_CONTRACTS_FAILED = "REPO_CONTRACTS_FAILED"
REPO_CONTRACTS_DESCENDANTS_SURVIVED = "REPO_CONTRACTS_DESCENDANTS_SURVIVED"
# §3-4 고정 코드
REPO_CONTRACTS_CANONICAL_PLAN_UNREADABLE = "REPO_CONTRACTS_CANONICAL_PLAN_UNREADABLE"
REPO_CONTRACTS_CANONICAL_PLAN_UNSUPPORTED = "REPO_CONTRACTS_CANONICAL_PLAN_UNSUPPORTED"
REPO_CONTRACTS_CANONICAL_PLAN_MISSING = "REPO_CONTRACTS_CANONICAL_PLAN_MISSING"
REPO_CONTRACTS_CANONICAL_PLAN_EXTRA = "REPO_CONTRACTS_CANONICAL_PLAN_EXTRA"
REPO_CONTRACTS_CANONICAL_PLAN_REORDERED = "REPO_CONTRACTS_CANONICAL_PLAN_REORDERED"
REPO_CONTRACTS_CANONICAL_PLAN_MUTATED = "REPO_CONTRACTS_CANONICAL_PLAN_MUTATED"
REPO_CONTRACTS_CANONICAL_ACTION_MISMATCH = "REPO_CONTRACTS_CANONICAL_ACTION_MISMATCH"
# §4 clean 실측
REPO_CONTRACTS_PREEXISTING_WORKTREE_DIRTY = "REPO_CONTRACTS_PREEXISTING_WORKTREE_DIRTY"
CLEAN_CHECK_COMMAND_FAILED = "CLEAN_CHECK_COMMAND_FAILED"
CLEAN_OUTPUT_INVALID = "CLEAN_OUTPUT_INVALID"
CLEAN_PATH_INVALID = "CLEAN_PATH_INVALID"
# §5 출력 모순
REPO_CONTRACTS_OUTPUT_CONTRADICTORY = "REPO_CONTRACTS_OUTPUT_CONTRADICTORY"
REPO_CONTRACTS_OUTPUT_INVALID = "REPO_CONTRACTS_OUTPUT_INVALID"
OUTPUT_ROOT_POLICY_VIOLATION = "OUTPUT_ROOT_POLICY_VIOLATION"
ERRATUM_2_DIGEST_MISMATCH = "ERRATUM_2_DIGEST_MISMATCH"

ERRATUM_2_PATH = "docs/box5/ac25/ac25-r6-erratum-2.json"
ERRATUM_2_SHA256 = "2ed584f139227a454c821729c44586fd628d8f0239b61700fae62cc7d7c185db"

_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_STATUS_RE = re.compile(r"\A[ MADRCUT?!]{2}\Z")
# 공개 로그에 내도 안전한 경로 문자만. 벗어나면 지문·개수로만 증명한다(§4-2).
_SAFE_PATH_RE = re.compile(r"\A[A-Za-z0-9_./+-]{1,200}\Z")
_DIRTY_PATH_LOG_LIMIT = 20
_DIRTY_PATH_LOG_BYTES = 4096
_FAILING_KEYS_LOG_BYTES = 2048

# ── §7-2 실행 전 기준 보호 대상 ────────────────────────────────────────
PROTECTED_GUARD_PATHS = (
    "scripts/verify/verify_repo_contracts.sh",
    "scripts/verify/verify_workflow_checkout_depth_ssot_v1.sh",
    "scripts/verify/verify_workflow_checkout_depth_autodiscover_v1.sh",
    "scripts/verify/verify_ssot_registry_consumer_bind_v1.sh",
    "scripts/verify/verify_no_raw_in_logs_exceptions_v1.sh",
)
# v4.4 explicitly changes the contract entrypoint and executes that exact-head
# candidate. Its blob remains measured above; the unchanged helper guards keep
# the base-equality restriction during Phase A.
MUTATION_FORBIDDEN_GUARD_PATHS = PROTECTED_GUARD_PATHS[1:]

CONTRACT_COMMAND = ("bash", "scripts/verify/verify_repo_contracts.sh")
BASE_REF_SCRIPT = "scripts/verify/verify_base_ref_available_v1.sh"

# 도구 버전은 ★비변형 observation★ 으로만 기록한다(§3-3 (3) allowlist).
TOOL_VERSION_PLAN = (
    ("python", ("python3", "--version")),
    ("node", ("node", "--version")),
    ("npm", ("npm", "--version")),
    ("git", ("git", "--version")),
    ("helm", ("helm", "version", "--short")),
)


def build_preparation_plan(
    root: Path, *, runner_temp: str = "/tmp"
) -> tuple[canonical_plan.CanonicalRunStep, ...]:
    """★준비 계획 = canonical 추출 그대로. 추가 명령 0 이다(§3-4).

    v3.0 이 더했던 상위 workspace 설치·빌드·helm 세 명령은 제거됐다.
    제거의 근거는 "그것 때문에 실패했다" 가 아니라 "canonical 에 없는 것을
    더하지 않기로 정했다" 이다(제1부 §C).
    제거 후에도 계약이 실패할 수 있다. 그러면 그 실패를 그대로 보고한다.
    """
    plan = canonical_plan.extract_canonical_plan(root, runner_temp=runner_temp)
    return plan.preparation


def build_execution_plan(
    root: Path, *, runner_temp: str = "/tmp"
) -> canonical_plan.ExecutionPlan:
    """실행 측 전체 — 준비 run + exact-head job 이 선언한 action·harness."""
    actions, harness = canonical_plan.extract_execution_workflow(
        root, runner_temp=runner_temp
    )
    return canonical_plan.ExecutionPlan(
        runs=build_preparation_plan(root, runner_temp=runner_temp),
        actions=actions,
        harness=harness,
    )


def contract_environment(
    root: Path, *, base_env: dict, runner_temp: str
) -> dict[str, str]:
    """계약에 넘길 환경변수도 canonical 에서 읽는다. 같은 스크립트라도
    다른 환경에서 돌면 같은 검사가 아니다."""
    plan = canonical_plan.extract_canonical_plan(root, runner_temp=runner_temp)
    merged = dict(base_env)
    for key, value in plan.contract_env:
        merged[key] = value
    return merged


class RepoContractError(Exception):
    """메시지에 코드 외 어떤 raw 값도 넣지 않는다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class DirtyPathEvidence:
    path: str
    first_phase: str
    plan_step_sha256: str
    head_blob_oid: str
    after_sha256: str
    mode: str
    status: str


@dataclass
class ContractReceipt:
    """§13 이 요구하는 키만 담는다. 원문은 담지 않는다."""

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
    canonical_workflow_sha256: str = ""
    canonical_step_count: int = 0
    # §3-4 다섯 축
    plan_missing: list = field(default_factory=list)
    plan_extra: list = field(default_factory=list)
    plan_reordered: list = field(default_factory=list)
    plan_mutated: list = field(default_factory=list)
    plan_unsupported: list = field(default_factory=list)
    contract_env_keys: list = field(default_factory=list)
    preparation_env_keys: list = field(default_factory=list)
    # §4 clean 실측 — NOT_EVALUATED 를 NO 로 바꾸지 않는다
    clean_check_executed: bool = False
    final_worktree_clean: str = "NOT_EVALUATED"
    dirty_path_count: int = 0
    dirty_path_manifest_sha256: str = ""
    dirty_paths: tuple = ()
    dirty_path_evidence: dict[str, DirtyPathEvidence] = field(default_factory=dict)
    clean_check_error_code: str = "NONE"
    first_dirty_phase: str = "NOT_EVALUATED"
    declared_canonical_output_policy: str = "WAITING_ERRATUM_2"
    # §5 guard 증거
    contract_key_count: int = 0
    primary_failed_guard: str = "NOT_RUN"
    primary_failed_guard_line_sha256: str = ""
    primary_failed_guard_line_bytes: int = 0
    failing_guard_keys: tuple = ()
    contract_block_lines: tuple = ()
    contract_unparsed_line_count: int = 0
    contract_unparsed_total_bytes: int = 0
    contract_unparsed_manifest_sha256: str = ""
    contract_parse_error_code: str = "NOT_RUN"
    contract_state_outcome: str = "NOT_RUN"
    contract_state_error_code: str = "NOT_RUN"
    raw_clean_status_exit_code: int = -1
    raw_clean_status_sha256: str = ""
    raw_clean_status_bytes: int = 0
    error_code: str = "NONE"
    verdict: int = 0


def _evidence_root(root: Path, environment: dict[str, str]) -> Path | None:
    configured = environment.get("AC25_CONTRACT_EVIDENCE_ROOT", "")
    if not configured:
        return None
    candidate = Path(configured)
    if not candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts[1:]):
        raise RepoContractError(OUTPUT_ROOT_POLICY_VIOLATION)
    repository = root.resolve()
    try:
        candidate.relative_to(repository)
    except ValueError:
        pass
    else:
        raise RepoContractError(OUTPUT_ROOT_POLICY_VIOLATION)
    try:
        candidate.mkdir(mode=0o700)
    except FileExistsError:
        pass
    try:
        mode = candidate.lstat().st_mode
        descriptor = os.open(candidate, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, AttributeError) as exc:
        raise RepoContractError(OUTPUT_ROOT_POLICY_VIOLATION) from exc
    try:
        if not stat.S_ISDIR(mode):
            raise RepoContractError(OUTPUT_ROOT_POLICY_VIOLATION)
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    return candidate


def _write_private(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)
    path.chmod(0o600)


def _bind_erratum_2(root: Path, receipt: ContractReceipt) -> None:
    try:
        raw = (root / ERRATUM_2_PATH).read_bytes()
    except OSError as exc:
        raise RepoContractError(ERRATUM_2_DIGEST_MISMATCH) from exc
    if hashlib.sha256(raw).hexdigest() != ERRATUM_2_SHA256:
        raise RepoContractError(ERRATUM_2_DIGEST_MISMATCH)
    receipt.declared_canonical_output_policy = "OUTSIDE_REPOSITORY_ONLY"


def command_plan_sha256(root: Path | None = None, *, runner_temp: str = "/tmp") -> str:
    """준비·action·harness·계약 전체 계획의 지문. 무엇이 바뀌어도 값이 바뀐다."""
    source = root or Path(__file__).resolve().parents[3]
    extracted = canonical_plan.extract_canonical_plan(source, runner_temp=runner_temp)
    execution = build_execution_plan(source, runner_temp=runner_temp)
    payload = json.dumps(
        {
            "preparation": [step.as_dict() for step in execution.runs],
            "actions": [step.as_dict() for step in execution.actions],
            "harness": [step.as_dict() for step in execution.harness],
            "contract": list(CONTRACT_COMMAND),
            "contract_env_keys": sorted(key for key, _value in extracted.contract_env),
            "guards": list(PROTECTED_GUARD_PATHS),
            "canonical_workflow_sha256": extracted.workflow_sha256,
        },
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run(argv, *, root: Path, cwd: str, runner_temp: Path, env) -> tuple[int, bytes, bytes]:
    """모든 바깥 명령은 격리기를 거친다. raw 를 로그로 내지 않는다."""
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
    """§7-2 — 계약·guard 파일의 blob OID 를 기록한다(read-only git 조회)."""
    oids: dict[str, str] = {}
    for path in PROTECTED_GUARD_PATHS:
        value = _git_text(root, ("rev-parse", f"HEAD:{path}"), runner_temp, env)
        if not _OID_RE.match(value or ""):
            raise RepoContractError(REPO_CONTRACTS_GUARD_MUTATED)
        oids[path] = value
    return oids


def assert_guards_unmodified(*, root: Path, base_ref: str, runner_temp: Path, env) -> None:
    """Reject base drift in helper guards outside the authorized v4.4 delta."""
    if not base_ref:
        return
    code, out, _err = _run(
        (
            "git", "diff", "--name-only", "-z", base_ref, "HEAD", "--",
            *MUTATION_FORBIDDEN_GUARD_PATHS,
        ),
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


# ── §4 clean 실측 ──────────────────────────────────────────────────────
def _validate_dirty_path(raw: bytes) -> str:
    """NUL 구분 Git 출력의 경로 하나를 검증한다. 위반은 예외로 닫는다(§4-2)."""
    try:
        path = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RepoContractError(CLEAN_PATH_INVALID) from exc
    if not path or path.startswith("/"):
        raise RepoContractError(CLEAN_PATH_INVALID)
    if any(part == ".." for part in path.split("/")):
        raise RepoContractError(CLEAN_PATH_INVALID)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in path):
        raise RepoContractError(CLEAN_PATH_INVALID)
    return path


def clean_snapshot_details(*, root: Path, runner_temp: Path, env) -> tuple[tuple[str, str], ...]:
    """`git status --porcelain=v1 -z --untracked-files=all` 을 격리 실행해
    dirty 경로의 정렬 목록을 낸다. ★관측만 한다. 정리하지 않는다(§4-3)."""
    code, out, _err = _run(
        ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
        root=root, cwd=".", runner_temp=runner_temp, env=env,
    )
    if code != 0:
        raise RepoContractError(CLEAN_CHECK_COMMAND_FAILED)
    entries: list[tuple[str, str]] = []
    tokens = out.split(b"\x00")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token:
            index += 1
            continue
        if len(token) < 4 or token[2:3] != b" ":
            raise RepoContractError(CLEAN_OUTPUT_INVALID)
        try:
            status = token[:2].decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise RepoContractError(CLEAN_OUTPUT_INVALID) from exc
        if _STATUS_RE.fullmatch(status) is None or status == "  ":
            raise RepoContractError(CLEAN_OUTPUT_INVALID)
        changed_path = _validate_dirty_path(token[3:])
        entries.append((changed_path, status))
        if status[:1] in ("R", "C"):
            # rename/copy 는 다음 token 이 원래 경로다 — 그것도 증거다
            index += 1
            if index >= len(tokens) or not tokens[index]:
                raise RepoContractError(CLEAN_OUTPUT_INVALID)
            entries.append((_validate_dirty_path(tokens[index]), status))
        index += 1
    if len({path for path, _status in entries}) != len(entries):
        raise RepoContractError(CLEAN_OUTPUT_INVALID)
    return tuple(sorted(entries))


def clean_snapshot(*, root: Path, runner_temp: Path, env) -> tuple[str, ...]:
    """Compatibility view containing only the observed paths."""
    return tuple(
        path
        for path, _status in clean_snapshot_details(
            root=root,
            runner_temp=runner_temp,
            env=env,
        )
    )


def dirty_manifest_sha256(paths: tuple[str, ...]) -> str:
    payload = json.dumps(
        {"paths": list(paths)}, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path_after_metadata(root: Path, path: str) -> tuple[str, str]:
    candidate = root / path
    try:
        file_stat = candidate.lstat()
    except OSError:
        return "NONE", "NONE"
    mode = f"{stat.S_IMODE(file_stat.st_mode):04o}"
    if candidate.is_symlink():
        payload = os.readlink(candidate).encode("utf-8", "surrogateescape")
    elif candidate.is_file():
        try:
            payload = candidate.read_bytes()
        except OSError:
            return "NONE", mode
    else:
        return "NONE", mode
    return hashlib.sha256(payload).hexdigest(), mode


def _observe_clean(
    receipt: ContractReceipt,
    phase: str,
    *,
    root,
    runner_temp,
    env,
    plan_step_sha256: str = "NONE",
) -> tuple[str, ...]:
    """한 시점의 clean 을 재고 첫 dirty 시점을 기록한다. 실패 판정은 하지 않는다."""
    details = clean_snapshot_details(root=root, runner_temp=runner_temp, env=env)
    dirty = tuple(path for path, _status in details)
    receipt.clean_check_executed = True
    for path, observed_status in details:
        previous = receipt.dirty_path_evidence.get(path)
        first_phase = previous.first_phase if previous is not None else phase
        first_plan_sha = (
            previous.plan_step_sha256 if previous is not None else plan_step_sha256
        )
        head_blob_oid = _git_text(
            root,
            ("rev-parse", f"HEAD:{path}"),
            runner_temp,
            env,
        )
        if _OID_RE.fullmatch(head_blob_oid or "") is None:
            head_blob_oid = "NONE"
        after_sha256, mode = _path_after_metadata(root, path)
        receipt.dirty_path_evidence[path] = DirtyPathEvidence(
            path=path,
            first_phase=first_phase,
            plan_step_sha256=first_plan_sha,
            head_blob_oid=head_blob_oid,
            after_sha256=after_sha256,
            mode=mode,
            status=observed_status,
        )
    if dirty and receipt.first_dirty_phase in ("NOT_EVALUATED", "NONE"):
        receipt.first_dirty_phase = phase
    return dirty


# ── §3-4 다섯 축 → 오류 코드 ───────────────────────────────────────────
def _diff_error_code(diff: canonical_plan.PlanDiff) -> str | None:
    if diff.exact:
        return None
    if diff.unsupported:
        return REPO_CONTRACTS_CANONICAL_PLAN_UNSUPPORTED
    action_labels = [
        item
        for bucket in (diff.missing, diff.extra, diff.reordered, diff.mutated)
        for item in bucket
        if item.startswith("action:")
    ]
    if action_labels:
        return REPO_CONTRACTS_CANONICAL_ACTION_MISMATCH
    if diff.missing:
        return REPO_CONTRACTS_CANONICAL_PLAN_MISSING
    if diff.extra:
        return REPO_CONTRACTS_CANONICAL_PLAN_EXTRA
    if diff.reordered:
        return REPO_CONTRACTS_CANONICAL_PLAN_REORDERED
    return REPO_CONTRACTS_CANONICAL_PLAN_MUTATED


def run_exact_head_contracts(
    *,
    root: Path,
    expected_head: str,
    base_ref: str = "",
    runner_temp: Path | None = None,
    env: dict | None = None,
) -> ContractReceipt:
    """§14 순서 그대로. 저장소 계약은 정확히 한 번 부른다."""
    environment = dict(env if env is not None else os.environ)
    temp = runner_temp or output_containment.default_runner_temp()
    receipt = ContractReceipt()
    head_confirmed = False
    evidence_root: Path | None = None

    try:
        try:
            evidence_root = _evidence_root(root, environment)
            # ── §3-4 — 동등성 게이트. 다섯 축 전부 0 이 아니면 실행하지 않는다.
            expected = canonical_plan.extract_canonical_plan(root, runner_temp=str(temp))
            execution = build_execution_plan(root, runner_temp=str(temp))
            receipt.command_plan_sha256 = command_plan_sha256(root, runner_temp=str(temp))
            receipt.canonical_workflow_sha256 = expected.workflow_sha256
            receipt.canonical_step_count = len(expected.preparation)
            receipt.preparation_env_keys = sorted({
                key for step in execution.runs for key, _value in step.env
            })
            diff = canonical_plan.compare_exact_plan(expected=expected, actual=execution)
            receipt.plan_missing = list(diff.missing)
            receipt.plan_extra = list(diff.extra)
            receipt.plan_reordered = list(diff.reordered)
            receipt.plan_mutated = list(diff.mutated)
            receipt.plan_unsupported = list(diff.unsupported)
            gate = _diff_error_code(diff)
            if gate is not None:
                raise RepoContractError(gate)

            _bind_erratum_2(root, receipt)

            receipt.exact_head, receipt.exact_tree = assert_exact_head(
                root=root, expected_head=expected_head, runner_temp=temp, env=environment
            )
            head_confirmed = True

            # P0 is the first post-identity observation.  Tool discovery must
            # never create a preexisting-clean false negative.
            if _observe_clean(receipt, "P0", root=root, runner_temp=temp, env=environment):
                raise RepoContractError(REPO_CONTRACTS_PREEXISTING_WORKTREE_DIRTY)

            receipt.runner_image = (
                f"{environment.get('ImageOS', 'unknown')}/"
                f"{environment.get('ImageVersion', 'unknown')}"
            )
            receipt.tool_versions = collect_tool_versions(
                root=root, runner_temp=temp, env=environment
            )
            receipt.helm_version = receipt.tool_versions.get("helm", "unknown")
            receipt.guard_blob_oids = guard_blob_oids(root=root, runner_temp=temp, env=environment)
            receipt.guard_manifest_sha256 = hashlib.sha256(
                json.dumps(receipt.guard_blob_oids, sort_keys=True).encode("utf-8")
            ).hexdigest()
            assert_guards_unmodified(
                root=root, base_ref=base_ref, runner_temp=temp, env=environment
            )

            # ── 준비 = canonical 그대로 (추가 명령 0) ──────────────────
            for position, step in enumerate(execution.runs):
                merged_env = {**environment, **dict(step.env)}
                code, _out, _err = _run(
                    step.argv, root=root, cwd=step.cwd, runner_temp=temp, env=merged_env
                )
                if code != 0:
                    raise RepoContractError(
                        REPO_CONTRACTS_BASE_REF_UNAVAILABLE
                        if BASE_REF_SCRIPT in step.argv
                        else REPO_CONTRACTS_PREPARATION_FAILED
                    )
                # P1 — 각 canonical 준비 단계 직후. 관측만 한다(§4-2·§4-3).
                _observe_clean(
                    receipt,
                    f"P1:{position}",
                    root=root,
                    runner_temp=temp,
                    env=environment,
                    plan_step_sha256=hashlib.sha256(
                        json.dumps(
                            step.as_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ).encode("utf-8")
                    ).hexdigest(),
                )

            # ── 저장소 계약: 정확히 한 번 ─────────────────────────────
            contract_env = contract_environment(
                root, base_env=environment, runner_temp=str(temp)
            )
            # Keep the canonical workflow's AC25_EVIDENCE_ROOT.  The canonical
            # preparation wrote the artifact-chain proof there; evidence_root
            # is the runner's separate private receipt directory.  Collapsing
            # the two roots makes the exact contract read a different,
            # unpopulated directory and fail with a false missing-proof result.
            receipt.contract_env_keys = sorted(
                key for key, _value in expected.contract_env
            )
            result, contract_stdout = output_containment.run_and_capture(
                list(expected.contract_argv),
                cwd=root,
                env=contract_env,
                timeout_seconds=3600,
                runner_temp=temp,
            )
            receipt.contract_exit_code = result.returncode
            receipt.stdout_sha256 = result.stdout_sha256
            receipt.stderr_sha256 = result.stderr_sha256
            receipt.stdout_bytes = result.stdout_bytes
            receipt.stderr_bytes = result.stderr_bytes
            receipt.descendants_observed = result.descendants_observed
            if evidence_root is not None:
                _write_private(evidence_root / "contract.stdout", contract_stdout)

            # §5 — 손실 없는 구조화. raw 는 여기서 끝난다.
            parsed = contract_parse.parse_contract_output(contract_stdout)
            receipt.contract_key_count = len(parsed.keys)
            receipt.primary_failed_guard = parsed.primary_failed_guard
            receipt.primary_failed_guard_line_sha256 = parsed.primary_line_sha256
            receipt.primary_failed_guard_line_bytes = parsed.primary_line_bytes
            receipt.failing_guard_keys = parsed.failing_guard_keys
            receipt.contract_block_lines = parsed.block_lines
            receipt.contract_unparsed_line_count = parsed.unparsed_line_count
            receipt.contract_unparsed_total_bytes = parsed.unparsed_total_bytes
            receipt.contract_unparsed_manifest_sha256 = parsed.unparsed_manifest_sha256
            receipt.contract_parse_error_code = parsed.parse_error_code

            # ── P2 — 계약 직후. 성패와 무관하게 잰다(§4-2).
            _observe_clean(receipt, "P2", root=root, runner_temp=temp, env=environment)

            if result.descendant_escape_detected or not result.cleanup_ok:
                raise RepoContractError(REPO_CONTRACTS_DESCENDANTS_SURVIVED)
            state = contract_state.evaluate_contract_state(
                exit_code=result.returncode,
                primary_failed_guard=receipt.primary_failed_guard,
                failing_guard_keys=tuple(receipt.failing_guard_keys),
                parse_error_code=receipt.contract_parse_error_code,
            )
            receipt.contract_state_outcome = state.outcome.value
            receipt.contract_state_error_code = state.error_code
            if state.outcome is contract_state.ContractOutcome.INVALID:
                raise RepoContractError(REPO_CONTRACTS_OUTPUT_INVALID)
            if state.outcome is contract_state.ContractOutcome.FAIL:
                raise RepoContractError(REPO_CONTRACTS_FAILED)
        finally:
            # ── P3 — 예외 처리 finally. checkout 신원을 확인했다면 반드시 잰다.
            #   ★재지 못한 상태는 NOT_EVALUATED 로 남는다. NO 로 바꾸지 않는다(§2).
            #   ★P3 자체의 실패가 원래 예외를 삼키면 안 된다 — 따로 받는다.
            if head_confirmed and receipt.clean_check_error_code == "NONE":
                try:
                    dirty = _observe_clean(
                        receipt, "P3", root=root, runner_temp=temp, env=environment
                    )
                    receipt.final_worktree_clean = "NO" if dirty else "YES"
                    receipt.dirty_paths = dirty
                    receipt.dirty_path_count = len(dirty)
                    receipt.dirty_path_manifest_sha256 = dirty_manifest_sha256(dirty)
                    if receipt.first_dirty_phase == "NOT_EVALUATED":
                        receipt.first_dirty_phase = "NONE"
                    if evidence_root is not None:
                        clean_code, clean_raw, _clean_err = _run(
                            (
                                "git", "status", "--porcelain=v2", "-z",
                                "--untracked-files=all",
                            ),
                            root=root,
                            cwd=".",
                            runner_temp=temp,
                            env=environment,
                        )
                        receipt.raw_clean_status_exit_code = clean_code
                        receipt.raw_clean_status_sha256 = hashlib.sha256(clean_raw).hexdigest()
                        receipt.raw_clean_status_bytes = len(clean_raw)
                        _write_private(evidence_root / "clean-status.porcelain-v2.z", clean_raw)
                        if clean_code != 0:
                            raise RepoContractError(CLEAN_CHECK_COMMAND_FAILED)
                except RepoContractError as clean_exc:
                    receipt.clean_check_error_code = clean_exc.code
                    receipt.final_worktree_clean = "NOT_EVALUATED"
    except RepoContractError as exc:
        if exc.code in (CLEAN_CHECK_COMMAND_FAILED, CLEAN_OUTPUT_INVALID, CLEAN_PATH_INVALID):
            # clean 검사 자체가 실패했다 — NOT_EVALUATED + 안정 코드(§4-4)
            receipt.clean_check_error_code = exc.code
            receipt.final_worktree_clean = "NOT_EVALUATED"
            if receipt.error_code == "NONE":
                receipt.error_code = exc.code
        else:
            receipt.error_code = exc.code
        receipt.verdict = 0
    except output_containment.ContainmentError as exc:
        receipt.error_code = exc.code
        receipt.verdict = 0
    except canonical_plan.CanonicalPlanError as exc:
        receipt.error_code = (
            REPO_CONTRACTS_CANONICAL_PLAN_UNSUPPORTED
            if exc.code == canonical_plan.CANONICAL_PLAN_UNSUPPORTED_SEMANTICS
            else REPO_CONTRACTS_CANONICAL_PLAN_UNREADABLE
        )
        receipt.verdict = 0
    else:
        # 성공 경로 — clean 은 ★실측했어야★ 하지만, 실측된 NO 는 판정이 아니라
        # 증거다(§4-3 "canonical step 이 만든 잔여물이라면 그것도 증거다").
        # §15 는 CLOSE-1(job success)과 CLOSE-2(clean YES)를 별개 conjunct 로
        # 둔다 — clean 판정은 CLOSE-2 가 receipt 값으로 한다. 여기서 NO 를
        # 실패로 바꾸면 두 판정이 결합되어 §9 의 분리가 깨진다.
        if receipt.final_worktree_clean in ("YES", "NO"):
            receipt.verdict = 1
        else:
            # 실측하지 못한 채로는 PASS 를 쓰지 않는다(§2)
            receipt.error_code = receipt.clean_check_error_code
    return receipt


# ── §13 허용된 출력 형식 ───────────────────────────────────────────────
def _bounded_join(items, *, limit_bytes: int) -> str:
    joined = ",".join(items)
    if not joined:
        return "NONE"
    if len(joined.encode("utf-8")) > limit_bytes:
        return "BOUNDED"
    return joined


def emit_lines(receipt: ContractReceipt) -> list[str]:
    lines = [
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
        f"CANONICAL_WORKFLOW_SHA256={receipt.canonical_workflow_sha256 or 'NONE'}",
        f"CANONICAL_STEP_COUNT={receipt.canonical_step_count}",
        f"CANONICAL_MISSING_STEP_COUNT={len(receipt.plan_missing)}",
        f"CANONICAL_EXTRA_STEP_COUNT={len(receipt.plan_extra)}",
        f"CANONICAL_REORDERED_STEP_COUNT={len(receipt.plan_reordered)}",
        f"CANONICAL_MUTATED_STEP_COUNT={len(receipt.plan_mutated)}",
        f"CANONICAL_UNSUPPORTED_STEP_COUNT={len(receipt.plan_unsupported)}",
        f"PREPARATION_ENV_BOUND_KEYS={len(receipt.preparation_env_keys)}",
        f"CLEAN_CHECK_EXECUTED={'YES' if receipt.clean_check_executed else 'NO'}",
        f"RAW_FINAL_WORKTREE_CLEAN={receipt.final_worktree_clean}",
        f"FINAL_WORKTREE_CLEAN={receipt.final_worktree_clean}",
        f"DECLARED_CANONICAL_OUTPUT_POLICY={receipt.declared_canonical_output_policy}",
        f"DIRTY_PATH_COUNT={receipt.dirty_path_count}",
        f"DIRTY_PATH_MANIFEST_SHA256={receipt.dirty_path_manifest_sha256 or 'NONE'}",
        f"FIRST_DIRTY_PHASE={receipt.first_dirty_phase}",
        f"CLEAN_CHECK_ERROR_CODE={receipt.clean_check_error_code}",
        f"PRIMARY_FAILED_GUARD={receipt.primary_failed_guard}",
        f"PRIMARY_FAILED_GUARD_LINE_SHA256={receipt.primary_failed_guard_line_sha256 or 'NONE'}",
        f"PRIMARY_FAILED_GUARD_LINE_BYTES={receipt.primary_failed_guard_line_bytes}",
        f"FAILING_GUARD_KEY_COUNT={len(receipt.failing_guard_keys)}",
        f"FAILING_GUARD_KEYS_SHA256="
        f"{contract_parse.failing_keys_sha256(tuple(receipt.failing_guard_keys))}",
        f"FAILING_GUARD_KEYS="
        f"{_bounded_join(receipt.failing_guard_keys, limit_bytes=_FAILING_KEYS_LOG_BYTES)}",
        f"CONTRACT_KEY_COUNT={receipt.contract_key_count}",
        f"CONTRACT_UNPARSED_LINE_COUNT={receipt.contract_unparsed_line_count}",
        f"CONTRACT_UNPARSED_TOTAL_BYTES={receipt.contract_unparsed_total_bytes}",
        f"CONTRACT_UNPARSED_MANIFEST_SHA256="
        f"{receipt.contract_unparsed_manifest_sha256 or 'NONE'}",
        f"CONTRACT_PARSE_ERROR_CODE={receipt.contract_parse_error_code}",
        f"CONTRACT_STATE_OUTCOME={receipt.contract_state_outcome}",
        f"CONTRACT_STATE_ERROR_CODE={receipt.contract_state_error_code}",
        f"CONTRACT_BLOCK_LINE_COUNT={len(receipt.contract_block_lines)}",
        f"RAW_CLEAN_STATUS_EXIT_CODE={receipt.raw_clean_status_exit_code}",
        f"RAW_CLEAN_STATUS_SHA256={receipt.raw_clean_status_sha256 or 'NONE'}",
        f"RAW_CLEAN_STATUS_BYTES={receipt.raw_clean_status_bytes}",
    ]
    # 계약 자신의 BLOCK 진단 — canonical 공개 로그와 같은 수준의 문구다.
    for ordinal, line in enumerate(receipt.contract_block_lines):
        lines.append(f"CONTRACT_BLOCK_LINE_{ordinal:02d}={line}")
    # §4-2 — 안전한 경로만, 최대 20 개 · 4096 bytes 까지. 초과분은 지문·개수다.
    emitted = 0
    budget = _DIRTY_PATH_LOG_BYTES
    for ordinal, path in enumerate(receipt.dirty_paths):
        if emitted >= _DIRTY_PATH_LOG_LIMIT:
            break
        if _SAFE_PATH_RE.match(path) is None:
            continue
        line = f"DIRTY_PATH_{ordinal:02d}={path}"
        evidence = receipt.dirty_path_evidence.get(path)
        detail_lines = []
        if evidence is not None:
            detail_lines = [
                f"DIRTY_PATH_FIRST_PHASE_{ordinal:02d}={evidence.first_phase}",
                f"DIRTY_PATH_PLAN_SHA256_{ordinal:02d}={evidence.plan_step_sha256}",
                f"DIRTY_PATH_HEAD_BLOB_OID_{ordinal:02d}={evidence.head_blob_oid}",
                f"DIRTY_PATH_AFTER_SHA256_{ordinal:02d}={evidence.after_sha256}",
                f"DIRTY_PATH_MODE_{ordinal:02d}={evidence.mode}",
                f"DIRTY_PATH_STATUS_{ordinal:02d}={evidence.status}",
            ]
        cost = sum(
            len(item.encode("utf-8")) for item in (line, *detail_lines)
        )
        if cost > budget:
            break
        lines.append(line)
        lines.extend(detail_lines)
        budget -= cost
        emitted += 1
    lines.extend([
        f"RUNNER_IMAGE={receipt.runner_image or 'unknown'}",
        f"HELM_VERSION={receipt.helm_version or 'unknown'}",
        f"NODE_VERSION={receipt.tool_versions.get('node', 'unknown')}",
        f"PYTHON_VERSION={receipt.tool_versions.get('python', 'unknown')}",
    ])
    return lines


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
    configured = os.environ.get("AC25_CONTRACT_EVIDENCE_ROOT", "")
    if configured and receipt.error_code != OUTPUT_ROOT_POLICY_VIOLATION:
        evidence_root = Path(configured).resolve()
        summary = {
            "clean_status_bytes": receipt.raw_clean_status_bytes,
            "clean_status_exit_code": receipt.raw_clean_status_exit_code,
            "clean_status_path": "clean-status.porcelain-v2.z",
            "clean_status_sha256": receipt.raw_clean_status_sha256,
            "command_plan_sha256": receipt.command_plan_sha256,
            "contract_exit_code": receipt.contract_exit_code,
            "contract_stdout_bytes": receipt.stdout_bytes,
            "contract_stdout_path": "contract.stdout",
            "contract_stdout_sha256": receipt.stdout_sha256,
            "guard_manifest_sha256": receipt.guard_manifest_sha256,
            "post_run_cleanup_used": False,
            "schema_version": "butler.ac25.contract-raw-evidence.v1",
            "target_head_sha": receipt.exact_head,
            "target_head_tree": receipt.exact_tree,
        }
        _write_private(
            evidence_root / "contract-run.json",
            (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        )
    for line in emit_lines(receipt):
        print(line)
    return 0 if receipt.verdict == 1 else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "CLEAN_CHECK_COMMAND_FAILED",
    "CLEAN_OUTPUT_INVALID",
    "CLEAN_PATH_INVALID",
    "CONTRACT_COMMAND",
    "MUTATION_FORBIDDEN_GUARD_PATHS",
    "PROTECTED_GUARD_PATHS",
    "REPO_CONTRACTS_BASE_REF_UNAVAILABLE",
    "REPO_CONTRACTS_CANONICAL_ACTION_MISMATCH",
    "REPO_CONTRACTS_CANONICAL_PLAN_EXTRA",
    "REPO_CONTRACTS_CANONICAL_PLAN_MISSING",
    "REPO_CONTRACTS_CANONICAL_PLAN_MUTATED",
    "REPO_CONTRACTS_CANONICAL_PLAN_REORDERED",
    "REPO_CONTRACTS_CANONICAL_PLAN_UNREADABLE",
    "REPO_CONTRACTS_CANONICAL_PLAN_UNSUPPORTED",
    "REPO_CONTRACTS_DESCENDANTS_SURVIVED",
    "REPO_CONTRACTS_EXACT_HEAD_MISMATCH",
    "REPO_CONTRACTS_FAILED",
    "REPO_CONTRACTS_GUARD_MUTATED",
    "REPO_CONTRACTS_OUTPUT_CONTRADICTORY",
    "REPO_CONTRACTS_OUTPUT_INVALID",
    "REPO_CONTRACTS_PREEXISTING_WORKTREE_DIRTY",
    "REPO_CONTRACTS_PREPARATION_FAILED",
    "REPO_CONTRACTS_SHALLOW_CLONE",
    "ContractReceipt",
    "DirtyPathEvidence",
    "RepoContractError",
    "assert_exact_head",
    "assert_guards_unmodified",
    "build_execution_plan",
    "build_preparation_plan",
    "clean_snapshot",
    "clean_snapshot_details",
    "collect_tool_versions",
    "command_plan_sha256",
    "contract_environment",
    "dirty_manifest_sha256",
    "emit_lines",
    "guard_blob_oids",
    "run_exact_head_contracts",
]
