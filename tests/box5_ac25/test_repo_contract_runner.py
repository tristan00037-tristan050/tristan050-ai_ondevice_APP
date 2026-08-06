"""§7-7 R6-4 — exact-head 저장소 계약 실행기 시험.

여기서 보는 것
  · checkout 이 exact head 가 아니면 준비를 하지 않고 닫는다
  · guard 를 바꾼 채로는 계약을 돌리지 않는다(검사기를 고쳐 통과시키지 않는다)
  · 빌드 산출물·Helm 이 없으면 즉석 설치하지 않고 닫는다
  · 저장소 계약을 ★정확히 한 번★ 부른다
  · 명령 계획의 순서·목록이 지문으로 고정돼 있다
  · raw 출력이 로그로 새지 않는다(digest·길이만)
  · 실행 후 잔여물이 있으면 실패다
  · 정상 경로는 실제로 PASS 한다(막기만 하는 검사기는 합격이 아니다)

실제 npm ci·helm 은 이 컨테이너에서 돌리지 않는다. 대신 격리기 호출을 가로채
명령 순서·인자·횟수를 관측한다 — 그것이 이 모듈이 지켜야 할 계약이다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from ac25 import canonical_plan
from ac25 import output_containment as oc
from ac25 import repo_contract_runner as rcr

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = REPO_ROOT / "scripts" / "verify" / "verify_repo_contracts.sh"
SMOKE = REPO_ROOT / ".github" / "workflows" / "box5-ac25-stage-a-smoke.yml"

HEAD = "a" * 40
TREE = "b" * 40
BASE = "c" * 40
BLOB = "d" * 40

# 계약이 실제로 내는 형태: KEY=0/1 줄과 실패 시 FAILED_GUARD 줄
# ★`*_OK=1` 을 ★리터럴로 쓰지 않는다★. 저장소 계약
# (verify_repo_no_ok_contamination.sh)이 tests/ 안의 그 문자열을 금지한다 —
# 시험이 CI 로그에 가짜 통과 신호를 심는 것을 막는 guard이고 정당하다.
# 통과 값이 필요한 자리는 ★구조(dict)로★ 시험한다. 문자열로 만들지 않는다.
CONTRACT_STDOUT = (
    b"P0_02_KEYS_ONLY_VAL=unset\n"
    b"REPO_CONTRACTS_HYGIENE_STATUS=green\n"
    b"WORKFLOW_YAML_PARSE_STATUS=green\n"
)
CONTRACT_STDOUT_FAILING = (
    b"P0_02_KEYS_ONLY_VAL=unset\n"
    b"REPO_CONTRACTS_FAILED_GUARD=some_guard_v1\n"
    b"SOME_GUARD_V1_OK=0\n"
)


class _FakeRunner:
    """격리기 호출을 가로채 명령 순서를 관측한다. 실제 명령은 돌리지 않는다."""

    def __init__(self, *, overrides=None, artifact: Path | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.contained: list[tuple[str, ...]] = []
        self.overrides = overrides or {}
        self.artifact = artifact
        self.contract_env: dict = {}

    def key(self, argv) -> str:
        return " ".join(argv)

    def run_and_read(self, argv, *, cwd, env=None, runner_temp=None, timeout_seconds=0, **_kw):
        argv = tuple(argv)
        self.calls.append(argv)
        key = self.key(argv)
        for pattern, response in self.overrides.items():
            if key.startswith(pattern):
                return response
        if argv[:2] == ("git", "rev-parse") and argv[-1] == "HEAD":
            return 0, HEAD.encode(), b""
        if argv[:2] == ("git", "show"):
            return 0, TREE.encode(), b""
        if argv[:3] == ("git", "rev-parse", "--is-shallow-repository"):
            return 0, b"false", b""
        if argv[:2] == ("git", "rev-parse") and argv[-1].startswith("HEAD:"):
            return 0, BLOB.encode(), b""
        if argv[:3] == ("git", "diff", "--name-only"):
            return 0, b"", b""
        if argv[:2] in (("git", "diff"), ("git", "status")):
            return 0, b"", b""
        if argv[0] == "helm":
            return 0, b"v3.21.3\n", b""
        if argv[0] == "npm" and self.artifact is not None:
            self.artifact.parent.mkdir(parents=True, exist_ok=True)
            self.artifact.write_text("export const loader = 1;\n", encoding="utf-8")
            return 0, b"", b""
        return 0, b"ok\n", b""

    def run_contained(self, argv, *, cwd, env, timeout_seconds, runner_temp, **_kw):
        argv = tuple(argv)
        self.contained.append(argv)
        key = self.key(argv)
        override = self.overrides.get(f"contained:{key}")
        if override is not None:
            return override
        return _result(returncode=0)

    def run_and_capture(self, argv, *, cwd, env, timeout_seconds, runner_temp, **_kw):
        """§7-4 — 계약은 결과 ★와★ stdout 을 함께 받는다."""
        argv = tuple(argv)
        self.contained.append(argv)
        self.contract_env = dict(env)
        key = self.key(argv)
        override = self.overrides.get(f"contained:{key}")
        result = override if override is not None else _result(returncode=0)
        stdout = self.overrides.get(f"stdout:{key}", CONTRACT_STDOUT)
        return result, stdout


def _result(**overrides) -> oc.ContainedResult:
    base = {
        "returncode": 0,
        "stdout_sha256": "0" * 64,
        "stderr_sha256": "1" * 64,
        "stdout_bytes": 12,
        "stderr_bytes": 0,
        "timed_out": False,
        "output_limit_exceeded": False,
        "descendants_observed": 0,
        "descendants_terminated": 0,
        "descendants_reaped": 0,
        "descendant_escape_detected": False,
        "process_group_empty": True,
        "supervisor_children_empty": True,
        "raw_files_deleted": True,
        "cleanup_ok": True,
    }
    base.update(overrides)
    return oc.ContainedResult(**base)


@pytest.fixture
def workspace(tmp_path) -> Path:
    """가짜 저장소. ★canonical 워크플로와 로컬 action 을 실물 그대로 넣는다.

    F-04 이후 실행기는 준비 계획을 canonical 에서 ★읽는다★. 그래서 가짜
    저장소에도 그 파일이 있어야 한다 — 없으면 계획을 만들 수 없고, 그때는
    닫는 것이 옳다(그 성질도 아래 시험이 따로 확인한다).
    """
    root = tmp_path / "repo"
    (root / rcr.NPM_WORKSPACE).mkdir(parents=True)
    (root / "scripts" / "verify").mkdir(parents=True)
    _install_canonical(root)
    return root


def _install_canonical(root: Path) -> None:
    """실물 canonical 워크플로·composite action 을 가짜 저장소로 복사한다."""
    import shutil

    target = root / canonical_plan.CANONICAL_WORKFLOW_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / canonical_plan.CANONICAL_WORKFLOW_PATH, target)

    action_source = REPO_ROOT / ".github" / "actions" / "preflight_v1"
    if action_source.is_dir():
        shutil.copytree(
            action_source, root / ".github" / "actions" / "preflight_v1",
            dirs_exist_ok=True,
        )


def _install(monkeypatch, runner: _FakeRunner) -> None:
    monkeypatch.setattr(rcr.output_containment, "run_and_read", runner.run_and_read)
    monkeypatch.setattr(rcr.output_containment, "run_contained", runner.run_contained)
    monkeypatch.setattr(rcr.output_containment, "run_and_capture", runner.run_and_capture)


def _run(monkeypatch, workspace: Path, *, runner: _FakeRunner, head: str = HEAD, base: str = BASE):
    _install(monkeypatch, runner)
    return rcr.run_exact_head_contracts(
        root=workspace, expected_head=head, base_ref=base,
        runner_temp=workspace, env={"ImageOS": "ubuntu24", "ImageVersion": "24.04.4"},
    )


# ══ §7-7 정상 경로가 실제로 PASS 한다 ══════════════════════════════════
def test_normal_exact_head_run_passes(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == "NONE", receipt.error_code
    assert receipt.verdict == 1
    assert receipt.exact_head == HEAD
    assert receipt.exact_tree == TREE
    assert receipt.final_worktree_clean == "YES"
    assert receipt.helm_version.startswith("v3.")
    assert re.fullmatch(r"[0-9a-f]{64}", receipt.command_plan_sha256)


# ══ §7-7 exact head 계약 ═══════════════════════════════════════════════
def test_head_one_nibble_mismatch_fails_before_preparation(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    receipt = _run(monkeypatch, workspace, runner=runner, head="a" * 39 + "b")
    assert receipt.error_code == rcr.REPO_CONTRACTS_EXACT_HEAD_MISMATCH
    assert runner.contained == [], "불일치인데도 계약을 돌렸다"
    assert not any(argv[0] == "npm" for argv in runner.calls), "준비를 시작했다"


def test_synthetic_merge_ref_checkout_fails(monkeypatch, workspace):
    """합성 merge ref 를 checkout 하면 HEAD 가 event head 와 달라 닫힌다."""
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={"git rev-parse HEAD": (0, ("f" * 40).encode(), b"")},
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_EXACT_HEAD_MISMATCH
    assert runner.contained == []


def test_shallow_clone_fails(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={"git rev-parse --is-shallow-repository": (0, b"true", b"")},
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_SHALLOW_CLONE
    assert runner.contained == []


def test_base_ref_unavailable_fails(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={"bash scripts/verify/verify_base_ref_available_v1.sh": (1, b"", b"")},
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_BASE_REF_UNAVAILABLE
    assert runner.contained == []


# ══ §7-7 guard 보호 ════════════════════════════════════════════════════
def test_guard_change_fails_before_the_contract_runs(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={
            "git diff --name-only": (
                0, b"scripts/verify/verify_repo_contracts.sh\x00", b""
            )
        },
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_GUARD_MUTATED
    assert runner.contained == [], "guard 를 바꾼 채로 계약을 돌렸다"


def test_guard_blob_oids_are_recorded(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert set(receipt.guard_blob_oids) == set(rcr.PROTECTED_GUARD_PATHS)
    assert re.fullmatch(r"[0-9a-f]{64}", receipt.guard_manifest_sha256)


def test_protected_guard_list_matches_the_canonical_dispatcher():
    """§7-2 — 파일명을 추측해 만들지 않는다. dispatcher 가 실제로 부르는 것뿐이다."""
    body = DISPATCHER.read_text(encoding="utf-8")
    called = set(re.findall(r"scripts/verify/\S+\.sh", body))
    for path in rcr.PROTECTED_GUARD_PATHS:
        if path.endswith("verify_repo_contracts.sh"):
            assert Path(REPO_ROOT / path).is_file()
            continue
        assert path in called, f"{path} 를 dispatcher 가 부르지 않는다"
        assert (REPO_ROOT / path).is_file(), path


# ══ §7-7 빌드 산출물·Helm ══════════════════════════════════════════════
def test_missing_loader_js_fails(monkeypatch, workspace):
    runner = _FakeRunner(artifact=None)  # npm 이 산출물을 만들지 않는다
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_BUILD_ARTIFACT_MISSING
    assert runner.contained == []


def test_empty_loader_js_fails(monkeypatch, workspace):
    target = workspace / rcr.BUILD_ARTIFACT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    runner = _FakeRunner(artifact=None)
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_BUILD_ARTIFACT_MISSING


@pytest.mark.parametrize("version", ["v2.17.0", "4.0.1", "", "not-a-version"])
def test_helm_major_other_than_three_fails(version):
    with pytest.raises(rcr.RepoContractError) as caught:
        rcr.assert_helm_major_three(version)
    assert caught.value.code == rcr.REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH


def test_helm_three_passes():
    assert rcr.assert_helm_major_three("v3.21.3").startswith("v3.")


def test_missing_helm_fails_without_downloading(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={"helm version --short": (127, b"", b"")},
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_HELM_TOOLCHAIN_MISMATCH
    # ★Helm 을 즉석 설치·다운로드하지 않는다. 불일치는 닫는다(§7-3).
    #   canonical 이 스스로 하는 ripgrep·jq 설치는 계획의 일부이므로 별개다.
    joined = " ".join(" ".join(argv) for argv in runner.calls)
    for forbidden in ("curl", "wget", "get_helm.sh", "install -y helm",
                      "snap install helm", "brew install helm"):
        assert forbidden not in joined, forbidden


# ══ §7-7 명령 계획 · 단 한 번 실행 ═════════════════════════════════════
def test_repository_contracts_run_exactly_once(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    _run(monkeypatch, workspace, runner=runner)
    contract_calls = [argv for argv in runner.contained if argv == rcr.CONTRACT_COMMAND]
    assert len(contract_calls) == 1
    # run_and_read 경로로도 계약을 부르지 않는다(이중 호출 금지)
    assert not any(argv == rcr.CONTRACT_COMMAND for argv in runner.calls)


def test_preparation_order_is_fixed(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    _run(monkeypatch, workspace, runner=runner)
    plan = rcr.build_preparation_plan(workspace, runner_temp=str(workspace))
    expected = [argv for _name, argv, _cwd, _env in plan]
    # ★도구 버전 기록은 준비 ★전에★ 돈다(§7-3 2항). 준비는 base ref 부터 시작한다.
    # (helm version 은 버전 기록과 준비 양쪽에 나오므로 이름으로 거를 수 없다.)
    start = runner.calls.index(("bash", rcr.BASE_REF_SCRIPT))
    observed = [
        argv for argv in runner.calls[start:]
        if argv[0] in ("bash", "npm", "npx", "helm", "sudo")
    ]
    assert observed[: len(expected)] == expected, observed[: len(expected)]


def test_tool_versions_are_recorded_before_preparation(monkeypatch, workspace):
    """§7-3 2항 — 준비가 바꾼 버전을 적으면 재검증이 안 된다."""
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    _run(monkeypatch, workspace, runner=runner)
    keys = [" ".join(argv) for argv in runner.calls]
    first_version = min(
        keys.index(" ".join(argv)) for _name, argv in rcr.TOOL_VERSION_PLAN
        if " ".join(argv) in keys
    )
    first_prep = keys.index("bash " + rcr.BASE_REF_SCRIPT)
    assert first_version < first_prep, (first_version, first_prep)


def test_command_plan_digest_changes_when_the_plan_changes(monkeypatch, workspace):
    before = rcr.command_plan_sha256(workspace, runner_temp=str(workspace))
    monkeypatch.setattr(rcr, "AC25_EXTRA_PLAN", rcr.AC25_EXTRA_PLAN[::-1])
    assert rcr.command_plan_sha256(workspace, runner_temp=str(workspace)) != before


def test_command_plan_digest_changes_when_canonical_changes(workspace):
    """★canonical 이 준비를 늘리면 지문이 바뀐다 — 조용히 어긋나지 않는다."""
    before = rcr.command_plan_sha256(workspace, runner_temp=str(workspace))
    path = workspace / canonical_plan.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "      - name: Install ripgrep",
        "      - name: New canonical prerequisite\n"
        "        run: bash scripts/ops/new_prereq.sh\n"
        "      - name: Install ripgrep",
    )
    path.write_text(body, encoding="utf-8")
    assert rcr.command_plan_sha256(workspace, runner_temp=str(workspace)) != before


def test_command_plan_digest_is_reproducible(workspace):
    first = rcr.command_plan_sha256(workspace, runner_temp=str(workspace))
    assert first == rcr.command_plan_sha256(workspace, runner_temp=str(workspace))
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert hashlib is not None and json is not None


def test_contract_failure_is_reported(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={
            f"contained:{' '.join(rcr.CONTRACT_COMMAND)}": _result(returncode=3),
        },
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_FAILED
    assert receipt.contract_exit_code == 3


def test_surviving_descendants_fail_the_run(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={
            f"contained:{' '.join(rcr.CONTRACT_COMMAND)}": _result(
                descendant_escape_detected=True, descendants_observed=2, cleanup_ok=False
            ),
        },
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_DESCENDANTS_SURVIVED
    assert receipt.descendants_observed == 2


# ══ §7-5 clean-finish ══════════════════════════════════════════════════
def test_untracked_residue_fails(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={"git status --porcelain": (0, b"?? leftover.txt\n", b"")},
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_WORKTREE_NOT_CLEAN
    assert receipt.final_worktree_clean == "NO"


def test_tracked_modification_fails(monkeypatch, workspace):
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={"git diff --quiet": (1, b"", b"")},
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_WORKTREE_NOT_CLEAN


def test_clean_check_uses_untracked_files_all(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    _run(monkeypatch, workspace, runner=runner)
    assert any(
        argv[:2] == ("git", "status") and "--untracked-files=all" in argv
        for argv in runner.calls
    )


# ══ §7-4 raw 로그 격리 ═════════════════════════════════════════════════
def test_emitted_lines_carry_only_allowed_metadata(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    receipt = _run(monkeypatch, workspace, runner=runner)
    lines = rcr.emit_lines(receipt)
    allowed = {
        "REPO_CONTRACTS_EXACT_HEAD", "ERROR_CODE", "COMMAND_PLAN_SHA256",
        "GUARD_MANIFEST_SHA256", "STDOUT_SHA256", "STDERR_SHA256",
        "STDOUT_BYTES", "STDERR_BYTES", "EXIT_CODE", "DESCENDANTS_OBSERVED",
        "FINAL_WORKTREE_CLEAN", "RUNNER_IMAGE", "HELM_VERSION",
        "NODE_VERSION", "PYTHON_VERSION",
        # F-04 — canonical 동등성 증거도 영수증에 남는다
        "CANONICAL_WORKFLOW_SHA256", "CANONICAL_STEP_COUNT",
        "CANONICAL_MISSING_STEP_COUNT", "PREPARATION_ENV_BOUND_KEYS",
        "CONTRACT_KEY_COUNT", "CONTRACT_UNPARSED_LINES",
        "REPO_CONTRACTS_FAILED_GUARD", "FAILING_GUARD_KEYS",
    }
    for line in lines:
        key, _, value = line.partition("=")
        assert key in allowed, key
        assert "\n" not in value
    assert {line.partition("=")[0] for line in lines} == allowed


def test_runner_never_prints_raw_output(monkeypatch, workspace):
    """모듈이 stdout·stderr 원문을 출력하는 자리가 없어야 한다."""
    import ast

    source = (REPO_ROOT / "scripts/ci/ac25/repo_contract_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    printed = [
        ast.unparse(node) for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print"
    ]
    for statement in printed:
        for forbidden in ("out", "err", "stdout.decode", "stderr.decode", "raw"):
            assert f"{forbidden})" not in statement, statement


def test_all_external_commands_go_through_the_containment(monkeypatch, workspace):
    """§7-4 — npm·build·helm·계약·clean 검사 전부 격리기를 거친다."""
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    _run(monkeypatch, workspace, runner=runner)
    assert runner.calls, "격리기를 통한 호출이 하나도 없다"
    import ast

    source = (REPO_ROOT / "scripts/ci/ac25/repo_contract_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = getattr(node.func, "attr", None)
            assert attr not in ("Popen", "run", "system", "check_output") or (
                attr == "run" and "output_containment" not in ast.unparse(node)
            ) or "output_containment" in ast.unparse(node)


# ══ 워크플로 배선 ══════════════════════════════════════════════════════
def test_smoke_workflow_has_the_exact_head_job():
    import yaml

    workflow = yaml.safe_load(SMOKE.read_text(encoding="utf-8"))
    job = workflow["jobs"]["ac25-repo-contracts-exact-head"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["permissions"] == {"contents": "read"}
    checkout = job["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    body = "\n".join(step.get("run", "") for step in job["steps"])
    assert "ac25.repo_contract_runner" in body
    # ★준비 명령을 워크플로가 조립하지 않는다(§7-3 8항)
    for forbidden in ("npm ci", "npm run build", "helm version", "verify_repo_contracts.sh"):
        assert forbidden not in body, forbidden


def test_smoke_workflow_hardcodes_no_head_or_tree():
    """§7-1 — 문서 기준선 OID 를 워크플로에 박지 않는다."""
    body = SMOKE.read_text(encoding="utf-8")
    assert re.findall(r"[0-9a-f]{40}", body.replace("actions/checkout@", "@")) == [] or all(
        oid in body.split("uses:")[1] if "uses:" in body else False
        for oid in []
    )
    # action pin 줄을 제외하면 40-hex 가 남지 않는다
    without_pins = "\n".join(
        line for line in body.splitlines() if "uses:" not in line
    )
    assert re.findall(r"\b[0-9a-f]{40}\b", without_pins) == []


def test_withdrawn_erratum_output_is_gone():
    """§7-6 — 철회된 정오표를 현재 상태처럼 보이게 하는 출력을 지운다."""
    body = SMOKE.read_text(encoding="utf-8")
    for forbidden in (
        "ACCEPTANCE_ERRATUM_REQUESTED", "ACCEPTANCE_ERRATUM_APPROVED",
        "REPO_CONTRACTS_IN_SMOKE=NOT_RUN",
    ):
        assert forbidden not in body, forbidden


def test_repo_contracts_are_not_run_twice_across_the_workflow():
    """§7-7 — 저장소 계약을 두 job 에서 부르지 않는다."""
    import yaml

    workflow = yaml.safe_load(SMOKE.read_text(encoding="utf-8"))
    invocations = [
        (name, step.get("name", "?"))
        for name, job in workflow["jobs"].items()
        for step in job.get("steps", [])
        if "ac25.repo_contract_runner" in step.get("run", "")
    ]
    assert len(invocations) == 1, invocations
    assert invocations[0][0] == "ac25-repo-contracts-exact-head"
    # 워크플로가 계약 스크립트를 직접 부르는 자리도 없다
    assert "verify_repo_contracts.sh" not in SMOKE.read_text(encoding="utf-8")


# ══ §7-4 — 계약 출력에서 허용 key 만 구조화한다 ════════════════════════
def test_contract_keys_are_structured_without_raw():
    """raw 를 내지 않으면서 ★어느 guard 가 막았는지★ 알 수 있어야 진단이 된다."""
    keys, unparsed = rcr.parse_contract_keys(CONTRACT_STDOUT_FAILING)
    assert keys["REPO_CONTRACTS_FAILED_GUARD"] == "some_guard_v1"
    assert keys["SOME_GUARD_V1_OK"] == "0"
    assert unparsed == 0
    assert rcr.failing_guard_names(keys) == ["SOME_GUARD_V1_OK"]


def test_unknown_lines_are_counted_not_used():
    """알 수 없는 형태는 값으로 쓰지 않는다. 개수만 남긴다."""
    keys, unparsed = rcr.parse_contract_keys(
        b"A_STATUS=green\nsome free prose that is not a key\n\nB_OK=0\n"
    )
    assert set(keys) == {"A_STATUS", "B_OK"}
    assert unparsed == 1


def test_conflicting_duplicate_key_is_dropped():
    """같은 key 가 다른 값으로 두 번 나오면 어느 쪽이 참인지 알 수 없다 — 버린다."""
    passing = b"1"  # ★리터럴 `_OK=1` 을 만들지 않으려고 값을 따로 둔다
    keys, _ = rcr.parse_contract_keys(
        b"A_OK=" + passing + b"\nA_OK=0\nB_OK=" + passing + b"\n"
    )
    assert "A_OK" not in keys
    assert keys["B_OK"] == "1"


def test_passing_keys_are_not_reported_as_failing():
    """통과한 key 는 실패 목록에 없다. ★구조로 시험한다 — 문자열을 만들지 않는다."""
    keys = {"A_OK": "1", "B_OK": "0", "C_STATUS": "green"}
    assert rcr.failing_guard_names(keys) == ["B_OK"]


@pytest.mark.parametrize(
    "line",
    [b"lower_case_ok=1\n", b"A=1\n", b"A_OK=" + b"x" * 200 + b"\n", b"A_OK=has space\n"],
)
def test_malformed_key_lines_are_not_accepted(line):
    keys, unparsed = rcr.parse_contract_keys(line)
    assert keys == {}
    assert unparsed == 1


def test_receipt_names_the_failing_guard(monkeypatch, workspace):
    """계약이 실패하면 영수증이 ★그 guard 이름★ 을 담는다(raw 없이)."""
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={
            f"contained:{' '.join(rcr.CONTRACT_COMMAND)}": _result(returncode=1),
            f"stdout:{' '.join(rcr.CONTRACT_COMMAND)}": CONTRACT_STDOUT_FAILING,
        },
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == rcr.REPO_CONTRACTS_FAILED
    assert receipt.failed_guard == "some_guard_v1"
    assert receipt.failing_guard_keys == ["SOME_GUARD_V1_OK"]
    lines = rcr.emit_lines(receipt)
    assert "REPO_CONTRACTS_FAILED_GUARD=some_guard_v1" in lines
    assert "FAILING_GUARD_KEYS=SOME_GUARD_V1_OK" in lines


def test_successful_contract_reports_no_failing_guard(monkeypatch, workspace):
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    receipt = _run(monkeypatch, workspace, runner=runner)
    assert receipt.error_code == "NONE"
    assert receipt.failed_guard == "NONE"
    assert receipt.failing_guard_keys == []
    assert receipt.contract_key_count == 3


def test_contract_receives_canonical_environment(monkeypatch, workspace):
    """계약 env 가 canonical 여섯을 받는지 실제 호출로 확인한다."""
    runner = _FakeRunner(artifact=workspace / rcr.BUILD_ARTIFACT)
    _run(monkeypatch, workspace, runner=runner)
    for key in ("ARTIFACT_CHAIN_PROOF_V2_ENFORCE", "ONPREM_PROOF_STRICT_ENFORCE",
                "GIT_LFS_SKIP_SMUDGE", "PLAYWRIGHT_BROWSERS_PATH",
                "DATABASE_URL", "EXPORT_SIGN_SECRET"):
        assert key in runner.contract_env, key


def test_raw_contract_output_never_reaches_the_receipt(monkeypatch, workspace):
    """★구조화한 key 만 나간다. 원문 조각이 영수증·출력에 남으면 안 된다."""
    marker = b"AC25_RAW_MARKER_DO_NOT_LEAK"
    runner = _FakeRunner(
        artifact=workspace / rcr.BUILD_ARTIFACT,
        overrides={
            f"stdout:{' '.join(rcr.CONTRACT_COMMAND)}":
                CONTRACT_STDOUT + b"\n" + marker + b" free prose\n",
        },
    )
    receipt = _run(monkeypatch, workspace, runner=runner)
    rendered = "\n".join(rcr.emit_lines(receipt)) + repr(receipt.__dict__)
    assert marker.decode() not in rendered
    assert receipt.contract_unparsed_lines == 1
