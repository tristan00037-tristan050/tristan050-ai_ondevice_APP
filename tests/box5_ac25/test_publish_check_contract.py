"""§20 C3 · M-6 — 발행 배선 계약 시험(Python 쪽).

★발행 로직 자체의 판정은 tests/box5_ac25/publish_check.test.mjs 가 ★실제 실행★ 으로
  증명한다. 정적 문자열 검색을 C3 PASS 로 세지 않는다.
  이 파일이 보는 것은 ★워크플로가 그 모듈을 올바르게 부르도록 배선됐는가★ 다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
TRUSTED = WORKFLOW_DIR / "box5-ac25-trusted-verification.yml"
SMOKE = WORKFLOW_DIR / "box5-ac25-stage-a-smoke.yml"
MODULE = REPO_ROOT / "scripts" / "ci" / "ac25" / "publish_check.mjs"
JS_TEST = REPO_ROOT / "tests" / "box5_ac25" / "publish_check.test.mjs"

CHECK_NAME = "box5-ac25/trusted-exact-head"
LOCKED_HEAD = "61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd04"
LOCKED_BASE = "afdb237e4e6e83d96a182b6c5366a2ad95949bee"


def _workflow(path: Path = TRUSTED) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _publish() -> dict:
    return _workflow()["jobs"]["publish-check"]


def _script() -> str:
    return _publish()["steps"][1]["with"]["script"]


# ══ 모듈이 존재하고 실행 가능한 시험이 붙어 있다 ═══════════════════════
def test_publisher_module_exists():
    assert MODULE.is_file()
    body = MODULE.read_text(encoding="utf-8")
    # ★production 호출은 github.rest.checks.create 다
    assert "github.rest.checks.create" in body
    assert "octokit.checks.create" not in body
    assert "github.checks.create(" not in body


def test_executable_test_exists_and_uses_the_same_api_shape():
    assert JS_TEST.is_file()
    body = JS_TEST.read_text(encoding="utf-8")
    assert "import test from 'node:test'" in body
    # ★mock 이 production 과 같은 모양이어야 한다
    assert "rest:" in body and "checks:" in body and "create:" in body
    # 외부 npm dependency 를 더하지 않는다
    assert "require('" not in body
    for forbidden in ("from 'chai'", "from 'jest'", "from 'sinon'"):
        assert forbidden not in body


def test_smoke_actually_runs_the_executable_test():
    """★원격에서 실제로 돈다. 정적 검사로 대체하지 않는다."""
    workflow = _workflow(SMOKE)
    job = workflow["jobs"]["ac25-publish-check-executable-test"]
    script = "\n".join(step.get("run", "") for step in job["steps"])
    assert "node --test tests/box5_ac25/publish_check.test.mjs" in script
    assert job["permissions"] == {"contents": "read"}
    assert job.get("environment") is None


def test_locked_constants_match_between_module_and_lock():
    body = MODULE.read_text(encoding="utf-8")
    assert f"'{LOCKED_HEAD}'" in body
    assert f"'{LOCKED_BASE}'" in body
    assert f"'{CHECK_NAME}'" in body


# ══ publish job 배선 ═══════════════════════════════════════════════════
def test_publish_runs_always():
    assert _publish()["if"] in ("always()", "${{ always() }}")


def test_publish_needs_all_three_jobs():
    assert set(_publish()["needs"]) == {
        "trusted-verification", "candidate-lane", "integration-lane"
    }


def test_publish_uses_the_protected_environment():
    assert _publish()["environment"] == "ac25-trusted-main"


def test_publish_is_the_only_job_with_checks_write():
    jobs = _workflow()["jobs"]
    writers = [
        name for name, job in jobs.items()
        if (job.get("permissions") or {}).get("checks") == "write"
    ]
    assert writers == ["publish-check"]


def test_publish_checks_out_the_protected_publisher():
    """★GITHUB_WORKSPACE 에 무엇이 있는지 보장 없이 import 하지 않는다."""
    steps = _publish()["steps"]
    checkout = steps[0]
    assert "actions/checkout@" in checkout["uses"]
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["path"] == "ac25-publisher"
    assert checkout["with"]["persist-credentials"] is False


def test_publish_imports_the_module_by_absolute_file_url():
    script = _script()
    assert "pathToFileURL" in script
    assert "ac25-publisher/" in script
    assert "publish_check.mjs" in script
    assert "await import(moduleUrl)" in script


def test_publish_does_not_run_candidate_code():
    steps = _publish()["steps"]
    assert len(steps) == 2
    assert all("run" not in step for step in steps)
    # 후보 head 를 checkout 하지 않는다
    assert steps[0]["with"]["ref"] == "${{ github.sha }}"


def test_publish_passes_only_named_fields():
    """★needs 전체를 JSON 으로 넘기지 않는다."""
    env = _publish()["steps"][1]["env"]
    assert all(key.startswith("AC25_") for key in env), env
    body = TRUSTED.read_text(encoding="utf-8")
    assert "toJSON" not in body


def test_publish_never_leaks_javascript_stack():
    script = _script()
    assert "error.stack" not in script
    assert "error.message" not in script
    assert "console.log" not in script
    assert "CHECK_RUN_PUBLICATION_FAILED" in script
    assert "ERROR_CODE=${code}" in script


def test_publish_error_code_shape_is_constrained():
    assert "/^[A-Z0-9_]{1,64}$/" in _script()


# ══ C6 — job output 최소화 ═════════════════════════════════════════════
def test_trusted_job_outputs_match_the_allowlist():
    from ac25.orchestrator import JOB_OUTPUT_ALLOWLIST

    outputs = _workflow()["jobs"]["trusted-verification"]["outputs"]
    assert set(outputs) == set(JOB_OUTPUT_ALLOWLIST)


def test_integration_job_outputs_match_the_allowlist():
    outputs = _workflow()["jobs"]["integration-lane"]["outputs"]
    assert set(outputs) == {
        "synthetic_merge_commit", "synthetic_merge_tree",
        "parent_base", "parent_candidate", "github_merge_ref_observed_sha256",
    }


def test_receipt_body_is_never_a_job_output():
    body = TRUSTED.read_text(encoding="utf-8")
    assert "ac25-receipt.json" not in body
    assert "AC25_RECEIPT_EOF" not in body
    assert "receipt<<" not in body


def test_github_merge_ref_is_only_carried_as_a_digest():
    outputs = _workflow()["jobs"]["integration-lane"]["outputs"]
    assert "github_merge_ref_observed" not in outputs
    assert "github_merge_ref_observed_sha256" in outputs


# ══ 이벤트·권한 계약 ═══════════════════════════════════════════════════
def test_trusted_workflow_accepts_only_workflow_dispatch():
    workflow = _workflow()
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert set(triggers) == {"workflow_dispatch"}


def test_top_level_permissions_are_empty():
    assert _workflow()["permissions"] == {}
    assert _workflow(SMOKE)["permissions"] == {}


def test_only_trusted_and_publish_use_the_environment():
    jobs = _workflow()["jobs"]
    with_environment = {name for name, job in jobs.items() if job.get("environment")}
    assert with_environment == {"trusted-verification", "publish-check"}


def test_smoke_has_no_environment_or_secret_anywhere():
    body = SMOKE.read_text(encoding="utf-8")
    assert "secrets." not in body
    assert "environment:" not in body
    assert "checks: write" not in body


def test_candidate_and_integration_lanes_have_no_secrets_or_write():
    jobs = _workflow()["jobs"]
    for name in ("candidate-lane", "integration-lane"):
        job = jobs[name]
        assert job.get("environment") is None
        assert job["permissions"] == {"contents": "read"}
        assert "secrets." not in yaml.dump(job), name


def test_approval_token_reaches_only_the_trusted_job():
    """★C5 — 승인 credential 은 trusted-verification 하나에만 노출한다."""
    jobs = _workflow()["jobs"]
    for name, job in jobs.items():
        rendered = yaml.dump(job, allow_unicode=True)
        if name == "trusted-verification":
            assert "AC25_APPROVAL_READ_TOKEN" in rendered
        else:
            assert "AC25_APPROVAL_READ_TOKEN" not in rendered, name


def test_two_credentials_are_wired_separately():
    steps = _workflow()["jobs"]["trusted-verification"]["steps"]
    orchestrate = next(step for step in steps if step.get("id") == "orchestrate")
    env = orchestrate["env"]
    assert env["AC25_APPROVAL_TOKEN"] == "${{ secrets.AC25_APPROVAL_READ_TOKEN }}"
    assert env["AC25_CANDIDATE_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert "GH_TOKEN" not in env, "단일 GH_TOKEN 으로 두 저장소를 읽지 않는다"


def test_all_checkouts_disable_credential_persistence():
    for path in (TRUSTED, SMOKE):
        for job in _workflow(path)["jobs"].values():
            for step in job.get("steps", []):
                if "checkout" in str(step.get("uses", "")):
                    assert step["with"]["persist-credentials"] is False


def test_every_action_is_pinned_to_a_full_sha():
    for path in (TRUSTED, SMOKE):
        for reference in re.findall(r"uses:\s*(\S+)", path.read_text(encoding="utf-8")):
            assert re.fullmatch(r"[0-9a-f]{40}", reference.partition("@")[2]), reference


def test_no_moving_runner_labels():
    for path in (TRUSTED, SMOKE):
        for job in _workflow(path)["jobs"].values():
            assert job["runs-on"] == "ubuntu-24.04", job["runs-on"]
