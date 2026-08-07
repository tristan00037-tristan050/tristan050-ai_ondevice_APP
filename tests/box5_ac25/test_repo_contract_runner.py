"""R6-4 실행기 — v3.1 §3·§4·§5 가 코드에 실제로 박혔는가.

핵심 부정 시험 셋이 이 판의 정체성이다.

    ① 계약이 실패해도 clean 검사는 finally 에서 ★실제로 실행★ 된다(§4-2).
       이전 판은 실행하지 않은 검사를 `NO` 로 적었다 — 그 값이 틀린 원인
       단정(v3.0 §4-1)의 근거가 됐다.
    ② `NOT_EVALUATED` 는 어떤 예외 경로에서도 `NO` 로 바뀌지 않는다(§2).
    ③ canonical 과 다섯 축 중 하나라도 어긋나면 계약을 ★실행하지 않는다★.
"""
from __future__ import annotations

import dataclasses
import re
import shutil
from pathlib import Path

import pytest
from ac25 import canonical_plan as cp
from ac25 import output_containment as oc
from ac25 import repo_contract_runner as rcr

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40

# ★오염 guard 준수 — 픽스처의 성공 요약 줄은 이어붙여 만든다.
PRIMARY_NONE_LINE = ("REPO_CONTRACTS_FAILED_GUARD=" + "NONE").encode() + b"\n"


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    for relative in (cp.CANONICAL_WORKFLOW_PATH, cp.EXECUTION_WORKFLOW_PATH):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)
    shutil.copytree(
        REPO_ROOT / ".github" / "actions" / "preflight_v1",
        root / ".github" / "actions" / "preflight_v1",
    )
    return root


def contained_result(returncode: int, *, escaped: bool = False) -> oc.ContainedResult:
    return oc.ContainedResult(
        returncode=returncode, stdout_sha256="0" * 64, stderr_sha256="1" * 64,
        stdout_bytes=10, stderr_bytes=0, timed_out=False,
        output_limit_exceeded=False, descendants_observed=0,
        descendants_terminated=0, descendants_reaped=0,
        descendant_escape_detected=escaped, process_group_empty=not escaped,
        supervisor_children_empty=True, raw_files_deleted=True,
        cleanup_ok=not escaped,
    )


