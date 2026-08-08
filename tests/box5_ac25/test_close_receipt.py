"""A-03 — 단일 SSOT receipt 가 §6 의 strict 규칙 그대로인가.

    · head/attempt 가 다른 증거 혼합 거부
    · 중복 키·알 수 없는 키·누락 키 거부
    · URL 범위 밖 거부 · 만료 뒤 발행 거부
    · canonicalize 결정성 · 요약 재생성 byte 동일
"""
from __future__ import annotations

import copy
import json

import pytest
from ac25 import r6_close_receipt as rcpt

pytestmark = pytest.mark.no_sidecar_token

HEAD = "6bc7d617cebded68949545bdad85a7716a7c24c6"
TREE = "8dfb53271644599252739a672bf922c05b7baa46"
BASE = "12d744b1f62572f35efaf40db71714b3b9f4ca2e"
REPO = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
SHA = "a" * 64


def job_provenance(**extra) -> dict:
    return {
        "source_type": "github_job",
        "source_url": f"https://github.com/{REPO}/actions/runs/1",
        "source_run_id": 1, "source_run_attempt": 1, "source_job_id": 2,
        "source_head_sha": HEAD, "observed_at": "2026-08-07T00:00:00Z",
        **extra,
    }


def local_provenance() -> dict:
    return {
        "source_type": "local_command",
        "command_argv": ["python3", "-m", "pytest", "tests/box5_ac25", "-q"],
        "observed_at": "2026-08-07T00:00:00Z",
    }


def make_receipt() -> dict:
    return {
        "schema_version": "r6_close_receipt.v1",
        "repository": REPO,
        "pr_number": 904,
        "head_sha": HEAD, "head_tree": TREE, "base_sha": BASE,
        "run_id": 1, "run_attempt": 1,
        "workflow_file_sha256": SHA,
        "canonical_workflow_sha256": SHA,
        "command_plan_sha256": SHA,
        "plan_diff": {"missing": 0, "extra": 0, "reordered": 0, "mutated": 0, "unsupported": 0},
        "exact_head_contract": {
            "conclusion": "success", "job_id": 2, "exit_code": 0,
            "error_code": "NONE", "provenance": job_provenance(),
        },
        "clean_evidence": {
            "clean_check_executed": True, "final_worktree_clean": "YES",
            "dirty_path_count": 0, "dirty_path_manifest_sha256": SHA,
            "first_dirty_phase": "NONE", "clean_check_error_code": "NONE",
            "provenance": job_provenance(),
        },
        "guard_evidence": {
            "primary_failed_guard": "NONE",
            "primary_failed_guard_line_sha256": SHA,
            "primary_failed_guard_line_bytes": 30,
            "failing_guard_key_count": 35,
            "failing_guard_keys_sha256": SHA,
            "unparsed_line_count": 0, "unparsed_total_bytes": 0,
            "unparsed_manifest_sha256": SHA,
            "parse_error_code": "NONE",
            "provenance": job_provenance(),
        },
        "python_tests": {
            "total": 1000, "passed": 1000, "failed": 0, "skipped": 0,
            "report_sha256": SHA, "provenance": local_provenance(),
        },
        "node_tests": {
            "total": 60, "passed": 60, "failed": 0, "skipped": 0,
            "report_sha256": SHA, "provenance": local_provenance(),
        },
        "required_checks": {
            "required_total": 61, "success": 61, "failure": 0, "cancelled": 0,
            "timed_out": 0, "action_required": 0, "neutral": 0, "skipped": 0,
            "missing": 0, "pending": 0, "unintended_skipped": 0,
            "skip_allowlist": [],
            "provenance": {
                "source_type": "github_api",
                "source_url": f"https://github.com/{REPO}/pull/904",
                "source_head_sha": HEAD,
                "observed_at": "2026-08-07T00:00:00Z",
            },
        },
        "review_threads": {
            "query_complete": True, "total": 4, "resolved": 4,
            "non_outdated_unresolved": 0,
            "provenance": {
                "source_type": "github_api",
                "source_url": f"https://github.com/{REPO}/pull/904",
                "source_head_sha": HEAD,
                "observed_at": "2026-08-07T00:00:00Z",
            },
        },
        "changed_path_manifest_sha256": SHA,
        "generated_at": "2026-08-07T00:00:00Z",
        "expires_at": "2026-08-12T00:00:00Z",
    }


