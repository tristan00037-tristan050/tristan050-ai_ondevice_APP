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
    executed = tuple(" ".join(argv) for _name, argv, _cwd in built)
    assert cp.missing_steps(plan, executed) == ()


def test_runner_plan_preserves_canonical_order(repo):
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    built = rcr.build_preparation_plan(repo, runner_temp="/tmp")
    keys = [" ".join(argv) for _name, argv, _cwd in built]
    positions = [keys.index(key) for key in plan.command_keys()]
    assert positions == sorted(positions), "canonical 순서가 뒤바뀌었다"


def test_runner_contract_environment_includes_canonical_env(repo):
    env = rcr.contract_environment(repo, base_env={"PATH": "/usr/bin"}, runner_temp="/tmp")
    plan = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    for key, value in plan.contract_env:
        assert env[key] == value, key
    assert env["PATH"] == "/usr/bin"


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
