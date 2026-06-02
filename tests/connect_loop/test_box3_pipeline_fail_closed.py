"""PR #770 box3 fail-closed 회귀 방지 (Codex P2 #1 + P1 #3, + P1 #2 잠금).

대상 결함(2026-06-01 실측 재현 후 정정):
  #1 (P2) grounding/pipeline.py: contract_only 변수만 보고 draft_text 를 suppress 하여
     _determine_status 의 final demotion(asset incomplete)을 무시하던 누출.
  #3 (P1) pipeline.py L73-74: fail_class 가 format/style adapter fail-closed 신호를
     무시하여 format_match_score:0.0 / forbidden_style_zero:false 인 draft 가 status="real"
     로 통과하던 결함.
  #2 (P1) draft_service.py: real_model_runner 호출 전 BOX3_DIGEST_ONLY_INPUT + sha256 강제
     (commit c420d563 v1.2.1 P0 에서 이미 정정됨 — 본 테스트는 그 계약을 잠근다).

함수명/시그니처/필드는 모두 실측(View) 기준. 추정 0.
"""
from __future__ import annotations

import re

import pytest

# ── #1: grounding/pipeline (force/runner 입력 + Box3PipelineInput 계약) ──────────
from butler_pc_core.cards.box3.grounding.pipeline import (
    Box3PipelineInput,
    Box3ReferenceDoc,
    digest_text,
    run_box3_pipeline as run_grounding_box3_pipeline,
)

# ── #3: pipeline (Box3Request 계약 + 주입 runner) + 단일 real 게이트 ──────────────
from butler_pc_core.cards.box3.pipeline import run_box3_pipeline, box3_real_claim_allowed
from butler_pc_core.cards.box3.asset_manifest import manifest_allows_real
from butler_pc_core.cards.box3.types import Box3Request

# ── #2: draft_service digest-only 계약 ─────────────────────────────────────────
from butler_pc_core.cards.box3.draft_service import (
    Box3ContractError,
    draft_from_current_contract,
)


# 모든 필수 섹션 + 정중체 + forbidden 0 → format/style/grounding 통과(유일한 real 경로 입력).
_CLEAN_REAL_DRAFT = "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"


def _passing_real_manifest() -> dict:
    assets = []
    for index, name in enumerate(
        ["helper3_format", "helper4_grounding", "helper7_table_figure", "helper8_company_style"],
        start=1,
    ):
        assets.append(
            {
                "asset_name": name,
                "role": name,
                "display_sha_prefix": f"{index:08x}...",
                "asset_path": f"/runtime/{name}",
                "sha256_full": f"{index}" * 64,
                "sha_scope": "file",
                "measured_at": "2026-06-01T00:00:00+00:00",
                "measured_by": "test",
                "source_metadata_files": ["adapter_config.json"],
                "interface_inventory_status": "pass",
                "real_claim_allowed": True,
                "fail_class": None,
            }
        )
    return {
        "schema_version": "box3.asset_manifest.v1",
        "status": "ASSET_INVENTORY_PASS",
        "real_claim_allowed": True,
        "assets": assets,
    }


def _request() -> Box3Request:
    return Box3Request(reference_docs=["digest-safe reference"], draft_request="digest-safe request")


# ───────────────────────────────────────────────────────────────────────────────
# 결함 #1 (P2) — grounding/pipeline contract_only demote 시 draft_text suppress
# ───────────────────────────────────────────────────────────────────────────────
def test_grounding_real_runner_is_blocked_no_raw_leak():
    """grounding 파이프라인은 real runner 를 받지 않는다 — 주입 시 raw(merged request_text+runtime_text)
    가 runner 에 도달하기 전에 fail-closed. real 생성은 pipeline.py 단일 게이트만 담당(#8 차단)."""
    calls = []

    def runner(prompt, config):
        calls.append(prompt)
        return "제목\n목적\n근거\n초안\n확인 필요\n본문 합니다"

    payload = Box3PipelineInput(
        request_text="기밀 사업 산문 request",
        reference_docs=[Box3ReferenceDoc(source_digest=digest_text("source"), runtime_text="기밀 근거 문서 원문")],
    )
    with pytest.raises(Box3ContractError) as exc:
        run_grounding_box3_pipeline(payload, runner=runner)
    assert "GROUNDING_REAL_RUNNER_NOT_SUPPORTED" in str(exc.value)
    assert calls == [], "raw text 가 grounding runner 에 도달하면 안 된다"