# ══ 유효한 receipt ═════════════════════════════════════════════════════
def test_valid_receipt_passes_and_digests_deterministically():
    receipt = make_receipt()
    rcpt.validate(receipt)
    assert rcpt.receipt_sha256(receipt) == rcpt.receipt_sha256(make_receipt())
    payload = rcpt.canonical_bytes(receipt)
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    reloaded, digest = rcpt.load_and_validate(payload)
    assert digest == rcpt.receipt_sha256(receipt)
    assert reloaded == receipt


# ══ head 가 다른 증거 혼합 거부 ═══════════════════════════════════════
def test_evidence_from_a_different_head_is_rejected():
    receipt = make_receipt()
    receipt["exact_head_contract"]["provenance"]["source_head_sha"] = "f" * 40
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_HEAD_MIXED


def test_stale_run_evidence_means_head_mixing():
    """오래된 성공 run 은 다른 head 의 관측이다 — 같은 코드로 닫힌다."""
    receipt = make_receipt()
    receipt["clean_evidence"]["provenance"]["source_head_sha"] = "e" * 40
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_HEAD_MIXED


# ══ run attempt 가 다른 증거 혼합 거부 ════════════════════════════════
def test_evidence_from_a_different_attempt_is_rejected():
    receipt = make_receipt()
    receipt["guard_evidence"]["provenance"]["source_run_attempt"] = 2
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_ATTEMPT_MIXED


def test_github_job_evidence_must_declare_its_head():
    receipt = make_receipt()
    del receipt["exact_head_contract"]["provenance"]["source_head_sha"]
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_PROVENANCE_INVALID


# ══ strict 구조 — 누락·미지·중복 ══════════════════════════════════════
def test_missing_field_is_rejected():
    receipt = make_receipt()
    del receipt["required_checks"]
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_MISSING_FIELD


def test_unknown_field_is_rejected():
    receipt = make_receipt()
    receipt["surprise"] = 1
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_UNKNOWN_FIELD


def test_unknown_nested_field_is_rejected():
    receipt = make_receipt()
    receipt["plan_diff"]["bonus"] = 0
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_UNKNOWN_FIELD


def test_duplicate_json_key_is_rejected():
    payload = rcpt.canonical_bytes(make_receipt())
    text = payload.decode("utf-8")
    duplicated = text.replace(
        '"pr_number": 904', '"pr_number": 904, "pr_number": 904', 1
    )
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.loads_strict(duplicated.encode("utf-8"))
    assert caught.value.code == rcpt.RECEIPT_DUPLICATE_KEY


# ══ URL 범위 ═══════════════════════════════════════════════════════════
def test_source_url_from_another_repository_is_rejected():
    receipt = make_receipt()
    receipt["exact_head_contract"]["provenance"]["source_url"] = (
        "https://github.com/attacker/repo/actions/runs/1"
    )
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_URL_OUT_OF_SCOPE


# ══ provenance 필수 ════════════════════════════════════════════════════
@pytest.mark.parametrize("section", ["python_tests", "node_tests", "required_checks"])
def test_every_measurement_needs_provenance(section):
    receipt = make_receipt()
    del receipt[section]["provenance"]
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_MISSING_FIELD


def test_local_command_provenance_needs_argv():
    receipt = make_receipt()
    del receipt["python_tests"]["provenance"]["command_argv"]
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_PROVENANCE_INVALID


# ══ clean 모순 · skip allowlist · 만료 ════════════════════════════════
def test_clean_yes_without_execution_is_contradictory():
    receipt = make_receipt()
    receipt["clean_evidence"]["clean_check_executed"] = False
    with pytest.raises(rcpt.ReceiptError):
        rcpt.validate(receipt)


