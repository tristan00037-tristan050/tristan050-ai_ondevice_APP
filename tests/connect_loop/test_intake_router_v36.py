from __future__ import annotations

import importlib.util
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from butler_pc_core.connect_loop.attachment_features import RuntimeAttachment, extract_attachment_features
from butler_pc_core.connect_loop.intake_router import (
    CANDIDATE_ENDPOINT_HINT,
    CompanyFactSchemaUnavailable,
    IntakeContractError,
    assert_intake_payload_safe,
    decide_intake,
    dispatchable_endpoint,
    validate_company_fact_candidate_payload,
)

ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / "connect_loop" / name).read_text(encoding="utf-8"))


class FakeCompanyFactCandidateRequest:
    def __init__(self, **data):
        if not data.get("category"):
            raise ValueError("category")
        if len(data.get("question_patterns", [])) < 2:
            raise ValueError("question_patterns")
        if len(data.get("answer_runtime_text", "")) < 10:
            raise ValueError("answer")
        if len(data.get("source", "")) < 3:
            raise ValueError("source")
        conf = float(data.get("confidence", 0.5))
        if conf < 0 or conf >= 1.0:
            raise ValueError("confidence")
        self._data = dict(data)

    def model_dump(self):
        return dict(self._data)


def bank_bundle():
    raw = "거래일자,입금,출금,잔액,적요,상대계좌예금주명\n2026-01-01,1000,0,1000,테스트,홍길동\n".encode("utf-8")
    return extract_attachment_features([RuntimeAttachment(raw, filename="bank.csv", content_type="text/csv")])


def bank_xlsx_bundle():
    shared_strings = [
        "거래일자",
        "입금",
        "출금",
        "잔액",
        "적요",
        "상대계좌예금주명",
        "2026-01-01",
        "1000",
        "0",
        "테스트",
        "홍길동",
    ]
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{text}</t></si>" for text in shared_strings)
        + "</sst>"
    )
    sheet_xml = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c>
      <c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>6</v></c><c r="B2" t="s"><v>7</v></c>
      <c r="C2" t="s"><v>8</v></c><c r="D2" t="s"><v>7</v></c>
      <c r="E2" t="s"><v>9</v></c><c r="F2" t="s"><v>10</v></c>
    </row>
  </sheetData>