def test_grounding_force_draft_text_path_still_suppresses():
    """force_draft_text(contract_only=True) 경로 무회귀 — 여전히 draft_text None."""
    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[Box3ReferenceDoc(source_digest=digest_text("source"), runtime_text="근거 문서")],
    )
    result = run_grounding_box3_pipeline(payload, force_draft_text="제목\n목적\n근거\n초안\n확인 필요").to_dict()
    assert result["draft_text"] is None


def test_grounding_receipt_and_citations_exclude_non_digest_source():
    """receipt_hook.source_digests 와 citations 모두 sha256:<64hex> 검증된 값만 포함 —
    caller 의 raw(email) 및 malformed(sha256:alice@example.com) echo 0(신규 #1)."""
    good = digest_text("source")
    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[
            Box3ReferenceDoc(source_digest=good, runtime_text="근거 문서"),
            Box3ReferenceDoc(source_digest="alice@example.com", runtime_text="raw"),  # prefix 없음
            Box3ReferenceDoc(source_digest="sha256:alice@example.com", runtime_text="raw"),  # malformed
        ],
    )
    result = run_grounding_box3_pipeline(
        payload, force_draft_text="제목\n목적\n근거\n초안\n확인 필요"
    ).to_dict()
    source_digests = result["receipt_hook"]["source_digests"]
    citation_sources = [c["source_digest"] for c in result["citations"]]
    assert result["evidence"]["evidence_unit_count"] == 1
    for bucket in (source_digests, citation_sources):
        assert good in bucket
        assert "alice@example.com" not in bucket
        assert "sha256:alice@example.com" not in bucket
        assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", str(x)) for x in bucket)


def test_grounding_malformed_source_digest_produces_no_evidence_unit():
    """helper7 extraction 단계부터 sha256:<64hex> full digest 만 evidence 로 인정한다."""
    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[
            Box3ReferenceDoc(source_digest="sha256:alice@example.com", runtime_text="raw"),
        ],
    )
    result = run_grounding_box3_pipeline(
        payload, force_draft_text="제목\n목적\n근거\n초안\n확인 필요"
    ).to_dict()

    assert result["evidence"]["evidence_unit_count"] == 0
    assert result["evidence"]["status"] == "NEEDS_REVIEW_NO_EVIDENCE"
    assert result["grounding"]["status"] == "needs_review"
    assert result["grounding"]["fail_class"] == "NO_EVIDENCE_UNITS"
    assert result["citations"] == []
    assert result["receipt_hook"]["source_digests"] == []


def test_pipeline_citations_are_digest_linked_not_supported():
    """CONTRACT_ONLY 스코프: pipeline citation 은 검증 없는 'supported' 가 아닌 'digest_linked'(과대주장 0).
    draft claim 추출·evidence 대조(실제 grounding 추출)는 real 단계 후속(신규 #2 최소 정직)."""
    result = run_box3_pipeline(_request())
    assert result["citations"]
    assert all(c["support_level"] == "digest_linked" for c in result["citations"])
    assert not any(c["support_level"] == "supported" for c in result["citations"])


# ───────────────────────────────────────────────────────────────────────────────
# pipeline runner 게이팅 (claim-level grounding 미구현 시 runner 미호출 = fail-closed)
# format/style/empty 게이트 로직 자체는 단위 매트릭스(test_real_gate_*)가 전수 검증한다.
# ───────────────────────────────────────────────────────────────────────────────
def test_pipeline_runner_not_invoked_until_claim_grounding():
    """passing manifest + runner 라도 claim-level grounding 미구현이면 runner 를 호출하지 않고
    contract_only — 모델 미실행으로 external_send_zero 가 runner 동작에 좌우되지 않음(신규)."""
    calls = []

    def runner(prompt, max_new_tokens):
        calls.append(prompt)
        return _CLEAN_REAL_DRAFT

    result = run_box3_pipeline(_request(), asset_manifest=_passing_real_manifest(), real_model_runner=runner)
    assert calls == [], "claim-level grounding 미구현 시 real_model_runner 가 호출되면 안 된다"
    assert result["status"] == "contract_only"
    assert result["real_claim_allowed"] is False
    assert result["draft_text"] is None
    assert result["external_send_zero"] is True


