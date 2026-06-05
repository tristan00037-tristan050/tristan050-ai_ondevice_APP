from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope, sha256_text
from butler_pc_core.cards.box3.actual_operation_pipeline import run_box3_actual_operation
from butler_pc_core.cards.box3.endpoint_wiring import run_box3_endpoint_wiring
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard, verify_helper_component_use_guard
from butler_pc_core.cards.box3.helper_sdk_bridge import HelperSdkBridge
from butler_pc_core.cards.box3.helper_wiring_manifest import HELPER_SHA
from butler_pc_core.cards.box3.local_sealed_runner import build_deterministic_test_runner, probe_helper3_helper5_adapter_stack


def _approval(scope_digest: str) -> dict:
    return {
        "schema_version": "box3.human_approval.v1",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("admin"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


def _write_fake_sdks(tmp_path: Path) -> dict[str, Path]:
    helper7 = tmp_path / "helper7_table_figure_sdk.py"
    helper7.write_text(
        """
def parse_for_evidence(reference_payload):
    out = []
    for idx, text in enumerate(reference_payload, start=1):
        out.append({"evidence_id": f"h7-{idx}", "text": text, "source_text": text, "kind": "text"})
    return out
""",
        encoding="utf-8",
    )
    helper4 = tmp_path / "helper4_grounding_sdk.py"
    helper4.write_text(
        """
# Returning None asks bridge to use the shared ClaimVerdict grounding SSOT after import succeeds.
def ground_claims(draft_text, evidence_bundle, embedder=None):
    return None
""",
        encoding="utf-8",
    )
    helper8 = tmp_path / "helper8_company_style_sdk.py"
    helper8.write_text(
        """
def apply_company_style(draft_text, profile_ref=None):
    return draft_text
""",
        encoding="utf-8",
    )
    helper2 = tmp_path / "helper2_embedding_sdk.py"
    helper2.write_text("class Helper2Embedder: pass\n", encoding="utf-8")
    return {"h7": helper7, "h4": helper4, "h8": helper8, "h2": helper2}


def test_role_manifest_requires_helper5_and_separates_adapter_from_sdk():
    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk")
    verdict = verify_helper_component_use_guard(guard)
    assert verdict.allowed is True
    assert set(verdict.helper_digests) == {"helper3_format", "helper5_tool_call", "helper4_grounding", "helper7_table_figure", "helper8_company_style"}
    assert verdict.helper_stack_supported is True
    assert verdict.sdk_call_supported is True


def test_legacy_guard_without_helper5_is_blocked():
    legacy = {
        "helper_stacking_supported": True,
        "sdk_call_supported": True,
        "embedder_provider": "helper2_sdk",
        "helpers": [
            {"asset_name": "helper3_format", "sha256_full": HELPER_SHA["helper3_format"], "component_use_allowed": True},
            {"asset_name": "helper4_grounding", "sha256_full": HELPER_SHA["helper4_grounding"], "component_use_allowed": True},
            {"asset_name": "helper7_table_figure", "sha256_full": HELPER_SHA["helper7_table_figure"], "component_use_allowed": True},
            {"asset_name": "helper8_company_style", "sha256_full": HELPER_SHA["helper8_company_style"], "component_use_allowed": True},
        ],
    }
    verdict = verify_helper_component_use_guard(legacy)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HELPER_REAL_USE_GUARD_PENDING"


def test_helper4_7_8_stack_attempt_blocks():
    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk")
    guard["sdk_modules"][0]["model_stack_supported"] = True
    verdict = verify_helper_component_use_guard(guard)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HELPER_SDK_STACK_ATTEMPT"


def test_helper8_noncanonical_sha_blocks():
    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk")
    for row in guard["sdk_modules"]:
        if row["asset_name"] == "helper8_company_style":
            row["sha256_full"] = "be18e3cc" + "0" * 56
    verdict = verify_helper_component_use_guard(guard)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HELPER8_NON_CANONICAL_SHA"


def test_embedder_missing_is_partial():
    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider=None)
    verdict = verify_helper_component_use_guard(guard)
    assert verdict.allowed is False
    assert verdict.fail_class == "PARTIAL_EMBEDDER_UNAVAILABLE"


def test_sdk_bridge_fail_closed_when_sdks_missing(monkeypatch):
    for key in [
        "BUTLER_HELPER4_GROUNDING_SDK_PATH",
        "BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH",
        "BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH",
        "BUTLER_HELPER2_EMBEDDING_SDK_PATH",
        "BUTLER_BGE_M3_MODEL_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)
    # PR #779 v1.3: 단일 경로 SSOT 로 bundled cards/box3/sdk subpackage 가 canonical fallback.
    # 본 fail-closed 회귀는 "env 미설정 + bundled subpackage 부재" 시나리오를 검증하므로
    # _import_from_env 가 모든 경로에서 ImportError 를 내도록 monkeypatch 한다 (raw 0).
    from butler_pc_core.cards.box3 import helper_sdk_bridge as _bridge_mod

    def _always_raise(_path_env, _module_name):
        raise ImportError("simulated_sdk_unavailable")

    monkeypatch.setattr(_bridge_mod, "_import_from_env", _always_raise)
    bridge = HelperSdkBridge()
    evidence = bridge.parse_evidence(["납품 일정은 2026년 6월 10일입니다."])
    assert evidence.parse_success is False
    assert evidence.fail_class == "PARTIAL_HELPER_SDK_UNAVAILABLE"


def test_sdk_bridge_with_helper2_and_fake_sdks_passes(tmp_path, monkeypatch):
    paths = _write_fake_sdks(tmp_path)
    monkeypatch.setenv("BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH", str(paths["h7"]))
    monkeypatch.setenv("BUTLER_HELPER4_GROUNDING_SDK_PATH", str(paths["h4"]))
    monkeypatch.setenv("BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH", str(paths["h8"]))
    monkeypatch.setenv("BUTLER_HELPER2_EMBEDDING_SDK_PATH", str(paths["h2"]))

    bridge = HelperSdkBridge()
    evidence = bridge.parse_evidence(["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."])
    assert evidence.parse_success is True
    grounded = bridge.ground_claims("핵심 내용: 납품 일정은 2026년 6월 10일입니다.", evidence)
    assert grounded.embedder_provider == "helper2_sdk"
    assert grounded.summary.unsupported_claim_count == 0
    styled = bridge.apply_company_style("제목: 초안")
    assert styled.style_applied is True
    persist = grounded.persistable_dict()
    assert "참고 문서" not in json.dumps(persist, ensure_ascii=False)


def test_model_adapter_stack_probe_never_stacks_sdk_modules(monkeypatch):
    # PR #783 (v5 canonical apply): helper3/5 는 v5 base 에 embedded — runtime
    # multi-LoRA stack env=1 시 BLOCK_HELPER35_DOUBLE_STACK_RISK. helper_sdk_stack_attempt_zero
    # 는 SDK helper(4/7/8) 가 model stack 에 끼지 않았음을 유지한다.
    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk")
    monkeypatch.setenv("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK", "1")
    verdict = probe_helper3_helper5_adapter_stack(guard)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HELPER35_DOUBLE_STACK_RISK"
    assert verdict.model_adapters == ["helper3_format", "helper5_tool_call"]
    assert verdict.helper_sdk_stack_attempt_zero is True


def test_pipeline_smoke_with_fake_sdks_and_test_runner(tmp_path, monkeypatch):
    paths = _write_fake_sdks(tmp_path)
    monkeypatch.setenv("BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH", str(paths["h7"]))
    monkeypatch.setenv("BUTLER_HELPER4_GROUNDING_SDK_PATH", str(paths["h4"]))
    monkeypatch.setenv("BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH", str(paths["h8"]))
    monkeypatch.setenv("BUTLER_HELPER2_EMBEDDING_SDK_PATH", str(paths["h2"]))

    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk")
    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 초안을 작성하세요.",
    )
    result = run_box3_actual_operation(
        env,
        helper_component_guard=guard,
        human_approval_config=_approval(env.request_digest),
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )
    assert result.status == "REAL_CANDIDATE"
    assert result.real_claim_allowed is False
    assert result.fail_class == "TEST_ONLY_RUNNER_NOT_REAL_APPROVAL"
    assert result.helper_sdk_receipts
    persist = result.to_persistable_dict()
    assert "draft_text" not in persist


def test_endpoint_smoke_approval_false_contract_only():
    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 초안을 작성하세요.",
    )
    response = run_box3_endpoint_wiring(
        reference_docs=env.reference_text_runtime_only,
        drafting_request=env.drafting_request_runtime_only,
        approval_config={"allow": False, "kill_switch_enabled": True, "approval_scope_digest": env.request_digest},
    )
    assert response["status"] == "contract_only"
    assert response["real_claim_allowed"] is False
    assert response["actual_wiring"]["runner_injected"] is False


def test_raw_leak_zero_in_persistable_outputs(tmp_path, monkeypatch):
    paths = _write_fake_sdks(tmp_path)
    monkeypatch.setenv("BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH", str(paths["h7"]))
    monkeypatch.setenv("BUTLER_HELPER4_GROUNDING_SDK_PATH", str(paths["h4"]))
    monkeypatch.setenv("BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH", str(paths["h8"]))
    monkeypatch.setenv("BUTLER_HELPER2_EMBEDDING_SDK_PATH", str(paths["h2"]))
    bridge = HelperSdkBridge()
    evidence = bridge.parse_evidence(["비밀이 아닌 참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."])
    grounded = bridge.ground_claims("핵심 내용: 납품 일정은 2026년 6월 10일입니다.", evidence)
    encoded = json.dumps({"evidence": evidence.persistable_dict(), "grounding": grounded.persistable_dict()}, ensure_ascii=False)
    assert "비밀이 아닌 참고 문서" not in encoded
    assert ("/" + "Users/") not in encoded
    assert ("sk-" + "proj-") not in encoded
