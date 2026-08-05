"""§15 M-6 — final check-run 계약 시험.

앞 단계가 실패하면 발행 단계가 건너뛰어져 후보에 ★아무 표시도 남지 않는다.
아무 표시가 없는 것은 "아직 안 함" 과 구별되지 않는다.

★성공·실패 모두 후보 head 에 도장을 남긴다.
★실패라고 발행을 생략하지 않는다. API 실패는 CHECK_RUN_PUBLICATION_FAILED 다.

워크플로 원문을 계약으로 검사한다. github-script 본문은 JavaScript 라 여기서
실행하지 않고, 판정 분기와 발행 순서가 존재하는지를 정적으로 확인한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
TRUSTED = REPO_ROOT / ".github" / "workflows" / "box5-ac25-trusted-verification.yml"

CHECK_NAME = "box5-ac25/trusted-exact-head"
CHECK_HEAD_SHA = "61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd04"


def _workflow() -> dict:
    return yaml.safe_load(TRUSTED.read_text(encoding="utf-8"))


def _publish() -> dict:
    return _workflow()["jobs"]["publish-check"]


def _script() -> str:
    return _publish()["steps"][0]["with"]["script"]


# ══ publish 는 언제나 돈다 ═════════════════════════════════════════════
def test_publish_runs_always():
    assert _publish()["if"] == "always()"


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


def test_publish_does_not_checkout_or_run_candidate_code():
    steps = _publish()["steps"]
    assert len(steps) == 1
    assert "checkout" not in str(steps[0].get("uses", ""))
    assert "run" not in steps[0]


# ══ 성공 조건 ══════════════════════════════════════════════════════════
def test_success_requires_every_needed_job_to_succeed():
    script = _script()
    for name in ("TRUSTED_RESULT", "CANDIDATE_RESULT", "INTEGRATION_RESULT"):
        assert name in script
    assert '_JOB_NOT_SUCCESS' in script
    assert 'value !== "success"' in script


def test_success_requires_trusted_verdict():
    assert "TRUSTED_VERDICT_NOT_PASS" in _script()
    assert "RECEIPT_VERDICT_NOT_PASS" in _script()


def test_success_requires_candidate_coordinates_to_agree():
    script = _script()
    assert "CANDIDATE_COORDINATE_MISMATCH" in script
    assert "CANDIDATE_EXECUTION_MISMATCH" in script
    assert "CANDIDATE_TREE_MISMATCH" in script


def test_success_requires_integration_parents_and_tree():
    script = _script()
    assert "MERGE_PARENT_MISMATCH" in script
    assert "MERGE_TREE_INVALID" in script
    assert "MERGE_COMMIT_INVALID" in script
    assert "MERGE_EQUALS_SCOPE_END" in script
    assert "parents[0] !== BASE" in script
    assert "parents[1] !== HEAD_SHA" in script


def test_success_requires_approval_and_identity_digests():
    script = _script()
    for key in (
        "approval_document_sha256", "identity_manifest_sha256",
        "identity_artifact_zip_sha256", "dependency_manifest_sha256",
    ):
        assert key in script, key
    assert "RECEIPT_DIGEST_INVALID" in script


def test_success_requires_no_coverage_gap():
    assert "RECEIPT_COVERAGE_GAP" in _script()
    assert "coverage_uncovered_count !== 0" in _script()


# ══ 실패도 반드시 발행한다 ═════════════════════════════════════════════
def test_failure_still_creates_a_check_run():
    """★conclusion 을 계산한 뒤 발행한다. 실패 분기에서 return 하지 않는다."""
    script = _script()
    conclusion = script.index('const conclusion =')
    create = script.index("checks.create")
    assert conclusion < create, "발행 전에 conclusion 이 정해져야 한다"
    # 발행 전에 빠져나가는 조기 return 이 없다
    before = script[:create]
    assert "return;" not in before.split("const conclusion =")[1]


def test_failure_sets_conclusion_failure():
    script = _script()
    assert 'errorCode === "OK" ? "success" : "failure"' in script


def test_error_code_is_recorded_and_never_overwritten():
    script = _script()
    assert 'if (errorCode === "OK") errorCode = code;' in script


def test_api_failure_uses_the_named_code():
    script = _script()
    assert "CHECK_RUN_PUBLICATION_FAILED" in script
    assert script.index("checks.create") < script.index("CHECK_RUN_PUBLICATION_FAILED")


def test_workflow_fails_when_conclusion_is_not_success():
    script = _script()
    assert 'if (conclusion !== "success")' in script
    assert "core.setFailed" in script


# ══ 이름·head_sha 고정 ═════════════════════════════════════════════════
def test_check_name_and_head_sha_are_pinned():
    script = _script()
    assert f'name: "{CHECK_NAME}"' in script
    assert _publish()["steps"][0]["env"]["EXPECTED_HEAD"] == CHECK_HEAD_SHA
    assert "head_sha: HEAD_SHA" in script


def test_head_sha_comes_from_env_not_from_a_job_output():
    """후보가 좌우할 수 있는 값으로 도장을 찍지 않는다."""
    script = _script()
    assert "const HEAD_SHA = process.env.EXPECTED_HEAD;" in script


# ══ 요약은 meta-only ═══════════════════════════════════════════════════
def test_summary_is_meta_only():
    script = _script()
    summary = script.split("const summary = [", 1)[1].split("].join", 1)[0]
    assert "error_code=" in summary
    assert "verdict=" in summary
    # 경로 목록·원문·토큰이 들어가지 않는다
    for forbidden in ("changed_paths", "offending_paths", "protected_changed_paths",
                      "document_bytes", "token", "TOKEN", "failures"):
        assert forbidden not in summary, forbidden
    # 개수는 허용된다
    assert "changed_path_count" in summary
    assert "offending_path_count" in summary


def test_summary_records_that_github_merge_ref_was_not_used():
    summary = _script().split("const summary = [", 1)[1].split("].join", 1)[0]
    assert "github_merge_ref_used_for_verdict=NO" in summary
    assert "github_merge_ref_observed=" in summary


def test_summary_records_synthetic_merge_coordinates():
    summary = _script().split("const summary = [", 1)[1].split("].join", 1)[0]
    for key in ("synthetic_merge_commit", "synthetic_merge_tree", "parents",
                "integration_base_commit"):
        assert key in summary, key


# ══ 이벤트·권한 계약 ═══════════════════════════════════════════════════
def test_trusted_workflow_accepts_only_workflow_dispatch():
    triggers = _workflow()[True] if True in _workflow() else _workflow()["on"]
    assert set(triggers) == {"workflow_dispatch"}


def test_top_level_permissions_are_empty():
    assert _workflow()["permissions"] == {}


def test_only_trusted_and_publish_use_the_environment():
    jobs = _workflow()["jobs"]
    with_environment = {
        name for name, job in jobs.items() if job.get("environment")
    }
    assert with_environment == {"trusted-verification", "publish-check"}


def test_candidate_and_integration_lanes_have_no_secrets_or_write():
    jobs = _workflow()["jobs"]
    for name in ("candidate-lane", "integration-lane"):
        job = jobs[name]
        assert job.get("environment") is None
        assert job["permissions"] == {"contents": "read"}
        body = yaml.dump(job)
        assert "secrets." not in body, name


def test_all_checkouts_disable_credential_persistence():
    for job in _workflow()["jobs"].values():
        for step in job.get("steps", []):
            if "checkout" in str(step.get("uses", "")):
                assert step["with"]["persist-credentials"] is False


def test_every_action_is_pinned_to_a_full_sha():
    body = TRUSTED.read_text(encoding="utf-8")
    for reference in re.findall(r"uses:\s*(\S+)", body):
        assert re.fullmatch(r"[0-9a-f]{40}", reference.partition("@")[2]), reference