def test_pipeline_clean_draft_stays_contract_only_until_claim_grounding():
    """format/style/digest-link grounding 모두 통과 + passing manifest + runner 라도, claim-level
    grounding 미구현(CLAIM_LEVEL_GROUNDING_IMPLEMENTED=False) 이므로 real 차단 → contract_only(신규 B)."""
    def runner(prompt, max_new_tokens):
        assert "BOX3_DIGEST_ONLY_INPUT" in prompt
        return _CLEAN_REAL_DRAFT

    result = run_box3_pipeline(_request(), asset_manifest=_passing_real_manifest(), real_model_runner=runner)
    assert result["status"] == "contract_only"
    assert result["real_claim_allowed"] is False
    assert result["draft_text"] is None


# ───────────────────────────────────────────────────────────────────────────────
# 결함 #2 (P1) — digest-only input enforce (이미 정정됨, 계약 잠금)
# ───────────────────────────────────────────────────────────────────────────────
def test_draft_service_raw_prose_blocked_before_real_runner():
    """raw business prose(PII/secrets/paths 0)도 BOX3_DIGEST_ONLY_INPUT 아니면 runner 도달 전 BLOCK."""
    calls = []

    def runner(prompt, max_new_tokens):
        calls.append(prompt)
        return "draft"

    raw_input = "당사는 이번 분기 매출이 전년 대비 12% 증가하였습니다. 이에 대한 보고서 초안을 작성합니다."
    prompt_template = "Box3 draft. Input: {input}"

    with pytest.raises(Box3ContractError) as exc:
        draft_from_current_contract(
            input_text=raw_input,
            prompt_template=prompt_template,
            max_new_tokens=512,
            real_model_runner=runner,
        )
    assert str(exc.value) == "DIGEST_ONLY_INPUT_REQUIRED_FOR_REAL_RUNNER"
    assert calls == [], "raw input 이 real_model_runner 에 도달하면 안 된다"
    # error 에 raw input 원문이 새지 않아야 한다(no-raw-output 정합).
    assert "매출" not in str(exc.value)


def test_real_runner_requires_canonical_prompt_template():
    """digest-only input 이라도 custom prose template 은 real runner 도달 전 BLOCK(신규 #1)."""
    from butler_pc_core.cards.box3.draft_service import (
        compose_box3_current_contract_input,
        draft_from_current_contract,
    )

    payload = compose_box3_current_contract_input(
        reference_doc_digests=["sha256:" + "a" * 64],
        request_digest="sha256:" + "b" * 64,
        max_new_tokens=128,
    )
    calls = []

    def runner(prompt, max_new_tokens):
        calls.append(prompt)
        return "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"

    with pytest.raises(Box3ContractError) as exc:
        draft_from_current_contract(
            input_text=payload["input_text"],  # 유효 digest-only input
            prompt_template="기밀 사업 산문이 담긴 사용자 정의 템플릿. Input: {input}",  # 비정본
            max_new_tokens=128,
            real_model_runner=runner,
        )
    assert "NON_CANONICAL_PROMPT_TEMPLATE_FOR_REAL_RUNNER" in str(exc.value)
    assert calls == [], "비정본 template 이 real_model_runner 에 도달하면 안 된다"


def test_digest_only_input_rejects_duplicate_fields():
    """digest-only 입력의 중복 필드명은 거부 — 앞선 raw 라인이 runner 로 전송되는 우회 차단(신규)."""
    from butler_pc_core.cards.box3.draft_service import validate_digest_only_contract_input

    dup_input = "\n".join(
        [
            "BOX3_DIGEST_ONLY_INPUT",
            "request_digest=평문 기밀 prose 가 담긴 라인",  # 중복 1 (raw)
            "request_digest=sha256:" + "a" * 64,            # 중복 2 (valid)
            "reference_doc_digests=sha256:" + "b" * 64,
            "format_hint_digest=sha256:" + "c" * 64,
        ]
    )
    with pytest.raises(Box3ContractError) as exc:
        validate_digest_only_contract_input(dup_input)
    assert "DIGEST_ONLY_INPUT_DUPLICATE_FIELD" in str(exc.value)


