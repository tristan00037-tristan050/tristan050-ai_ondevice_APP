"""A-02 — canonical 동등성이 ★포함관계가 아니라 완전 일치★ 로 고정되는가.

v3.1 §3-6 이 이 파일의 계약이다. 이전 판의 `test_extra_ac25_steps_are_allowed`
는 삭제됐고, ★반대 방향★ 시험(추가 명령 거부)으로 교체됐다 — 단순 삭제만
하고 대체 시험을 만들지 않으면 실패라고 지시서가 명시했다.

비교 다섯 축: missing · extra · reordered · mutated · unsupported.
하나라도 0 이 아니면 동등이 아니고, runner 는 계약을 실행하지 않는다.
"""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
from ac25 import canonical_plan as cp
from ac25 import repo_contract_runner as rcr

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = REPO_ROOT / "scripts" / "ci" / "ac25"


@pytest.fixture
def repo(tmp_path) -> Path:
    """canonical 워크플로 · composite action · 실행 워크플로를 담은 가짜 저장소."""
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


def _plans(root):
    expected = cp.extract_canonical_plan(root, runner_temp="/tmp")
    actual = rcr.build_execution_plan(root, runner_temp="/tmp")
    return expected, actual


def _diff(expected, actual):
    return cp.compare_exact_plan(expected=expected, actual=actual)


# ══ §3-6 ① canonical 과 완전 동일한 계획만 PASS ═══════════════════════
def test_identical_plan_is_exact(repo):
    expected, actual = _plans(repo)
    diff = _diff(expected, actual)
    assert diff.exact, dataclasses.asdict(diff)


def test_real_repository_plan_is_exact_including_approved_differences():
    """실물 저장소 — checkout ref 의 승인된 exact-head 차이만으로 PASS 다."""
    expected = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/tmp")
    actual = rcr.build_execution_plan(REPO_ROOT, runner_temp="/tmp")
    diff = _diff(expected, actual)
    assert diff.exact, dataclasses.asdict(diff)


# ══ §3-6 ② 명령 하나 추가 시 EXTRA ════════════════════════════════════
def test_one_extra_command_is_rejected(repo):
    expected, actual = _plans(repo)
    intruder = dataclasses.replace(
        actual.runs[0], index=len(actual.runs), name="smuggled build#0",
        argv=("npm", "run", "build"), source="workflow:smuggled",
    )
    forged = dataclasses.replace(actual, runs=actual.runs + (intruder,))
    diff = _diff(expected, forged)
    assert diff.extra and not diff.exact


def test_removed_npm_build_cannot_come_back_under_another_name(repo):
    """★제거한 npm ci·build 를 다른 이름·wrapper 로 되살리면 EXTRA 다(§3-5)."""
    expected, actual = _plans(repo)
    revived = dataclasses.replace(
        actual.runs[0], index=len(actual.runs), name="totally innocent step#0",
        argv=("bash", "-c", "npm ci"), source="workflow:innocent",
    )
    forged = dataclasses.replace(actual, runs=actual.runs + (revived,))
    assert _diff(expected, forged).extra


# ══ §3-6 ③ 명령 하나 누락 시 MISSING ══════════════════════════════════
def test_one_missing_command_is_rejected(repo):
    expected, actual = _plans(repo)
    forged = dataclasses.replace(actual, runs=actual.runs[:-1])
    diff = _diff(expected, forged)
    assert diff.missing and not diff.exact