</worksheet>"""
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
        zf.writestr("xl/sharedStrings.xml", shared_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return extract_attachment_features([
        RuntimeAttachment(
            out.getvalue(),
            filename="bank.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ])


def dataset_bundle():
    raw = "측정일,온도,습도,수량\n2026-01-01,10,20,30\n".encode("utf-8")
    return extract_attachment_features([RuntimeAttachment(raw, filename="data.csv", content_type="text/csv")])


def policy_bundle():
    raw = "제1조 목적. 본 내규는 회사 규정과 시행일 및 결재 절차를 정한다.".encode("utf-8")
    return extract_attachment_features([RuntimeAttachment(raw, filename="policy.txt", content_type="text/plain")])


def format_bundle():
    raw = "회사 표준 양식. 작성란: ______ 제출서식 템플릿.".encode("utf-8")
    return extract_attachment_features([RuntimeAttachment(raw, filename="form.txt", content_type="text/plain")])


def test_attachment_features_schema_validates_multi_file():
    bundle = extract_attachment_features([
        RuntimeAttachment("거래일자,입금,출금,잔액\n".encode("utf-8"), filename="a.csv", content_type="text/csv"),
        RuntimeAttachment("제1조 회사 내규 시행일".encode(), filename="b.txt", content_type="text/plain"),
    ])
    Draft7Validator(_schema("attachment_features.schema.json")).validate(bundle.to_dict())
    assert bundle.attachment_count == 2
    assert bundle.raw_text_logged is False


def test_policy_off_never_opens_callable_endpoint():
    decision = decide_intake(request_id="req-1", attachment_bundle=bank_bundle(), runtime_text="분개", policy_ready_override=False)
    assert decision["target_endpoint"] == "none"
    assert decision["policy_callable"] is False
    assert decision["fallback_required"] is True
    assert decision["fail_class"] == "POLICY_BOOTSTRAP_REQUIRED"
    assert decision["next_action"] == "POLICY_BOOTSTRAP_REQUIRED"
    Draft7Validator(_schema("intake_decision.schema.json")).validate(decision)


def test_policy_on_box5_is_callable_but_router_does_not_call():
    decision = decide_intake(request_id="req-2", attachment_bundle=bank_bundle(), runtime_text="분개", policy_ready_override=True)
    assert decision["primary_destination"] == "box5_accounting_classify"
    assert decision["target_endpoint"] == "POST /accounting/classify"
    assert decision["policy_callable"] is True
    assert decision["fallback_required"] is False
    assert dispatchable_endpoint(decision) == "POST /accounting/classify"
    Draft7Validator(_schema("intake_decision.schema.json")).validate(decision)


def test_xlsx_bank_headers_route_to_box5_without_cell_value_surface():
    bundle = bank_xlsx_bundle()
    assert bundle.attachments[0]["file_kind"] == "bank_statement_table"
    assert bundle.attachments[0]["column_role_flags"]["has_date_column"] is True
    assert bundle.attachments[0]["column_role_flags"]["has_amount_column"] is True
    decision = decide_intake(request_id="req-xlsx", attachment_bundle=bundle, runtime_text="분개", policy_ready_override=True)
    assert decision["primary_destination"] == "box5_accounting_classify"
    assert decision["target_endpoint"] == "POST /accounting/classify"
    encoded = json.dumps(decision, ensure_ascii=False)
    assert "2026-01-01" not in encoded
    assert "홍길동" not in encoded
    Draft7Validator(_schema("intake_decision.schema.json")).validate(decision)


def test_company_fact_file_only_is_hint_not_dispatchable():
    decision = decide_intake(request_id="req-3", attachment_bundle=policy_bundle(), runtime_text="회사 규정", policy_ready_override=True)
    assert decision["primary_destination"] == "company_fact_candidate"
    assert decision["target_endpoint"] == "none"
    assert decision["candidate_endpoint_hint"] == CANDIDATE_ENDPOINT_HINT
    assert decision["candidate_payload_ready"] is False
    assert decision["candidate_payload_digest"] is None
    assert decision["next_action"] == "STRUCTURE_COMPANY_FACT_CANDIDATE_REQUIRED"
    assert decision["policy_callable"] is True
    assert dispatchable_endpoint(decision) is None
    Draft7Validator(_schema("intake_decision.schema.json")).validate(decision)


def test_company_fact_structured_payload_promotes_only_after_schema_validation():
    payload = {
        "category": "company_policy",
        "question_patterns": ["휴가 규정은?", "연차 규정 알려줘"],
        "answer_runtime_text": "연차 승인 절차는 관리자 검토 후 확정됩니다.",
        "source": "사내규정",
        "confidence": 0.5,
    }
    decision = decide_intake(
        request_id="req-4",
        attachment_bundle=policy_bundle(),
        runtime_text="회사 규정",
        structured_candidate_payload=payload,
        policy_ready_override=True,
        company_fact_model_cls=FakeCompanyFactCandidateRequest,
    )
    assert decision["target_endpoint"] == "POST /v1/company-facts/candidates"
    assert decision["candidate_payload_ready"] is True
    assert decision["candidate_payload_digest"].startswith("sha256:")
    assert decision["next_action"] == "CALL_BOX_ENDPOINT"
    Draft7Validator(_schema("intake_decision.schema.json")).validate(decision)


def test_confidence_one_is_blocked_for_candidate_payload():
    payload = {
        "category": "company_policy",
        "question_patterns": ["A?", "B?"],
        "answer_runtime_text": "충분히 긴 답변입니다.",
        "source": "사내규정",
        "confidence": 1.0,
    }
    with pytest.raises(IntakeContractError):
        validate_company_fact_candidate_payload(payload, model_cls=FakeCompanyFactCandidateRequest)


def test_company_fact_schema_available_in_main_validates_payload():
    payload = {
        "category": "company_policy",
        "question_patterns": ["A?", "B?"],
        "answer_runtime_text": "충분히 긴 답변입니다.",
        "source": "사내규정",
        "confidence": 0.5,
    }
    digest = validate_company_fact_candidate_payload(payload)
    assert digest.startswith("sha256:")


def test_company_fact_schema_import_failure_is_fail_closed(monkeypatch):
    import butler_pc_core.connect_loop.intake_router as intake_router

    payload = {
        "category": "company_policy",
        "question_patterns": ["A?", "B?"],
        "answer_runtime_text": "충분히 긴 답변입니다.",
        "source": "사내규정",
        "confidence": 0.5,
    }

    def _raise_unavailable():
        raise CompanyFactSchemaUnavailable()

    monkeypatch.setattr(intake_router, "_load_company_fact_candidate_model", _raise_unavailable)
    with pytest.raises(CompanyFactSchemaUnavailable):
        validate_company_fact_candidate_payload(payload)


def test_company_format_candidate_stays_none_admin_followup():
    decision = decide_intake(request_id="req-5", attachment_bundle=format_bundle(), runtime_text="회사 양식", policy_ready_override=True)
    assert decision["primary_destination"] == "company_format_candidate"
    assert decision["target_endpoint"] == "none"
    assert decision["candidate_endpoint_hint"] is None
    assert decision["next_action"] == "ADMIN_FORMAT_REGISTRATION_REQUIRED"
    assert decision["fail_class"] == "ADMIN_FORMAT_REGISTRATION_REQUIRED"
    assert dispatchable_endpoint(decision) is None


def test_multi_attachment_conflict_asks_followup():
    bundle = extract_attachment_features([
        RuntimeAttachment("거래일자,입금,출금,잔액\n".encode("utf-8"), filename="bank.csv", content_type="text/csv"),
        RuntimeAttachment("제1조 회사 내규 시행일".encode(), filename="policy.txt", content_type="text/plain"),
    ])
    decision = decide_intake(request_id="req-6", attachment_bundle=bundle, runtime_text="", policy_ready_override=True)
    assert decision["primary_destination"] == "ask_followup"
    assert decision["target_endpoint"] == "none"
    assert decision["fail_class"] == "MULTI_ATTACHMENT_CONFLICT"
    assert decision["fallback_required"] is True


def test_decision_id_is_order_invariant_for_attachments():
    a = RuntimeAttachment("거래일자,입금,출금,잔액\n".encode("utf-8"), filename="bank.csv", content_type="text/csv")
    b = RuntimeAttachment("제1조 회사 내규 시행일".encode(), filename="policy.txt", content_type="text/plain")
    d1 = decide_intake(request_id="req-7", attachment_bundle=extract_attachment_features([a, b]), policy_ready_override=True)
    d2 = decide_intake(request_id="req-7", attachment_bundle=extract_attachment_features([b, a]), policy_ready_override=True)
    assert d1["decision_id"] == d2["decision_id"]


def test_decision_id_includes_runtime_text_digest():
    d1 = decide_intake(request_id="req-runtime", attachment_bundle=bank_bundle(), runtime_text="분개", policy_ready_override=True)
    d2 = decide_intake(request_id="req-runtime", attachment_bundle=bank_bundle(), runtime_text="데이터 분석", policy_ready_override=True)
    assert d1["decision_id"] != d2["decision_id"]


def test_dlp_bucket_records_signal_without_raw_value():
    raw = "거래일자,입금,출금\n/Users/private/path,sk-proj-secret-like-token\n".encode()
    bundle = extract_attachment_features([RuntimeAttachment(raw, filename="bank.csv", content_type="text/csv")])
    decision = decide_intake(request_id="req-8", attachment_bundle=bundle, runtime_text="분개", policy_ready_override=True)
    encoded = json.dumps(decision, ensure_ascii=False)
    assert "DLP_SIGNAL_PRESENT" in encoded
    assert "/Users/private/path" not in encoded
    assert "sk-proj-secret-like-token" not in encoded


def test_field_aware_raw_gate_blocks_path_in_followup_prompt_but_not_endpoint_slash():
    decision = decide_intake(request_id="req-9", attachment_bundle=bank_bundle(), runtime_text="분개", policy_ready_override=True)
    assert_intake_payload_safe(decision)  # endpoint slash is not a false positive
    tainted = dict(decision)
    tainted["followup_prompt"] = "파일 /Users/me/bank.csv를 다시 올려주세요"
    with pytest.raises(IntakeContractError):
        assert_intake_payload_safe(tainted)


def test_corrupt_or_macro_fail_closed():
    bundle = extract_attachment_features([RuntimeAttachment(b"not-a-zip", filename="book.xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")])
    assert bundle.unsupported_files
    decision = decide_intake(request_id="req-10", attachment_bundle=bundle, policy_ready_override=True)
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True


def test_no_static_test_token_fallback_in_route_source():
    route_source = (ROOT / "butler_pc_core" / "sidecar" / "routes" / "router_intake_decide.py").read_text(encoding="utf-8")
    assert "test-valid-capability-token" not in route_source
    assert "verify_authorization_header" in route_source


def test_dataset_routes_to_box8_followup_because_endpoint_missing():
    decision = decide_intake(request_id="req-11", attachment_bundle=dataset_bundle(), runtime_text="데이터 분석", policy_ready_override=True)
    assert decision["primary_destination"] == "box8_data_insight"
    assert decision["target_endpoint"] == "none"
    assert decision["next_action"] == "ASK_FOLLOWUP"


def test_no_raw_keys_in_persisted_decision_surface():
    decision = decide_intake(request_id="req-12", attachment_bundle=bank_bundle(), runtime_text="분개", policy_ready_override=True)
    encoded = json.dumps(decision, ensure_ascii=False)
    forbidden = ["sample_cell_value", "source_text_runtime", "runtime_file_text", "filename", "file_path"]
    assert not any(item in encoded for item in forbidden)


def test_raw_zero_verifier_failure_message_is_raw_free():
    script = ROOT / "scripts" / "verify_intake_router_raw_zero.py"
    spec = importlib.util.spec_from_file_location("verify_intake_router_raw_zero", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.RawZeroVerifierFailure) as excinfo:
        module._assert_no_forbidden_surface({"surface": "/Users/private/path"})
    assert str(excinfo.value) == "FORBIDDEN_VALUE"
    assert "/Users/private/path" not in str(excinfo.value)


def test_policy_bootstrap_status_fail_closed_without_store():
    from butler_pc_core.connect_loop.intake_router import policy_bootstrap_status
    status = policy_bootstrap_status(None)
    assert status.ready is False
    assert status.fail_class in {"POLICY_BOOTSTRAP_STATUS_UNAVAILABLE", "POLICY_BOOTSTRAP_REQUIRED", "POLICY_LOAD_FAILED"}


def test_audio_meeting_routes_to_box7_followup_endpoint_none():
    bundle = extract_attachment_features([RuntimeAttachment(b"audio-bytes", filename="meeting.m4a", content_type="audio/mp4")])
    decision = decide_intake(request_id="req-13", attachment_bundle=bundle, runtime_text="회의록 만들어줘", policy_ready_override=True)
    assert decision["primary_destination"] == "box7_meeting_minutes"
    assert decision["target_endpoint"] == "none"
    assert decision["next_action"] == "ASK_FOLLOWUP"


def test_external_doc_to_convert_routes_to_box2_when_policy_ready():
    raw = "타사 양식으로 된 외부 문서입니다. 우리 양식으로 변환 필요".encode()
    bundle = extract_attachment_features([RuntimeAttachment(raw, filename="external.txt", content_type="text/plain")])
    decision = decide_intake(request_id="req-14", attachment_bundle=bundle, runtime_text="우리 양식으로 변환", policy_ready_override=True)
    assert decision["primary_destination"] == "box2_form_convert"
    assert decision["target_endpoint"] == "POST /v1/cards/2/rewrite"


def test_draft_source_routes_to_box3_when_policy_ready():
    raw = "사업계획 보고서 자료입니다. 매출 계획과 출시 일정 요약".encode()
    bundle = extract_attachment_features([RuntimeAttachment(raw, filename="plan.txt", content_type="text/plain")])
    decision = decide_intake(request_id="req-15", attachment_bundle=bundle, runtime_text="초안 작성", policy_ready_override=True)
    assert decision["primary_destination"] == "box3_draft_from_material"
    assert decision["target_endpoint"] == "POST /v1/cards/3/draft"


def test_candidate_payload_invalid_returns_block_decision():
    bad = {"category": "x", "question_patterns": ["하나"], "answer_runtime_text": "짧음", "source": "내", "confidence": 0.5}
    decision = decide_intake(
        request_id="req-16",
        attachment_bundle=policy_bundle(),
        runtime_text="회사 규정",
        structured_candidate_payload=bad,
        policy_ready_override=True,
        company_fact_model_cls=FakeCompanyFactCandidateRequest,
    )
    assert decision["target_endpoint"] == "none"
    assert decision["next_action"] == "BLOCK"
    assert decision["fail_class"] == "INTAKE_COMPANY_FACT_CANDIDATE_SCHEMA_INVALID"


def test_target_endpoint_invalid_gate_blocks():
    from butler_pc_core.connect_loop.intake_router import assert_intake_payload_safe
    decision = decide_intake(request_id="req-17", attachment_bundle=bank_bundle(), runtime_text="분개", policy_ready_override=True)
    bad = dict(decision)
    bad["target_endpoint"] = "POST /unknown"
    with pytest.raises(IntakeContractError):
        assert_intake_payload_safe(bad)


def test_route_module_contains_no_box_endpoint_call_logic():
    source = (ROOT / "butler_pc_core" / "sidecar" / "routes" / "router_intake_decide.py").read_text(encoding="utf-8")
    assert "TestClient" not in source
    assert ".post(" not in source.replace('@router.post("/v1/router/intake-decide")', "")
    assert "requests." not in source