class World:
    """격리기 호출을 가로채는 가짜 세계. git·도구·계약 응답을 통제한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict, object]] = []
        self.clean_outputs: list = []      # git status 응답 큐(bytes 또는 int=exit)
        self.prep_fail = None              # argv 술어 → 준비 실패 주입
        self.contract_exit = 0
        self.contract_stdout = PRIMARY_NONE_LINE
        self.contract_escaped = False
        self.contract_calls = 0
        self.status_calls = 0

    def run_and_read(self, argv, *, cwd, env=None, runner_temp=None,
                     timeout_seconds=0, **_kw):
        argv = tuple(argv)
        self.calls.append((argv, dict(env or {}), cwd))
        if argv[:2] == ("git", "status"):
            self.status_calls += 1
            item = self.clean_outputs.pop(0) if self.clean_outputs else b""
            if isinstance(item, int):
                return item, b"", b""
            return 0, item, b""
        if argv == ("git", "rev-parse", "HEAD"):
            return 0, HEAD.encode(), b""
        if argv[:2] == ("git", "show"):
            return 0, ("b" * 40).encode(), b""
        if argv == ("git", "rev-parse", "--is-shallow-repository"):
            return 0, b"false", b""
        if argv[:2] == ("git", "rev-parse") and argv[-1].startswith("HEAD:"):
            return 0, ("d" * 40).encode(), b""
        if argv[:2] == ("git", "diff"):
            return 0, b"", b""
        if argv == ("git", "--version"):
            return 0, b"git version 2.54.0", b""
        if argv[-1] == "--version" or argv[:2] == ("helm", "version"):
            return 0, b"v0.0-test", b""
        if self.prep_fail is not None and self.prep_fail(argv):
            return 1, b"", b""
        return 0, b"", b""

    def run_and_capture(self, argv, *, cwd, env, timeout_seconds, runner_temp, **_kw):
        self.contract_calls += 1
        self.contract_env = dict(env)
        return contained_result(
            self.contract_exit, escaped=self.contract_escaped
        ), self.contract_stdout


@pytest.fixture
def world(monkeypatch) -> World:
    fake = World()
    monkeypatch.setattr(rcr.output_containment, "run_and_read", fake.run_and_read)
    monkeypatch.setattr(rcr.output_containment, "run_and_capture", fake.run_and_capture)
    return fake


def run(repo, tmp_path, **kwargs):
    return rcr.run_exact_head_contracts(
        root=repo, expected_head=kwargs.pop("expected_head", HEAD),
        runner_temp=tmp_path, env=kwargs.pop("env", {"PATH": "/usr/bin"}), **kwargs,
    )


def prep_count(repo) -> int:
    return len(rcr.build_preparation_plan(repo, runner_temp="/tmp"))


# ══ 성공 경로 ══════════════════════════════════════════════════════════
def test_success_path_measures_clean_and_passes(repo, world, tmp_path):
    receipt = run(repo, tmp_path)
    assert receipt.error_code == "NONE"
    assert receipt.verdict == 1
    assert receipt.clean_check_executed is True
    assert receipt.final_worktree_clean == "YES"
    assert receipt.dirty_path_count == 0
    assert receipt.first_dirty_phase == "NONE"
    assert receipt.primary_failed_guard == "NONE"
    assert world.contract_calls == 1
    # P0 + 준비 단계마다 P1 + P2 + P3
    assert world.status_calls == prep_count(repo) + 3
    # 다섯 축 전부 0
    assert receipt.plan_missing == receipt.plan_extra == []
    assert receipt.plan_reordered == receipt.plan_mutated == []
    assert receipt.plan_unsupported == []


def test_preparation_is_canonical_only_no_extra_commands(repo, world, tmp_path):
    """★npm ci·build:packages:server·helm 이 준비에서 사라졌다(§3-4)."""
    run(repo, tmp_path)
    prep_argvs = [argv for argv, _env, _cwd in world.calls if argv[0] in ("npm", "npx", "helm", "sudo", "bash")]
    joined = [" ".join(argv) for argv in prep_argvs]
    assert not any(argv == ("npm", "ci") for argv in prep_argvs)
    assert not any("build:packages:server" in item for item in joined)
    # helm 은 observation(version --short)으로만 나타난다
    helm_calls = [argv for argv in prep_argvs if argv[0] == "helm"]
    assert helm_calls == [("helm", "version", "--short")]


def test_canonical_env_is_bound_to_steps_and_contract(repo, world, tmp_path):
    receipt = run(repo, tmp_path)
    by_command = {" ".join(argv): env for argv, env, _cwd in world.calls}
    playwright_key = next(k for k in by_command if "playwright" in k)
    assert by_command[playwright_key]["PLAYWRIGHT_BROWSERS_PATH"].endswith("/ms-playwright")
    assert by_command["bash tools/preflight_v1.sh"]["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert by_command["bash tools/preflight_v1.sh"]["PATH"] == "/usr/bin"
    assert world.contract_env["ARTIFACT_CHAIN_PROOF_V2_ENFORCE"] == "1"
    assert world.contract_env["ONPREM_PROOF_STRICT_ENFORCE"] == "0"
    assert "GIT_LFS_SKIP_SMUDGE" in receipt.preparation_env_keys
    assert "PLAYWRIGHT_BROWSERS_PATH" in receipt.preparation_env_keys


# ══ §4-4 ① contract 실패 후에도 finally clean 검사가 실행됨 ═══════════
def test_clean_is_measured_in_finally_even_when_contract_fails(repo, world, tmp_path):
    world.contract_exit = 1
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_FAILED
    # ★실행됐고, 실측이 YES 다. 실패가 clean 을 NO 로 오염시키지 않는다(§11).
    assert receipt.clean_check_executed is True
    assert receipt.final_worktree_clean == "YES"
    assert world.status_calls == prep_count(repo) + 3
    # 실패한 실행의 NONE 요약은 요약이 아니다 — UNPARSED 로 보고한다(§5-1)
    assert receipt.primary_failed_guard == "UNPARSED"


# ══ §4-4 ② checkout 확인 전 실패는 NOT_EVALUATED ══════════════════════
def test_failure_before_head_confirmation_is_not_evaluated(repo, world, tmp_path):
    receipt = run(repo, tmp_path, expected_head="not-an-oid")
    assert receipt.error_code == rcr.REPO_CONTRACTS_EXACT_HEAD_MISMATCH
    assert receipt.final_worktree_clean == "NOT_EVALUATED"
    assert receipt.clean_check_executed is False
    assert receipt.first_dirty_phase == "NOT_EVALUATED"


# ══ §4-4 ③④ 실측 YES 만 YES · tracked/staged/untracked 각각 NO ════════
@pytest.mark.parametrize(
    "entry", [b" M tracked_file\x00", b"A  staged_file\x00", b"?? untracked_file\x00"],
    ids=["tracked", "staged", "untracked"],
)
def test_each_dirty_kind_is_measured_as_no(repo, world, tmp_path, entry):
    total = prep_count(repo) + 3
    world.clean_outputs = [b""] * (total - 1) + [entry]
    receipt = run(repo, tmp_path)
    assert receipt.final_worktree_clean == "NO"
    assert receipt.error_code == rcr.REPO_CONTRACTS_WORKTREE_NOT_CLEAN
    assert receipt.verdict == 0
    assert receipt.dirty_path_count == 1
    assert receipt.first_dirty_phase == "P3"


# ══ §4-4 ⑤ dirty manifest 정렬·결정적 ═════════════════════════════════
def test_dirty_manifest_is_sorted_and_deterministic(repo, world, tmp_path):
    total = prep_count(repo) + 3
    world.clean_outputs = [b""] * (total - 1) + [b"?? zebra\x00?? alpha\x00"]
    receipt = run(repo, tmp_path)
    assert receipt.dirty_paths == ("alpha", "zebra")
    assert receipt.dirty_path_manifest_sha256 == rcr.dirty_manifest_sha256(("alpha", "zebra"))
    assert rcr.dirty_manifest_sha256(("alpha", "zebra")) == rcr.dirty_manifest_sha256(
        ("alpha", "zebra")
    )


def test_rename_entries_keep_both_paths(repo, world, tmp_path):
    total = prep_count(repo) + 3
    world.clean_outputs = [b""] * (total - 1) + [b"R  new_name\x00old_name\x00"]
    receipt = run(repo, tmp_path)
    assert receipt.dirty_paths == ("new_name", "old_name")


# ══ §4-4 ⑥ path traversal·제어문자 거부 ═══════════════════════════════
@pytest.mark.parametrize(
    "entry", [b"?? ../escape\x00", b"?? /absolute\x00", b"?? bad\x01name\x00"],
    ids=["traversal", "absolute", "control-char"],
)
def test_invalid_dirty_paths_are_rejected_not_normalized(repo, world, tmp_path, entry):
    world.clean_outputs = [entry]  # P0 에서 즉시
    receipt = run(repo, tmp_path)
    assert receipt.clean_check_error_code == rcr.CLEAN_PATH_INVALID
    assert receipt.final_worktree_clean == "NOT_EVALUATED"
    assert receipt.verdict == 0


# ══ §4-4 ⑦ clean 검사 자체 실패 → NOT_EVALUATED + 안정 코드 ═══════════
def test_clean_command_failure_is_not_evaluated_with_stable_code(repo, world, tmp_path):
    world.clean_outputs = [1]  # P0 의 git status 가 exit 1
    receipt = run(repo, tmp_path)
    assert receipt.clean_check_error_code == rcr.CLEAN_CHECK_COMMAND_FAILED
    assert receipt.final_worktree_clean == "NOT_EVALUATED"
    assert receipt.verdict == 0


# ══ §4-4 ⑧ 어떤 예외도 NOT_EVALUATED 를 NO 로 바꾸지 않는다 ═══════════
def test_not_evaluated_never_becomes_no(repo, world, tmp_path):
    for receipt in (
        run(repo, tmp_path, expected_head="not-an-oid"),
        run(repo, tmp_path),
    ):
        if receipt.final_worktree_clean == "NOT_EVALUATED":
            assert receipt.final_worktree_clean != "NO"
    # 소스 수준으로도 고정한다 — 예외 블록에 NO 대입이 없다
    source = (REPO_ROOT / "scripts/ci/ac25/repo_contract_runner.py").read_text(
        encoding="utf-8"
    )
    assert 'final_worktree_clean = "NO"' not in source.replace(
        'receipt.final_worktree_clean = "NO" if dirty else "YES"', ""
    )


# ══ §4-4 ⑨ git clean/reset/rm 이 production 에 없다 (정적) ════════════
def test_no_cleanup_commands_in_production_runner():
    source = (REPO_ROOT / "scripts/ci/ac25/repo_contract_runner.py").read_text(
        encoding="utf-8"
    )
    for token in ('"clean"', "'clean'", '"reset"', "'reset'", '"rm"', "'rm'",
                  "rmtree", "unlink("):
        assert token not in source, token


# ══ P0 — 시작 전 dirty 면 준비를 시작하지 않는다 ══════════════════════
def test_preexisting_dirty_worktree_blocks_preparation(repo, world, tmp_path):
    world.clean_outputs = [b"?? leftover\x00", b"?? leftover\x00"]
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_PREEXISTING_WORKTREE_DIRTY
    assert receipt.first_dirty_phase == "P0"
    prep_ran = [
        argv for argv, _e, _c in world.calls
        if argv[0] in ("sudo", "npm", "npx") and argv[-1] != "--version"
    ]
    assert prep_ran == [], "P0 dirty 인데 준비를 시작했다"
    assert world.contract_calls == 0


# ══ P1 — 처음 dirty 가 된 단계의 index 를 기록한다 ════════════════════
def test_first_dirty_phase_records_the_step_index(repo, world, tmp_path):
    total = prep_count(repo) + 3
    # P0 clean · P1:0 clean · P1:1 부터 dirty
    world.clean_outputs = [b"", b""] + [b"?? made_by_step\x00"] * (total - 2)
    receipt = run(repo, tmp_path)
    assert receipt.first_dirty_phase == "P1:1"
    assert world.contract_calls == 1, "P1 dirty 는 관측이지 중단 사유가 아니다(§4-3)"
    assert receipt.final_worktree_clean == "NO"


# ══ §3-4 동등성 게이트 — 어긋나면 계약을 실행하지 않는다 ══════════════
def _forge_execution(monkeypatch, repo, mutate):
    real = rcr.build_execution_plan(repo, runner_temp="/tmp")
    monkeypatch.setattr(rcr, "build_execution_plan", lambda *a, **k: mutate(real))


def test_extra_step_gate_blocks_the_contract(repo, world, tmp_path, monkeypatch):
    def mutate(plan):
        intruder = dataclasses.replace(
            plan.runs[0], index=99, name="smuggled#0", argv=("npm", "ci"),
        )
        return dataclasses.replace(plan, runs=plan.runs + (intruder,))

    _forge_execution(monkeypatch, repo, mutate)
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_EXTRA
    assert receipt.plan_extra
    assert world.contract_calls == 0
    assert receipt.final_worktree_clean == "NOT_EVALUATED"


def test_missing_step_gate_blocks_the_contract(repo, world, tmp_path, monkeypatch):
    _forge_execution(
        monkeypatch, repo,
        lambda plan: dataclasses.replace(plan, runs=plan.runs[:-1]),
    )
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_MISSING
    assert world.contract_calls == 0


def test_mutated_step_gate_blocks_the_contract(repo, world, tmp_path, monkeypatch):
    def mutate(plan):
        first = dataclasses.replace(plan.runs[0], cwd="elsewhere")
        return dataclasses.replace(plan, runs=(first,) + plan.runs[1:])

    _forge_execution(monkeypatch, repo, mutate)
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_MUTATED
    assert world.contract_calls == 0


def test_reordered_steps_gate_blocks_the_contract(repo, world, tmp_path, monkeypatch):
    def mutate(plan):
        swapped = list(plan.runs)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        return dataclasses.replace(plan, runs=tuple(swapped))

    _forge_execution(monkeypatch, repo, mutate)
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_REORDERED
    assert world.contract_calls == 0


def test_action_mismatch_gate_blocks_the_contract(repo, world, tmp_path, monkeypatch):
    def mutate(plan):
        victim = plan.actions[0]
        forged = dataclasses.replace(victim, uses="attacker/act@" + "e" * 40)
        return dataclasses.replace(
            plan, actions=tuple(forged if a is victim else a for a in plan.actions)
        )

    _forge_execution(monkeypatch, repo, mutate)
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_ACTION_MISMATCH
    assert world.contract_calls == 0


def test_unreadable_canonical_blocks_the_contract(tmp_path, world):
    root = tmp_path / "empty"
    (root / "scripts").mkdir(parents=True)
    receipt = rcr.run_exact_head_contracts(
        root=root, expected_head=HEAD, runner_temp=tmp_path, env={},
    )
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_UNREADABLE
    assert world.contract_calls == 0


def test_unsupported_canonical_syntax_blocks_the_contract(repo, world, tmp_path):
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "      - name: Install ripgrep\n",
        "      - name: Install ripgrep\n        if: always()\n",
    )
    path.write_text(body, encoding="utf-8")
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_UNSUPPORTED
    assert world.contract_calls == 0


# ══ §5 결선 — 공백 primary · 0-key · 모순 ═════════════════════════════
def test_spaced_primary_guard_survives_parsing(repo, world, tmp_path):
    guard_name = "repo " + "OK".lower().upper() + " contamination guard"
    world.contract_exit = 1
    world.contract_stdout = (
        ("REPO_CONTRACTS_FAILED_GUARD=" + guard_name).encode() + b"\n"
        + b"SOME_GUARD" + b"_OK=0\n"
        + b"== guard: something v1 ==\n"
    )
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_FAILED
    assert receipt.primary_failed_guard == guard_name
    assert receipt.primary_failed_guard_line_bytes > 0
    assert receipt.failing_guard_keys == ("SOME_GUARD_OK",)
    assert receipt.contract_unparsed_line_count == 1
    assert receipt.contract_unparsed_manifest_sha256


def test_exit_zero_with_named_primary_is_contradictory(repo, world, tmp_path):
    world.contract_exit = 0
    world.contract_stdout = b"REPO_CONTRACTS_FAILED_GUARD=named guard v1\n"
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_OUTPUT_CONTRADICTORY
    assert receipt.verdict == 0


def test_exit_zero_without_summary_line_is_contradictory(repo, world, tmp_path):
    world.contract_stdout = b"WHATEVER_KEY=x\n"
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_OUTPUT_CONTRADICTORY
    assert receipt.primary_failed_guard == "UNPARSED"


def test_non_utf8_contract_output_is_closed(repo, world, tmp_path):
    world.contract_stdout = b"\xff\xfe broken"
    receipt = run(repo, tmp_path)
    assert receipt.contract_parse_error_code == "CONTRACT_OUTPUT_NOT_UTF8"
    assert receipt.error_code == rcr.REPO_CONTRACTS_OUTPUT_CONTRADICTORY


def test_descendant_escape_is_fatal(repo, world, tmp_path):
    world.contract_escaped = True
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_DESCENDANTS_SURVIVED
    assert receipt.verdict == 0


# ══ 준비 실패 코드 구분 ════════════════════════════════════════════════
def test_base_ref_preflight_failure_has_its_own_code(repo, world, tmp_path):
    world.prep_fail = lambda argv: rcr.BASE_REF_SCRIPT in argv
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_BASE_REF_UNAVAILABLE


def test_other_preparation_failure_is_preparation_failed(repo, world, tmp_path):
    world.prep_fail = lambda argv: argv[:1] == ("sudo",)
    receipt = run(repo, tmp_path)
    assert receipt.error_code == rcr.REPO_CONTRACTS_PREPARATION_FAILED


# ══ §13 출력 형식 ══════════════════════════════════════════════════════
def test_emit_lines_carry_every_required_key(repo, world, tmp_path):
    receipt = run(repo, tmp_path)
    lines = rcr.emit_lines(receipt)
    keys = {line.split("=", 1)[0] for line in lines}
    for required in (
        "REPO_CONTRACTS_EXACT_HEAD", "ERROR_CODE", "COMMAND_PLAN_SHA256",
        "CANONICAL_MISSING_STEP_COUNT", "CANONICAL_EXTRA_STEP_COUNT",
        "CANONICAL_REORDERED_STEP_COUNT", "CANONICAL_MUTATED_STEP_COUNT",
        "CANONICAL_UNSUPPORTED_STEP_COUNT",
        "CLEAN_CHECK_EXECUTED", "FINAL_WORKTREE_CLEAN", "DIRTY_PATH_COUNT",
        "DIRTY_PATH_MANIFEST_SHA256", "FIRST_DIRTY_PHASE", "CLEAN_CHECK_ERROR_CODE",
        "PRIMARY_FAILED_GUARD", "PRIMARY_FAILED_GUARD_LINE_SHA256",
        "PRIMARY_FAILED_GUARD_LINE_BYTES", "FAILING_GUARD_KEY_COUNT",
        "FAILING_GUARD_KEYS_SHA256", "FAILING_GUARD_KEYS",
        "CONTRACT_UNPARSED_LINE_COUNT", "CONTRACT_UNPARSED_TOTAL_BYTES",
        "CONTRACT_UNPARSED_MANIFEST_SHA256", "CONTRACT_PARSE_ERROR_CODE",
    ):
        assert required in keys, required


def test_dirty_paths_in_log_are_bounded_and_safe(repo, world, tmp_path):
    total = prep_count(repo) + 3
    entries = b"".join(f"?? file_{i:03d}\x00".encode() for i in range(50))
    world.clean_outputs = [b""] * (total - 1) + [entries]
    receipt = run(repo, tmp_path)
    lines = rcr.emit_lines(receipt)
    dirty_lines = [
        line for line in lines if re.match(r"DIRTY_PATH_\d", line)
    ]
    assert 0 < len(dirty_lines) <= 20
    assert receipt.dirty_path_count == 50
    # 로그에 안 실린 나머지는 지문·개수가 증명한다
    assert any(line.startswith("DIRTY_PATH_MANIFEST_SHA256=") for line in lines)


def test_huge_failing_key_list_is_bounded_in_log(repo, world, tmp_path):
    world.contract_exit = 1
    body = b"".join(
        f"VERY_LONG_GUARD_NAME_{i:04d}_PADDED_TO_MAKE_IT_WIDE".encode()
        + b"_OK=0\n" for i in range(200)
    )
    world.contract_stdout = ("REPO_CONTRACTS_FAILED_GUARD=" + "x guard").encode() + b"\n" + body
    receipt = run(repo, tmp_path)
    line = next(
        l for l in rcr.emit_lines(receipt) if l.startswith("FAILING_GUARD_KEYS=")
    )
    assert line == "FAILING_GUARD_KEYS=BOUNDED"
    assert len(receipt.failing_guard_keys) == 200


# ══ 계약은 정확히 한 번 · run_and_read 경로로 부르지 않는다 ═══════════
def test_contract_runs_exactly_once_and_only_via_capture(repo, world, tmp_path):
    run(repo, tmp_path)
    assert world.contract_calls == 1
    for argv, _env, _cwd in world.calls:
        # read-only OID 조회(rev-parse HEAD:<path>)는 실행이 아니다
        if argv[:2] == ("git", "rev-parse"):
            continue
        assert "verify_repo_contracts.sh" not in " ".join(argv)


# ══ 준비 명령이 canonical 순서 그대로 실행된다 ════════════════════════
def test_preparation_executes_in_canonical_order(repo, world, tmp_path):
    run(repo, tmp_path)
    plan = rcr.build_preparation_plan(repo, runner_temp=str(tmp_path))
    executed = [argv for argv, _e, _c in world.calls]
    positions = []
    cursor = 0
    for step in plan:
        while cursor < len(executed) and executed[cursor] != step.argv:
            cursor += 1
        assert cursor < len(executed), f"준비 단계가 실행되지 않았다: {step.name}"
        positions.append(cursor)
    assert positions == sorted(positions)


# ══ 명령 계획 지문 ═════════════════════════════════════════════════════
def test_command_plan_digest_is_stable(repo):
    first = rcr.command_plan_sha256(repo, runner_temp="/tmp")
    assert first == rcr.command_plan_sha256(repo, runner_temp="/tmp")
    assert re.fullmatch(r"[0-9a-f]{64}", first)