# ══ §3-6 ④ 같은 명령 두 개 중 하나 누락 시 MISSING ════════════════════
def test_duplicate_command_multiplicity_is_preserved(repo):
    """set 비교였다면 중복 하나가 사라져도 몰랐다(§11 금지 항목)."""
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "          bash scripts/ops/gen_build_stamp_v1.sh\n",
        "          bash scripts/ops/gen_build_stamp_v1.sh\n"
        "          bash scripts/ops/gen_build_stamp_v1.sh\n",
    )
    path.write_text(body, encoding="utf-8")
    expected = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    duplicated = [
        step for step in expected.preparation
        if step.argv == ("bash", "scripts/ops/gen_build_stamp_v1.sh")
    ]
    assert len(duplicated) == 2

    # 실행 측이 그중 하나만 돌리는 위조 — 잡혀야 한다
    kept = [step for step in expected.preparation if step is not duplicated[1]]
    forged = cp.ExecutionPlan(
        runs=tuple(kept),
        actions=rcr.build_execution_plan(repo, runner_temp="/tmp").actions,
        harness=rcr.build_execution_plan(repo, runner_temp="/tmp").harness,
    )
    assert _diff(expected, forged).missing


# ══ §3-6 ⑤ 순서 교환 시 REORDERED ═════════════════════════════════════
def test_swapped_order_is_rejected(repo):
    expected, actual = _plans(repo)
    swapped = list(actual.runs)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    forged = dataclasses.replace(actual, runs=tuple(swapped))
    diff = _diff(expected, forged)
    assert diff.reordered and not diff.exact


# ══ §3-6 ⑥⑦⑧⑨ argv·cwd·env·shell 변경 시 MUTATED ═════════════════════
def test_changed_argv_argument_is_rejected(repo):
    expected, actual = _plans(repo)
    victim = next(s for s in actual.runs if "--require-jq" in s.argv)
    mutated = dataclasses.replace(
        victim, argv=tuple(a for a in victim.argv if a != "--require-jq")
    )
    forged = dataclasses.replace(
        actual, runs=tuple(mutated if s is victim else s for s in actual.runs)
    )
    diff = _diff(expected, forged)
    assert diff.mutated and not diff.exact


def test_changed_cwd_is_rejected(repo):
    expected, actual = _plans(repo)
    victim = actual.runs[0]
    mutated = dataclasses.replace(victim, cwd="somewhere/else")
    forged = dataclasses.replace(
        actual, runs=(mutated,) + actual.runs[1:]
    )
    assert _diff(expected, forged).mutated


@pytest.mark.parametrize("attack", ["drop", "add", "change"])
def test_env_key_drop_add_or_value_change_is_rejected(repo, attack):
    expected, actual = _plans(repo)
    victim = next(s for s in actual.runs if dict(s.env).get("GIT_LFS_SKIP_SMUDGE"))
    env = dict(victim.env)
    if attack == "drop":
        env.pop("GIT_LFS_SKIP_SMUDGE")
    elif attack == "add":
        env["INJECTED"] = "x"
    else:
        env["GIT_LFS_SKIP_SMUDGE"] = "0"
    mutated = dataclasses.replace(victim, env=tuple(sorted(env.items())))
    forged = dataclasses.replace(
        actual, runs=tuple(mutated if s is victim else s for s in actual.runs)
    )
    assert _diff(expected, forged).mutated, attack


def test_changed_shell_is_rejected(repo):
    expected, actual = _plans(repo)
    victim = actual.runs[0]
    mutated = dataclasses.replace(victim, shell="sh")
    forged = dataclasses.replace(actual, runs=(mutated,) + actual.runs[1:])
    assert _diff(expected, forged).mutated


# ══ §3-6 ⑩⑪ action ref family · with 변경 시 ACTION_MISMATCH ══════════
def test_action_family_change_is_rejected(repo):
    expected, actual = _plans(repo)
    victim = actual.actions[0]
    mutated = dataclasses.replace(
        victim, uses="attacker/checkout@" + "a" * 40
    )
    forged = dataclasses.replace(actual, actions=(mutated,) + actual.actions[1:])
    diff = _diff(expected, forged)
    offending = diff.missing + diff.extra + diff.mutated
    assert any(item.startswith("action:") for item in offending)