# ───────────────────────────────────────────────────────────────────────────────
# manifest PASS gate (empty real draft 축은 단위 매트릭스 test_real_gate_* 가 검증)
# ───────────────────────────────────────────────────────────────────────────────
def test_manifest_allows_real_requires_pass_status():
    """top-level status 가 ASSET_INVENTORY_PASS 가 아니면(드리프트) real 불가(신규 #B)."""
    drifted = _passing_real_manifest()
    drifted["status"] = "PARTIAL_ASSET_INVENTORY_PENDING"  # real_claim_allowed 는 true 로 드리프트
    assert manifest_allows_real(drifted) is False
    # 정합 PASS manifest 는 여전히 허용(무회귀)
    assert manifest_allows_real(_passing_real_manifest()) is True


def test_pipeline_drifted_manifest_does_not_enable_real_runner():
    """status=PENDING 인데 real_claim_allowed=true 인 드리프트 manifest 는 demotion 이 아니라 BLOCK."""
    drifted = _passing_real_manifest()
    drifted["status"] = "PARTIAL_ASSET_INVENTORY_PENDING"
    calls = []

    def runner(prompt, max_new_tokens):
        calls.append(prompt)
        return _CLEAN_REAL_DRAFT

    result = run_box3_pipeline(_request(), asset_manifest=drifted, real_model_runner=runner)
    assert result["status"] == "blocked"
    assert result["fail_class"] == "BLOCK_ASSET_MANIFEST_STATUS_DRIFT"
    assert result["real_claim_allowed"] is False
    assert result["contract_only"] is True
    assert result["draft_text"] is None
    assert calls == []


def test_pipeline_bad_schema_manifest_blocks_instead_of_demoting():
    """caller supplied schema drift 는 ASSET_INTERFACE_PENDING 으로 숨기지 않고 BLOCK 으로 표면화."""
    bad = _passing_real_manifest()
    bad["schema_version"] = "box3.asset_manifest.v2"
    calls = []

    def runner(prompt, max_new_tokens):
        calls.append(prompt)
        return _CLEAN_REAL_DRAFT

    result = run_box3_pipeline(_request(), asset_manifest=bad, real_model_runner=runner)
    assert result["status"] == "blocked"
    assert result["fail_class"] == "BLOCK_ASSET_MANIFEST_SCHEMA_DRIFT"
    assert result["contract_only"] is True
    assert result["real_claim_allowed"] is False
    assert result["draft_text"] is None
    assert calls == []


# ───────────────────────────────────────────────────────────────────────────────
# 근본 재검토: 단일 real 게이트 8축 매트릭스 (각 축 단독 실패 → real false 전수)
# ───────────────────────────────────────────────────────────────────────────────
_PASS_FORMAT = {"format_match_score": 1.0, "required_sections_present": True, "required_sections": []}
_FAIL_FORMAT = {"format_match_score": 0.0, "required_sections_present": False, "required_sections": []}
_PASS_STYLE = {"style_match_score": 0.9, "forbidden_style_zero": True}
_FAIL_STYLE = {"style_match_score": 0.4, "forbidden_style_zero": False}


def _gate(**over):
    base = dict(
        real_allowed=True,            # asset PASS + manifest 유효 + interface PASS 응축
        draft_was_real=True,          # runner 실행
        real_draft_text=_CLEAN_REAL_DRAFT,  # non-empty
        grounding_fail=None,          # grounding pass(digest-link)
        format_result=_PASS_FORMAT,   # format pass
        style_result=_PASS_STYLE,     # style pass
        claim_level_grounding_verified=True,  # claim-level grounding 축(아래 별도 테스트로 검증)
    )
    base.update(over)
    return box3_real_claim_allowed(**base)


def test_real_gate_baseline_all_axes_pass_is_real():
    assert _gate() is True