def test_intended_skip_requires_allowlist():
    receipt = make_receipt()
    receipt["required_checks"]["skipped"] = 1
    with pytest.raises(rcpt.ReceiptError):
        rcpt.validate(receipt)
    receipt["required_checks"]["skip_allowlist"] = ["known-optional-check"]
    rcpt.validate(receipt)


def test_issuing_after_expiry_is_rejected():
    receipt = make_receipt()
    receipt["generated_at"] = "2026-08-13T00:00:00Z"
    with pytest.raises(rcpt.ReceiptError) as caught:
        rcpt.validate(receipt)
    assert caught.value.code == rcpt.RECEIPT_EXPIRED_AT_ISSUE


# ══ §9 CLOSE 기계 판정 ════════════════════════════════════════════════
def test_complete_only_when_every_close_passes():
    verdict = rcpt.close_judgement(make_receipt(), production_python3_s_pass=True)
    assert verdict["complete"] is True
    assert verdict["block_reason"] == "NONE"


def test_cancelled_exact_head_job_blocks_complete():
    receipt = make_receipt()
    receipt["exact_head_contract"]["conclusion"] = "cancelled"
    verdict = rcpt.close_judgement(receipt, production_python3_s_pass=True)
    assert verdict["close1"] is False and verdict["complete"] is False
    assert verdict["block_reason"] == "EXACT_HEAD_JOB_CANCELLED"


def test_unintended_skip_blocks_close4():
    receipt = make_receipt()
    receipt["required_checks"]["skipped"] = 1
    receipt["required_checks"]["unintended_skipped"] = 1
    verdict = rcpt.close_judgement(receipt, production_python3_s_pass=True)
    assert verdict["close4"] is False and verdict["complete"] is False


def test_not_evaluated_clean_blocks_close2():
    receipt = make_receipt()
    receipt["clean_evidence"]["final_worktree_clean"] = "NOT_EVALUATED"
    receipt["clean_evidence"]["first_dirty_phase"] = "NOT_EVALUATED"
    verdict = rcpt.close_judgement(receipt, production_python3_s_pass=True)
    assert verdict["close2"] is False and verdict["complete"] is False


def test_python3_s_failure_blocks_complete():
    verdict = rcpt.close_judgement(make_receipt(), production_python3_s_pass=False)
    assert verdict["close3"] is False and verdict["complete"] is False
    assert verdict["block_reason"] == "PRODUCTION_PYTHON3_S_FAILED"


# ══ §6-5 재생성 byte 동일 ═════════════════════════════════════════════
def test_summary_regenerates_byte_identical():
    receipt = make_receipt()
    first = rcpt.render_summary(receipt)
    second = rcpt.render_summary(copy.deepcopy(receipt))
    assert first == second
    assert str(receipt["pr_number"]) in first


def test_summary_has_no_manual_number_entry_api():
    """수치를 손으로 다시 넣는 입력이 없다 — 입력은 receipt 하나다(§6-4)."""
    import inspect

    signature = inspect.signature(rcpt.render_summary)
    assert list(signature.parameters) == ["receipt"]


# ══ schema 파일과 validator 의 결속 ═══════════════════════════════════
def test_schema_file_matches_the_validator_constants():
    schema = rcpt.schema_document()
    assert schema["properties"].keys() == set(rcpt._TOP_REQUIRED)
    assert set(schema["required"]) == set(rcpt._TOP_REQUIRED)
    assert schema["additionalProperties"] is False
    for section, keys in (
        ("plan_diff", rcpt._PLAN_DIFF_KEYS),
        ("exact_head_contract", rcpt._CONTRACT_KEYS),
        ("clean_evidence", rcpt._CLEAN_KEYS),
        ("guard_evidence", rcpt._GUARD_KEYS),
        ("required_checks", rcpt._CHECK_KEYS),
        ("review_threads", rcpt._REVIEW_KEYS),
    ):
        node = schema["properties"][section]
        assert set(node["required"]) == set(keys), section
        assert node["additionalProperties"] is False, section


def test_schema_file_is_strict_json():
    raw = rcpt.SCHEMA_PATH.read_bytes()
    json.loads(raw)
    assert rcpt.SCHEMA_PATH.name == "r6_close_receipt.v1.schema.json"