def test_action_fetch_depth_change_is_rejected(repo):
    expected, actual = _plans(repo)
    victim = next(a for a in actual.actions if a.family == "actions/checkout")
    with_args = dict(victim.with_args)
    with_args["fetch-depth"] = "1"
    mutated = dataclasses.replace(victim, with_args=tuple(sorted(with_args.items())))
    forged = dataclasses.replace(
        actual, actions=tuple(mutated if a is victim else a for a in actual.actions)
    )
    diff = _diff(expected, forged)
    assert any("fetch-depth" in item for item in diff.mutated)


def test_unapproved_action_pin_is_rejected(repo):
    """full SHA 라도 ★승인 목록에 없으면★ 통과하지 않는다(§3-3 ②)."""
    expected, actual = _plans(repo)
    victim = actual.actions[0]
    mutated = dataclasses.replace(
        victim, uses=f"{victim.family}@{'f' * 40}"
    )
    forged = dataclasses.replace(
        actual, actions=tuple(mutated if a is victim else a for a in actual.actions)
    )
    assert _diff(expected, forged).mutated


def test_checkout_ref_other_than_exact_head_is_rejected(repo):
    """허용된 ref 차이는 exact PR head ★하나뿐★ 이다(§3-3 ①)."""
    expected, actual = _plans(repo)
    victim = next(a for a in actual.actions if a.family == "actions/checkout")
    with_args = dict(victim.with_args)
    with_args["ref"] = "refs/heads/main"
    mutated = dataclasses.replace(victim, with_args=tuple(sorted(with_args.items())))
    forged = dataclasses.replace(
        actual, actions=tuple(mutated if a is victim else a for a in actual.actions)
    )
    assert any("ref" in item for item in _diff(expected, forged).mutated)


def test_approved_pins_match_the_real_workflow():
    """승인 pin 표가 실물 워크플로의 pin 과 어긋나면 여기서 잡힌다."""
    actions, _harness = cp.extract_execution_workflow(REPO_ROOT)
    for action in actions:
        assert action.ref == cp.APPROVED_ACTION_PINS[action.family], action.family


# ══ §3-5 harness — 승인된 run 하나만 ══════════════════════════════════
def test_extra_harness_run_step_is_rejected(repo):
    expected, actual = _plans(repo)
    smuggled = dataclasses.replace(
        actual.harness[0], name="extra#0", argv=("bash", "evil.sh")
    )
    forged = dataclasses.replace(actual, harness=actual.harness + (smuggled,))
    assert _diff(expected, forged).extra


def test_missing_harness_is_rejected(repo):
    expected, actual = _plans(repo)
    forged = dataclasses.replace(actual, harness=())
    assert _diff(expected, forged).missing


# ══ §3-6 ⑬ local composite action 의 working-directory 손실 시 FAIL ═══
def test_composite_working_directory_is_preserved_and_its_loss_rejected(repo):
    action_path = repo / ".github" / "actions" / "preflight_v1" / "action.yml"
    body = action_path.read_text(encoding="utf-8").replace(
        "      shell: bash\n", "      shell: bash\n      working-directory: subdir\n"
    )
    action_path.write_text(body, encoding="utf-8")

    expected = cp.extract_canonical_plan(repo, runner_temp="/tmp")
    composite = next(
        s for s in expected.preparation if s.source.startswith("action:")
    )
    assert composite.cwd == "subdir", "★working-directory 를 추출이 버렸다"

    # 실행 측이 cwd 를 잃은 채 같은 명령을 돌리는 위조 — MUTATED 다
    lost = dataclasses.replace(composite, cwd=".")
    forged_runs = tuple(
        lost if s is composite else s for s in expected.preparation
    )
    execution = rcr.build_execution_plan(repo, runner_temp="/tmp")
    forged = dataclasses.replace(execution, runs=forged_runs)
    assert _diff(expected, forged).mutated


