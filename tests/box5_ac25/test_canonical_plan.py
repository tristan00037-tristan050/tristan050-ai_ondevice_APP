"""F-04 — canonical 준비 계획과의 동등성이 ★기계로★ 고정되는가.

감사 F-04: 두 안 모두 자기가 정의한 축소 계획을 들고 있었다. canonical
`product-verify-repo-guards.yml` 은 그보다 많은 준비를 한 뒤 계약을 돌린다.

지시서 §4-2 4항
    · canonical 의 준비 단계와 환경변수를 단일 정본 계획으로 추출하거나
      동등성을 기계 검증한다
    · ★자기가 정의한 축소 계획이 아니라 canonical 과의 완전 일치를
      부정 시험으로 고정한다

이 파일이 그 부정 시험이다. canonical 이 준비를 늘리면 여기서 빨간불이 켜진다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from ac25 import canonical_plan as cp
from ac25 import repo_contract_runner as rcr

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path) -> Path:
    """canonical 워크플로와 composite action 을 담은 가짜 저장소."""
    root = tmp_path / "repo"
    target = root / cp.CANONICAL_WORKFLOW_PATH
    target.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / cp.CANONICAL_WORKFLOW_PATH, target)
    shutil.copytree(
        REPO_ROOT / ".github" / "actions" / "preflight_v1",
        root / ".github" / "actions" / "preflight_v1",
    )
    return root


# ══ 추출이 실물과 일치한다 ═════════════════════════════════════════════
def test_canonical_plan_is_extracted_from_the_real_workflow():
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/runner/temp")
    keys = plan.command_keys()
    # canonical 이 실제로 하는 준비가 전부 잡혀야 한다
    for required in (
        "bash scripts/verify/verify_base_ref_available_v1.sh",
        "sudo apt-get install -y ripgrep jq",
        "bash tools/preflight_v1.sh",
        "bash scripts/verify/verify_ops_deps.sh --require-node-npm --require-rg --require-jq",
        "npm --prefix webcore_appcore_starter_4_17/scripts/web_e2e ci",
        "npx --prefix webcore_appcore_starter_4_17/scripts/web_e2e playwright "
        "install --with-deps chromium",
        "bash scripts/ops/gen_build_stamp_v1.sh",
        "bash scripts/ops/gen_artifact_chain_proof_v2.sh",
    ):
        assert required in keys, required


def test_workflow_level_steps_are_separated_not_faked():
    """checkout·setup-node 는 명령으로 흉내내지 않는다. 워크플로가 해야 한다."""
    plan = cp.extract_canonical_plan(REPO_ROOT)
    assert any(ref.startswith("actions/checkout@") for ref in plan.workflow_level)
    assert any(ref.startswith("actions/setup-node@") for ref in plan.workflow_level)
    for key in plan.command_keys():
        assert not key.startswith("actions/")


def test_local_composite_action_is_resolved_to_its_commands():
    plan = cp.extract_canonical_plan(REPO_ROOT)
    assert "bash tools/preflight_v1.sh" in plan.command_keys()


def test_contract_environment_is_extracted():
    """계약에 넘기는 환경변수 여섯을 그대로 가져온다."""
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/runner/temp")
    env = dict(plan.contract_env)
    assert env["ARTIFACT_CHAIN_PROOF_V2_ENFORCE"] == "1"
    assert env["ONPREM_PROOF_STRICT_ENFORCE"] == "0"
    assert env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == "/runner/temp/ms-playwright"
    assert "DATABASE_URL" in env and "EXPORT_SIGN_SECRET" in env
    assert plan.contract_argv == ("bash", cp.CONTRACT_SCRIPT)


def test_expressions_are_resolved_not_left_as_text():
    """`${{ runner.temp }}` 가 문자열로 남으면 없는 경로를 가리킨다."""
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/x/y")
    for _key, value in plan.contract_env:
        assert "${{" not in value
    assert cp.resolve_expressions("${{ runner.temp }}/z", runner_temp="/x/y") == "/x/y/z"


def test_unknown_expression_is_fail_closed():
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.resolve_expressions("${{ secrets.TOKEN }}", runner_temp="/x")
    assert caught.value.code == cp.CANONICAL_PLAN_INCOMPLETE


# ══ ★완전 일치 부정 시험 — canonical 이 앞서가면 잡힌다 ════════════════
def test_missing_step_is_reported_when_canonical_adds_one(repo):
    """canonical 이 준비를 늘렸는데 우리가 안 하면 그 목록이 나와야 한다."""
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "      - name: Install ripgrep",
        "      - name: Brand new prerequisite\n"
        "        run: bash scripts/ops/brand_new_prereq.sh\n"
        "      - name: Install ripgrep",
    )
    path.write_text(body, encoding="utf-8")

    plan = cp.extract_canonical_plan(repo)
    # 새 단계를 뺀 채로 실행했다고 가정한다
    executed = tuple(
        key for key in plan.command_keys()
        if key != "bash scripts/ops/brand_new_prereq.sh"
    )
    gaps = cp.missing_steps(plan, executed)
    assert gaps == ("bash scripts/ops/brand_new_prereq.sh",)


def test_no_missing_step_when_plan_covers_canonical(repo):
    plan = cp.extract_canonical_plan(repo)
    assert cp.missing_steps(plan, plan.command_keys()) == ()


def test_extra_ac25_steps_are_allowed(repo):
    """AC-25 는 canonical 보다 ★더★ 해도 된다. ★덜★ 하면 안 된다."""
    plan = cp.extract_canonical_plan(repo)
    executed = plan.command_keys() + ("npm ci", "helm version --short")
    assert cp.missing_steps(plan, executed) == ()


def test_runner_plan_covers_every_canonical_step(repo):
    """실행기가 만드는 계획이 canonical 을 ★전부★ 덮는지 본다."""
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    built = rcr.build_preparation_plan(repo, runner_temp="/tmp")
    executed = tuple(" ".join(argv) for _name, argv, _cwd, _env in built)
    assert cp.missing_steps(plan, executed) == ()


def test_runner_plan_preserves_canonical_order(repo):
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    built = rcr.build_preparation_plan(repo, runner_temp="/tmp")
    keys = [" ".join(argv) for _name, argv, _cwd, _env in built]
    positions = [keys.index(key) for key in plan.command_keys()]
    assert positions == sorted(positions), "canonical 순서가 뒤바뀌었다"


def test_runner_contract_environment_includes_canonical_env(repo):
    env = rcr.contract_environment(repo, base_env={"PATH": "/usr/bin"}, runner_temp="/tmp")
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    for key, value in plan.contract_env:
        assert env[key] == value, key
    assert env["PATH"] == "/usr/bin"


# ══ v2.0 §4-1 — 준비 env 가 실행 계획에 결속된다 ═══════════════════════
def test_preparation_steps_carry_their_canonical_env(repo):
    """★읽어 놓고 버리면 명령은 같아도 실행 환경이 다르다.

    이전 판은 `CanonicalStep.env` 를 읽고 `(name, argv, cwd)` 로 내리면서
    버렸다. 감사가 `F04_PREPARATION_ENV_BINDING_DROPPED` 라 부른 자리다.
    """
    built = rcr.build_preparation_plan(repo, runner_temp="/runner/temp")
    for item in built:
        assert len(item) == 4, "계획 항목은 (name, argv, cwd, env) 여야 한다"

    by_command = {" ".join(argv): dict(env) for _n, argv, _c, env in built}

    # canonical 이 job 수준으로 건 env 는 모든 canonical 단계에 실린다
    assert by_command["bash tools/preflight_v1.sh"]["GIT_LFS_SKIP_SMUDGE"] == "1"
    # step 수준 env 도 그 단계에만 실린다
    playwright = by_command[
        "npx --prefix webcore_appcore_starter_4_17/scripts/web_e2e playwright "
        "install --with-deps chromium"
    ]
    assert playwright["PLAYWRIGHT_BROWSERS_PATH"] == "/runner/temp/ms-playwright"
    # 그 단계가 아닌 곳에는 없다
    assert "PLAYWRIGHT_BROWSERS_PATH" not in by_command["bash tools/preflight_v1.sh"]


def test_removing_a_preparation_env_changes_the_plan_digest(repo):
    """canonical 의 준비 env 하나를 ★지우면★ 계획이 달라진다 — 실패한다."""
    before = rcr.command_plan_sha256(repo, runner_temp="/runner/temp")
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        '    env:\n      GIT_LFS_SKIP_SMUDGE: "1"\n', "", 1
    )
    path.write_text(body, encoding="utf-8")
    assert rcr.command_plan_sha256(repo, runner_temp="/runner/temp") != before


def test_changing_a_preparation_env_value_changes_the_plan_digest(repo):
    """값을 ★바꾸면★ 실패한다."""
    before = rcr.command_plan_sha256(repo, runner_temp="/runner/temp")
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "${{ runner.temp }}/ms-playwright", "/attacker/ms-playwright"
    )
    path.write_text(body, encoding="utf-8")
    assert rcr.command_plan_sha256(repo, runner_temp="/runner/temp") != before


def test_preparation_env_is_actually_passed_to_the_command(repo, monkeypatch, tmp_path):
    """★계획에만 있고 실행에 안 실리면 결속이 아니다. 실제 호출 env 를 본다."""
    seen: list[tuple[str, dict]] = []

    def capture(argv, *, cwd, env=None, runner_temp=None, timeout_seconds=0, **_kw):
        argv = tuple(argv)
        seen.append((" ".join(argv), dict(env or {})))
        if argv[0] == "helm":
            return 0, b"v3.21.3\n", b""
        if argv[:2] == ("git", "rev-parse") and argv[-1] == "HEAD":
            return 0, ("a" * 40).encode(), b""
        if argv[:2] == ("git", "show"):
            return 0, ("b" * 40).encode(), b""
        if argv[:3] == ("git", "rev-parse", "--is-shallow-repository"):
            return 0, b"false", b""
        if argv[:2] == ("git", "rev-parse") and argv[-1].startswith("HEAD:"):
            return 0, ("d" * 40).encode(), b""
        if argv[0] == "npm":
            artifact = repo / rcr.BUILD_ARTIFACT
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("x", encoding="utf-8")
        return 0, b"", b""

    contract_env: dict = {}

    def contract(argv, *, cwd, env, timeout_seconds, runner_temp, **_kw):
        contract_env.update(env)
        return rcr.output_containment.ContainedResult(
            returncode=0, stdout_sha256="0" * 64, stderr_sha256="1" * 64,
            stdout_bytes=0, stderr_bytes=0, timed_out=False,
            output_limit_exceeded=False, descendants_observed=0,
            descendants_terminated=0, descendants_reaped=0,
            descendant_escape_detected=False, process_group_empty=True,
            supervisor_children_empty=True, raw_files_deleted=True, cleanup_ok=True,
        )

    monkeypatch.setattr(rcr.output_containment, "run_and_read", capture)
    monkeypatch.setattr(
        rcr.output_containment, "run_and_capture",
        lambda *a, **k: (contract(*a, **k), b"A_OK=1\n"),
    )
    receipt = rcr.run_exact_head_contracts(
        root=repo, expected_head="a" * 40, runner_temp=tmp_path, env={"PATH": "/usr/bin"},
    )
    assert receipt.error_code == "NONE", receipt.error_code
    by_command = dict(seen)
    playwright_key = next(k for k in by_command if "playwright" in k)
    assert by_command[playwright_key]["PLAYWRIGHT_BROWSERS_PATH"].endswith("/ms-playwright")
    assert by_command["bash tools/preflight_v1.sh"]["GIT_LFS_SKIP_SMUDGE"] == "1"
    # ★AC-25 추가 단계에는 canonical 의 step env 가 붙지 않는다
    assert "PLAYWRIGHT_BROWSERS_PATH" not in by_command["helm version --short"]
    # ★기반 환경은 그대로 살아 있다
    assert by_command["bash tools/preflight_v1.sh"]["PATH"] == "/usr/bin"
    # ★계약에도 canonical env 여섯이 실린다
    assert contract_env["ARTIFACT_CHAIN_PROOF_V2_ENFORCE"] == "1"
    assert contract_env["ONPREM_PROOF_STRICT_ENFORCE"] == "0"
    # ★영수증이 결속 사실을 증거로 남긴다
    assert "GIT_LFS_SKIP_SMUDGE" in receipt.preparation_env_keys
    assert "PLAYWRIGHT_BROWSERS_PATH" in receipt.preparation_env_keys


# ══ v2.0 §4-1 — 위조된 argv 를 통과시키지 않는다 (B2 결함 재현) ════════
def test_forged_argv_with_the_same_step_name_is_rejected(repo):
    """★단계 이름만 유지하고 argv 를 바꾸면 통과하던 것이 B2 결함이었다."""
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    forged = tuple(
        "bash scripts/ops/attacker.sh" if "preflight_v1" in key else key
        for key in plan.command_keys()
    )
    gaps = cp.missing_steps(plan, forged)
    assert "bash tools/preflight_v1.sh" in gaps


def test_forged_argument_inside_a_step_is_rejected(repo):
    """인자 하나만 빼도 다른 명령이다 — 통과시키지 않는다."""
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    forged = tuple(
        key.replace(" --require-jq", "") for key in plan.command_keys()
    )
    gaps = cp.missing_steps(plan, forged)
    assert gaps == (
        "bash scripts/verify/verify_ops_deps.sh "
        "--require-node-npm --require-rg --require-jq",
    )


def test_runner_closes_when_a_canonical_step_is_missing(repo, monkeypatch, tmp_path):
    """빠진 단계가 있으면 ★계약을 돌리지 않는다.★"""
    real_plan = rcr.build_preparation_plan(repo, runner_temp=str(tmp_path))
    monkeypatch.setattr(
        rcr, "build_preparation_plan",
        lambda *a, **k: tuple(
            item for item in real_plan if "preflight_v1" not in " ".join(item[1])
        ),
    )
    contained: list = []
    monkeypatch.setattr(
        rcr.output_containment, "run_contained",
        lambda *a, **k: contained.append(a) or None,
    )

    def fake(argv, *, cwd, env=None, runner_temp=None, timeout_seconds=0, **_kw):
        argv = tuple(argv)
        if argv[0] == "helm":
            return 0, b"v3.21.3\n", b""
        if argv[:2] == ("git", "rev-parse") and argv[-1] == "HEAD":
            return 0, ("a" * 40).encode(), b""
        if argv[:2] == ("git", "show"):
            return 0, ("b" * 40).encode(), b""
        if argv[:3] == ("git", "rev-parse", "--is-shallow-repository"):
            return 0, b"false", b""
        if argv[:2] == ("git", "rev-parse") and argv[-1].startswith("HEAD:"):
            return 0, ("d" * 40).encode(), b""
        if argv[0] == "npm":
            artifact = repo / rcr.BUILD_ARTIFACT
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("x", encoding="utf-8")
        return 0, b"", b""

    monkeypatch.setattr(rcr.output_containment, "run_and_read", fake)
    receipt = rcr.run_exact_head_contracts(
        root=repo, expected_head="a" * 40, runner_temp=tmp_path, env={"PATH": "/usr/bin"},
    )
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_MISMATCH
    assert receipt.canonical_missing_steps == ["bash tools/preflight_v1.sh"]
    assert contained == [], "빠진 단계가 있는데 계약을 돌렸다"


# ══ 읽지 못하면 닫는다 ═════════════════════════════════════════════════
def test_missing_canonical_workflow_is_fail_closed(tmp_path):
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(tmp_path)
    assert caught.value.code == cp.CANONICAL_WORKFLOW_MISSING


def test_malformed_canonical_workflow_is_fail_closed(repo):
    (repo / cp.CANONICAL_WORKFLOW_PATH).write_text("{{ not yaml", encoding="utf-8")
    with pytest.raises(cp.CanonicalPlanError):
        cp.extract_canonical_plan(repo)


def test_renamed_job_is_fail_closed(repo):
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "  product-verify-repo-guards:\n    name:", "  renamed-job:\n    name:", 1
    )
    path.write_text(body, encoding="utf-8")
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(repo)
    assert caught.value.code == cp.CANONICAL_JOB_NOT_FOUND


def test_missing_contract_step_is_fail_closed(repo):
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "bash scripts/verify/verify_repo_contracts.sh", "true", 1
    )
    path.write_text(body, encoding="utf-8")
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(repo)
    assert caught.value.code == cp.CANONICAL_CONTRACT_STEP_NOT_FOUND


def test_unresolvable_local_action_is_fail_closed(repo):
    shutil.rmtree(repo / ".github" / "actions" / "preflight_v1")
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(repo)
    assert caught.value.code == cp.CANONICAL_ACTION_UNRESOLVED


def test_runner_closes_when_canonical_is_unreadable(tmp_path, monkeypatch):
    """계획을 읽지 못하면 무엇과 같은지 말할 수 없다 — 계약을 돌리지 않는다."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    contained: list = []
    monkeypatch.setattr(
        rcr.output_containment, "run_contained",
        lambda *a, **k: contained.append(a) or None,
    )
    receipt = rcr.run_exact_head_contracts(
        root=root, expected_head="a" * 40, runner_temp=tmp_path, env={},
    )
    assert receipt.error_code == rcr.REPO_CONTRACTS_CANONICAL_PLAN_UNREADABLE
    assert receipt.verdict == 0
    assert contained == [], "계획을 못 읽었는데 계약을 돌렸다"


# ══ 지문이 변화를 잡는다 ═══════════════════════════════════════════════
def test_plan_digest_is_stable_and_sensitive(repo):
    before = cp.extract_canonical_plan(repo, runner_temp="/tmp").sha256()
    assert before == cp.extract_canonical_plan(repo, runner_temp="/tmp").sha256()

    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "--require-node-npm --require-rg --require-jq", "--require-node-npm"
    )
    path.write_text(body, encoding="utf-8")
    assert cp.extract_canonical_plan(repo, runner_temp="/tmp").sha256() != before