def test_real_gate_blocks_real_until_claim_level_grounding():
    """claim-level grounding 미구현(기본값) 시 다른 축이 모두 통과해도 real 불가(신규 B fail-closed)."""
    # 기본 인자(claim_level_grounding_verified 미지정) → 모듈 상수 False → real 차단
    assert box3_real_claim_allowed(
        real_allowed=True,
        draft_was_real=True,
        real_draft_text=_CLEAN_REAL_DRAFT,
        grounding_fail=None,
        format_result=_PASS_FORMAT,
        style_result=_PASS_STYLE,
    ) is False
    # 명시적으로 claim-level 미검증을 주어도 False
    assert _gate(claim_level_grounding_verified=False) is False


def test_real_gate_each_single_axis_failure_blocks_real():
    # 8축 → 게이트 입력 6슬롯(asset/manifest/interface 3축은 real_allowed 로 응축)
    assert _gate(real_allowed=False) is False              # axis 1/7/8 (manifest 계열)
    assert _gate(draft_was_real=False) is False            # axis 2 runner
    assert _gate(grounding_fail="GROUNDING_X") is False    # axis 3 grounding
    assert _gate(real_draft_text="") is False              # axis 6 empty
    assert _gate(real_draft_text="   \n ") is False        # axis 6 whitespace
    assert _gate(format_result=_FAIL_FORMAT) is False      # axis 4 format
    assert _gate(style_result=_FAIL_STYLE) is False        # axis 5 style


def test_manifest_allows_real_rejects_duplicate_assets():
    """#C: 동일 helper3 4중복(이름 집합 미충족·중복)이면 real 불가."""
    dup = _passing_real_manifest()
    only = dup["assets"][0]
    dup["assets"] = [dict(only) for _ in range(4)]  # helper3_format 4중복
    assert manifest_allows_real(dup) is False


def test_manifest_allows_real_rejects_schema_drift():
    """axis 7 보강: schema_version 이 정본(box3.asset_manifest.v1)과 다르거나 누락이면 real 불가."""
    wrong = _passing_real_manifest()
    wrong["schema_version"] = "box3.asset_manifest.v2"
    assert manifest_allows_real(wrong) is False
    missing = _passing_real_manifest()
    del missing["schema_version"]
    assert manifest_allows_real(missing) is False


def test_manifest_allows_real_requires_interface_pass():
    """#8/#D(pipeline manifest): 한 자산이라도 interface_inventory_status != pass 면 real 불가."""
    m = _passing_real_manifest()
    m["assets"][1]["interface_inventory_status"] = "full_sha_and_interface_inventory_required"
    assert manifest_allows_real(m) is False


def test_manifest_allows_real_rejects_unknown_sha_scope():
    """real row 는 full SHA뿐 아니라 SHA scope(file/directory_manifest)도 확정되어야 한다."""
    m = _passing_real_manifest()
    m["assets"][0]["sha_scope"] = "unknown"
    assert manifest_allows_real(m) is False


def test_manifest_allows_real_requires_each_row_real_claim_and_no_fail_class():
    """row 수준 fail-closed: top-level real_claim_allowed=true 여도 개별 row 가 real_claim_allowed=false
    거나 blocking fail_class 면 real 불가(신규)."""
    m = _passing_real_manifest()
    m["assets"][2]["real_claim_allowed"] = False
    assert manifest_allows_real(m) is False
    m2 = _passing_real_manifest()
    m2["assets"][1]["fail_class"] = "BLOCK_FULL_SHA_NOT_MEASURED"
    assert manifest_allows_real(m2) is False


def test_grounding_asset_status_gates_on_interface_inventory():
    """#D(grounding): Box3Asset 가 sha/scope valid 여도 interface_status != pass 면 PASS 아님."""
    from butler_pc_core.cards.box3.grounding.asset_manifest import Box3Asset

    full_sha = "a" * 64
    pending = Box3Asset(asset_name="x", role="r", asset_path_ref="REF", sha256_full=full_sha,
                        sha_scope="file", interface_status="full_sha_and_interface_inventory_required")
    assert pending.status() == "INTERFACE_INVENTORY_PENDING"
    passed = Box3Asset(asset_name="x", role="r", asset_path_ref="REF", sha256_full=full_sha,
                       sha_scope="file", interface_status="pass")
    assert passed.status() == "PASS"