# ══ §3-6 ⑭ 지원하지 않는 동적 문법 → UNSUPPORTED ══════════════════════
@pytest.mark.parametrize(
    "needle,replacement",
    [
        (
            "      - name: Install ripgrep\n",
            "      - name: Install ripgrep\n        if: always()\n",
        ),
        (
            "      - name: Install ripgrep\n",
            "      - name: Install ripgrep\n        continue-on-error: true\n",
        ),
        (
            "    runs-on: ubuntu-latest\n",
            "    runs-on: ubuntu-latest\n    container: node:20\n",
        ),
        (
            "    runs-on: ubuntu-latest\n",
            "    runs-on: ubuntu-latest\n    strategy:\n      fail-fast: false\n",
        ),
    ],
    ids=["if", "continue-on-error", "container", "strategy"],
)
def test_unsupported_workflow_syntax_is_closed(repo, needle, replacement):
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8")
    assert needle in body
    path.write_text(body.replace(needle, replacement, 1), encoding="utf-8")
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(repo)
    assert caught.value.code == cp.CANONICAL_PLAN_UNSUPPORTED_SEMANTICS


def test_dynamic_secrets_expression_is_closed():
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.resolve_expressions("${{ secrets.TOKEN }}", runner_temp="/x")
    assert caught.value.code == cp.CANONICAL_PLAN_UNSUPPORTED_SEMANTICS


def test_nested_uses_inside_composite_is_closed(repo):
    action_path = repo / ".github" / "actions" / "preflight_v1" / "action.yml"
    body = action_path.read_text(encoding="utf-8").replace(
        "  steps:\n",
        "  steps:\n    - name: nested\n      uses: actions/cache@v4\n",
    )
    action_path.write_text(body, encoding="utf-8")
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(repo)
    assert caught.value.code == cp.CANONICAL_PLAN_UNSUPPORTED_SEMANTICS


def test_shell_metacharacters_are_closed_not_guessed(repo):
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "bash scripts/ops/gen_build_stamp_v1.sh",
        "bash scripts/ops/gen_build_stamp_v1.sh | tee /tmp/log",
    )
    path.write_text(body, encoding="utf-8")
    with pytest.raises(cp.CanonicalPlanError) as caught:
        cp.extract_canonical_plan(repo)
    assert caught.value.code == cp.CANONICAL_PLAN_UNSUPPORTED_SEMANTICS


# ══ §3-6 ⑮ AC25_EXTRA_PLAN 식별자가 production 에 남으면 FAIL ═════════
def test_extra_plan_identifiers_are_gone_from_production():
    forbidden = ("AC25_EXTRA_PLAN", "build:packages:server", "BUILD_ARTIFACT")
    offenders = []
    for path in sorted(PRODUCTION_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        offenders += [
            f"{path.name}:{token}" for token in forbidden if token in source
        ]
    assert offenders == [], offenders


def test_the_extra_allowed_test_itself_is_gone():
    """옛 방향(추가 허용)을 고정하던 시험 ★함수★ 가 남아 있으면 안 된다(§3-6)."""
    offenders = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("def test_extra_ac25_steps_are_allowed"):
                offenders.append(path.name)
    assert offenders == [], offenders


# ══ 추출 충실도 — cwd·env·shell 합성 ══════════════════════════════════
def test_extraction_captures_the_real_preparation():
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/runner/temp")
    argvs = [" ".join(step.argv) for step in plan.preparation]
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
        assert required in argvs, required
    assert all(step.shell == "bash" for step in plan.preparation)
    assert [step.index for step in plan.preparation] == list(range(len(plan.preparation)))


def test_actions_are_recorded_with_inputs_not_faked_as_commands():
    plan = cp.extract_canonical_plan(REPO_ROOT)
    families = [action.family for action in plan.actions]
    assert families == ["actions/checkout", "actions/setup-node"]
    checkout = plan.actions[0]
    assert dict(checkout.with_args)["fetch-depth"] == "0"
    for step in plan.preparation:
        assert not step.argv[0].startswith("actions/")


def test_contract_environment_is_extracted():
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/runner/temp")
    env = dict(plan.contract_env)
    assert env["ARTIFACT_CHAIN_PROOF_V2_ENFORCE"] == "1"
    assert env["ONPREM_PROOF_STRICT_ENFORCE"] == "0"
    assert env["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == "/runner/temp/ms-playwright"
    assert "DATABASE_URL" in env and "EXPORT_SIGN_SECRET" in env
    assert plan.contract_argv == ("bash", cp.CONTRACT_SCRIPT)


def test_preparation_env_layers_job_then_step(repo):
    plan = cp.extract_canonical_plan(repo, runner_temp="/runner/temp")
    by_argv = {" ".join(s.argv): dict(s.env) for s in plan.preparation}
    assert by_argv["bash tools/preflight_v1.sh"]["GIT_LFS_SKIP_SMUDGE"] == "1"
    playwright = by_argv[
        "npx --prefix webcore_appcore_starter_4_17/scripts/web_e2e playwright "
        "install --with-deps chromium"
    ]
    assert playwright["PLAYWRIGHT_BROWSERS_PATH"] == "/runner/temp/ms-playwright"
    assert "PLAYWRIGHT_BROWSERS_PATH" not in by_argv["bash tools/preflight_v1.sh"]


def test_expressions_are_resolved_not_left_as_text():
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/x/y")
    for _key, value in plan.contract_env:
        assert "${{" not in value
    assert cp.resolve_expressions("${{ runner.temp }}/z", runner_temp="/x/y") == "/x/y/z"


def test_execution_side_resolves_exact_head_markers():
    actions, harness = cp.extract_execution_workflow(REPO_ROOT, runner_temp="/rt")
    checkout = next(a for a in actions if a.family == "actions/checkout")
    assert dict(checkout.with_args)["ref"] == cp.EXACT_HEAD_MARKER
    assert len(harness) == 1
    assert harness[0].argv == cp.APPROVED_HARNESS_ARGV
    env = dict(harness[0].env)
    assert env["AC25_EVENT_HEAD_SHA"] == cp.EXACT_HEAD_MARKER
    assert env["AC25_BASE_REF"] == cp.PR_BASE_MARKER


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


# ══ 지문 ═══════════════════════════════════════════════════════════════
def test_plan_digest_is_stable_and_sensitive(repo):
    before = cp.extract_canonical_plan(repo, runner_temp="/tmp").sha256()
    assert before == cp.extract_canonical_plan(repo, runner_temp="/tmp").sha256()
    path = repo / cp.CANONICAL_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "--require-node-npm --require-rg --require-jq", "--require-node-npm"
    )
    path.write_text(body, encoding="utf-8")
    assert cp.extract_canonical_plan(repo, runner_temp="/tmp").sha256() != before


def test_command_plan_digest_covers_the_harness(repo):
    before = rcr.command_plan_sha256(repo, runner_temp="/tmp")
    path = repo / cp.EXECUTION_WORKFLOW_PATH
    body = path.read_text(encoding="utf-8").replace(
        "python3 -m ac25.repo_contract_runner",
        "python3 -m ac25.other_runner",
    )
    path.write_text(body, encoding="utf-8")
    assert rcr.command_plan_sha256(repo, runner_temp="/tmp") != before


# ══ observation allowlist (§3-3 ③) ════════════════════════════════════
def test_observation_allowlist_is_exact_match_only():
    assert cp.observation_only(("git", "rev-parse", "HEAD"))
    assert cp.observation_only(("helm", "version", "--short"))
    assert not cp.observation_only(("git", "rev-parse", "HEAD", "--extra"))
    assert not cp.observation_only(("npm", "ci"))
    assert not cp.observation_only(("helm", "install", "x"))


def test_tool_version_plan_is_observation_only():
    for _name, argv in rcr.TOOL_VERSION_PLAN:
        assert cp.observation_only(argv), argv
