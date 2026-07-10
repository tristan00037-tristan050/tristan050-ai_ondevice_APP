from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .actual_contracts import assert_persistable_digest_only, sha256_text, stable_json_digest
from .actual_fail_class import (
    BLOCK_GROUNDING_EMBEDDER_MISSING,
    PARTIAL_BGE_M3_FALLBACK_USED,
    PARTIAL_EMBEDDER_UNAVAILABLE,
    PARTIAL_HELPER_SDK_UNAVAILABLE,
)
# 박스 3 helper SDK v1.3 정합 (2026-06-04, PR #779): main 본진 import 경로 정정.
# - ClaimGroundingSummary 는 real_grounding.py SSOT (real_contracts 가 아님).
# - DigestOnlyReceipt 는 helper_sdk_bridge 자체에서 정의 (본 모듈 안 dataclass).
from .real_contracts import ClaimVerdict, EvidenceUnit
from .real_grounding import (
    ClaimGroundingSummary,
    extract_claims,
    extract_evidence_units,
    ground_claims,
    summarize_grounding,
)

HELPER4_SDK_PATH_ENV = "BUTLER_HELPER4_GROUNDING_SDK_PATH"
HELPER7_SDK_PATH_ENV = "BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH"
HELPER8_SDK_PATH_ENV = "BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH"
HELPER2_SDK_PATH_ENV = "BUTLER_HELPER2_EMBEDDING_SDK_PATH"
BGE_M3_MODEL_DIR_ENV = "BUTLER_BGE_M3_MODEL_DIR"

@dataclass(frozen=True)
class DigestOnlyReceipt:
    """박스 3 helper SDK v1.3 — bridge 안의 digest-only 영수증 (raw 0).

    PR #779 정정: 본진 real_contracts.py 에 별도 모듈이 없으므로 본 모듈 안에 정의 (단일
    경로, helper_sdk_bridge SSOT). 모든 필드는 digest/카운트/상태 라벨만 허용.
    """

    schema_version: str
    request_digest: str
    stage: str
    counters: dict[str, Any]
    status: str
    fail_class: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_digest": self.request_digest,
            "stage": self.stage,
            "counters": dict(self.counters),
            "status": self.status,
            "fail_class": self.fail_class,
        }



_HELPER4_MARKER_RE = re.compile(r"\s*\(근거\d+\)\s*$")
_HELPER4_KO_FACT_RE = re.compile(
    r"^(?P<item>[A-Za-z0-9가-힣\s]+?)(?:은|는|이|가)\s+(?P<value>.+?)입니다$"
)


def _normalize_claim_line_for_helper4(claim_text: str) -> str:
    """Normalize one factual Korean sentence into evidence-like item:value form.

    This preserves the claim's own value. It does not replace the claim with
    evidence text, so contradictions remain detectable by helper4.
    """
    text = claim_text.strip()
    text = _HELPER4_MARKER_RE.sub("", text).strip()
    text = text.rstrip(".。").strip()
    m = _HELPER4_KO_FACT_RE.match(text)
    if not m:
        return text
    item = " ".join(m.group("item").split())
    value = " ".join(m.group("value").split())
    return f"{item}: {value}"


def _draft_text_for_helper4_grounding(draft_text: str) -> str:
    """Normalize draft into one factual claim per line before helper4 grounding.

    This does not change the final draft text.
    This does not relax helper4 thresholds.
    Compact labels, abstain rows, and multi-sentence label content are filtered
    by real_grounding.extract_claims(); each remaining factual claim is normalized
    into evidence-like item:value form while preserving its own value.
    """
    claims = extract_claims(draft_text)
    factual_lines = [
        _normalize_claim_line_for_helper4(c.claim_text_runtime_only)
        for c in claims
        if c.is_factual and c.claim_text_runtime_only.strip()
    ]
    return "\n".join(factual_lines) if factual_lines else draft_text


def _promoted_verdict(verdict: ClaimVerdict, factual_digests: set[str]) -> ClaimVerdict:
    """SDK 판정 보강 — 승격만 허용(약화 금지).

    SDK 가 non_claim 으로 본 claim 이라도, real_grounding.extract_claims 의 _is_factual
    (SDK 의 좁은 키워드 사전보다 넓은 정의: 숫자·사실 힌트 포함)이 factual 로 보면
    no_evidence 로 승격한다 — "책상 50개"·"서울시청" 류가 전부 non_claim 처리되어
    factual_claim_count=0 → vacuous BLOCK_NO_FACTUAL_CLAIMS 가 되는 것을 막는다.
    근거 매칭 방향(unsupported/supported/no_evidence)은 SDK 판정을 그대로 신뢰하므로
    절대 바꾸지 않는다. 오직 non_claim → no_evidence 승격만 한다.
    ClaimVerdict 계약상 no_evidence ↔ NO_MATCHING_EVIDENCE · evidence_digests 는 비어야 한다.
    """
    if verdict.support_level == "non_claim" and verdict.claim_digest in factual_digests:
        return ClaimVerdict(
            verdict.claim_id, verdict.claim_digest, "no_evidence", [], verdict.confidence, "NO_MATCHING_EVIDENCE",
        )
    return verdict


def _extract_helper8_styled_text(styled: Any, *, original_draft: str) -> tuple[str, str | None]:
    """helper8 산출물에서 초안 텍스트만 안전 추출한다 (fail-closed).

    지원 형태: str · dict(draft_text|draft_text_runtime|text) · 객체(.draft_text|
    .draft_text_runtime|.text). bridge 내부 계약은 draft_text_runtime, 외부 SDK 객체는
    draft_text 를 쓸 수 있어 양쪽 다 지원한다.

    금지: str(styled)/repr(styled)/getattr 강제 문자열화. 알 수 없는 타입·빈 값·값 자체가
    "StyledDraft(" repr 문자열인 경우는 원본 draft 를 유지하고
    PARTIAL_HELPER_SDK_UNAVAILABLE 로 fail-closed 한다(원문 repr 오염 0).
    """
    if isinstance(styled, str):
        value = styled
    elif isinstance(styled, dict):
        value = None
        for key in ("draft_text", "draft_text_runtime", "text"):
            candidate = styled.get(key)
            if isinstance(candidate, str):
                value = candidate
                break
    else:
        value = None
        for attr in ("draft_text", "draft_text_runtime", "text"):
            candidate = getattr(styled, attr, None)
            if isinstance(candidate, str):
                value = candidate
                break
    if not isinstance(value, str) or not value.strip():
        return original_draft, PARTIAL_HELPER_SDK_UNAVAILABLE
    if value.lstrip().startswith("StyledDraft("):
        return original_draft, PARTIAL_HELPER_SDK_UNAVAILABLE
    return value, None


@dataclass
class EvidenceBundle:
    evidence_units_runtime: list[EvidenceUnit]
    parse_success: bool
    fail_class: str | None
    source_count: int
    parser_receipt: DigestOnlyReceipt

    def persistable_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": "box3.helper7.evidence_bundle.v1_2",
            "evidence_count": len(self.evidence_units_runtime),
            "source_count": self.source_count,
            "parse_success": self.parse_success,
            "fail_class": self.fail_class,
            "evidence_digests": [unit.evidence_digest for unit in self.evidence_units_runtime],
            "source_digests": [unit.source_digest for unit in self.evidence_units_runtime],
            "parser_receipt": self.parser_receipt.to_dict(),
        }
        assert_persistable_digest_only(payload)
        return payload

@dataclass
class GroundingBundle:
    claim_verdicts: list[ClaimVerdict]
    summary: ClaimGroundingSummary
    embedder_provider: str | None
    fail_class: str | None
    receipt: DigestOnlyReceipt

    def persistable_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": "box3.helper4.grounding_bundle.v1_2",
            "claim_verdicts": [verdict.to_dict() for verdict in self.claim_verdicts],
            "summary": self.summary.to_dict(),
            "embedder_provider": self.embedder_provider,
            "fail_class": self.fail_class,
            "receipt": self.receipt.to_dict(),
        }
        assert_persistable_digest_only(payload)
        return payload

@dataclass
class StyledDraft:
    draft_text_runtime: str
    style_applied: bool
    fail_class: str | None
    receipt: DigestOnlyReceipt

    def persistable_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": "box3.helper8.styled_draft.v1_2",
            "draft_digest": sha256_text(self.draft_text_runtime) if self.draft_text_runtime else None,
            "style_applied": self.style_applied,
            "fail_class": self.fail_class,
            "receipt": self.receipt.to_dict(),
        }
        assert_persistable_digest_only(payload)
        return payload

def _import_from_env(path_env: str, module_name: str):
    path = os.environ.get(path_env)
    if path:
        p = Path(path)
        if p.is_file():
            # Import from an exact file path without persisting or logging it.
            spec = importlib.util.spec_from_file_location(module_name, str(p))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                previous_module = sys.modules.get(module_name)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                except Exception:
                    if previous_module is None:
                        sys.modules.pop(module_name, None)
                    else:
                        sys.modules[module_name] = previous_module
                    raise
                return module
        elif p.is_dir():
            sys.path.insert(0, str(p))
    # 박스 3 helper SDK 통합 v1.3 (2026-06-04, PR #779): 단일 경로 SSOT — env 미지정 시
    # cards/box3/sdk/* 캐노니컬 subpackage 를 우선 사용한다 (CODEX src/ 병렬 봉합 0).
    try:
        return importlib.import_module(f"butler_pc_core.cards.box3.sdk.{module_name}")
    except ImportError:
        return importlib.import_module(module_name)

class HelperSdkBridge:
    """Single server-local bridge for helper7 parse, helper4 grounding, helper8 style.

    All raw text stays inside runtime objects. Persistable outputs are digest/count/verdict/fail_class only.
    """

    def __init__(self, *, allow_rule_proxy_for_tests: bool = False):
        self.allow_rule_proxy_for_tests = allow_rule_proxy_for_tests
        self._helper7 = None
        self._helper4 = None
        self._helper8 = None
        self._helper2 = None
        self._embedder_provider: str | None = None

    @classmethod
    def from_env(cls) -> "HelperSdkBridge":
        return cls(allow_rule_proxy_for_tests=os.environ.get("BUTLER_BOX3_ALLOW_TEST_RULE_PROXY") == "1")

    def _load_helper7(self):
        if self._helper7 is None:
            self._helper7 = _import_from_env(HELPER7_SDK_PATH_ENV, "helper7_table_figure_sdk")
        return self._helper7

    def _load_helper4(self):
        if self._helper4 is None:
            self._helper4 = _import_from_env(HELPER4_SDK_PATH_ENV, "helper4_grounding_sdk")
        return self._helper4

    def _load_helper8(self):
        if self._helper8 is None:
            self._helper8 = _import_from_env(HELPER8_SDK_PATH_ENV, "helper8_company_style_sdk")
        return self._helper8

    def _load_embedder(self):
        if self._helper2 is not None:
            return self._helper2, self._embedder_provider
        try:
            module = _import_from_env(HELPER2_SDK_PATH_ENV, "helper2_embedding_sdk")
            # 박스 3 v1.3 real activation (2026-06-04): module 이 .embed() 직접 노출하지 않고
            # Helper2Embedder/Embedder 클래스만 노출하는 경우, 자동으로 인스턴스화 (digest-only).
            embedder_obj = module
            if not callable(getattr(module, "embed", None)):
                for cls_name in ("Helper2Embedder", "Embedder", "BgeM3Embedder"):
                    cls = getattr(module, cls_name, None)
                    if isinstance(cls, type):
                        embedder_obj = cls()
                        break
            self._helper2 = embedder_obj
            self._embedder_provider = "helper2_sdk"
            return self._helper2, self._embedder_provider
        except Exception:
            bge = os.environ.get(BGE_M3_MODEL_DIR_ENV)
            if bge:
                self._embedder_provider = "bge_m3"
                # BGE-M3 fallback is explicit and must be disclosed; this object is a capability marker only.
                self._helper2 = {"provider": "bge_m3", "model_dir_digest": sha256_text(bge)}
                return self._helper2, self._embedder_provider
            return None, None

    def parse_evidence(self, reference_payload: list[str]) -> EvidenceBundle:
        request_digest = stable_json_digest({"reference_digests": [sha256_text(x) for x in reference_payload]})
        try:
            helper7 = self._load_helper7()
        except Exception:
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper7_parse", {}, "partial", PARTIAL_HELPER_SDK_UNAVAILABLE)
            return EvidenceBundle([], False, PARTIAL_HELPER_SDK_UNAVAILABLE, len(reference_payload), receipt)

        try:
            if hasattr(helper7, "parse_for_evidence"):
                raw_units = helper7.parse_for_evidence(reference_payload)
            elif hasattr(helper7, "parse_evidence"):
                raw_units = helper7.parse_evidence(reference_payload)
            else:
                raw_units = reference_payload
            evidence_units: list[EvidenceUnit] = []
            for idx, item in enumerate(raw_units if isinstance(raw_units, list) else [raw_units], start=1):
                if isinstance(item, EvidenceUnit):
                    evidence_units.append(item)
                elif isinstance(item, dict):
                    text = str(item.get("text") or item.get("content") or "")
                    source_text = str(item.get("source_text") or text or "empty")
                    kind = item.get("kind") if item.get("kind") in {"text", "table", "figure"} else "text"
                    evidence_units.append(EvidenceUnit(
                        evidence_id=str(item.get("evidence_id") or f"h7-{idx}"),
                        source_digest=sha256_text(source_text),
                        evidence_digest=sha256_text(text),
                        kind=kind,
                        text_runtime_only=text,
                    ))
                elif isinstance(item, str) and item.strip():
                    evidence_units.extend(extract_evidence_units([item]))
            if not evidence_units:
                evidence_units = extract_evidence_units(reference_payload)
            receipt = DigestOnlyReceipt(
                "box3.helper_sdk.receipt.v1_2",
                request_digest,
                "helper7_parse",
                {"evidence_count": len(evidence_units), "source_count": len(reference_payload)},
                "pass",
                None,
            )
            return EvidenceBundle(evidence_units, True, None, len(reference_payload), receipt)
        except Exception:
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper7_parse", {}, "partial", PARTIAL_HELPER_SDK_UNAVAILABLE)
            return EvidenceBundle([], False, PARTIAL_HELPER_SDK_UNAVAILABLE, len(reference_payload), receipt)

    def ground_claims(self, draft_text: str, evidence_bundle: EvidenceBundle) -> GroundingBundle:
        request_digest = stable_json_digest({
            "draft_digest": sha256_text(draft_text),
            "evidence_digests": [unit.evidence_digest for unit in evidence_bundle.evidence_units_runtime],
        })
        embedder, provider = self._load_embedder()
        if embedder is None:
            summary = summarize_grounding([])
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper4_grounding", {}, "partial", PARTIAL_EMBEDDER_UNAVAILABLE)
            return GroundingBundle([], summary, None, PARTIAL_EMBEDDER_UNAVAILABLE, receipt)
        try:
            helper4 = self._load_helper4()
        except Exception:
            if not self.allow_rule_proxy_for_tests:
                summary = summarize_grounding([])
                receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper4_grounding", {}, "partial", PARTIAL_HELPER_SDK_UNAVAILABLE)
                return GroundingBundle([], summary, provider, PARTIAL_HELPER_SDK_UNAVAILABLE, receipt)
            claims = extract_claims(draft_text)
            verdicts = ground_claims(claims, evidence_bundle.evidence_units_runtime)
            summary = summarize_grounding(verdicts)
            receipt = DigestOnlyReceipt(
                "box3.helper_sdk.receipt.v1_2",
                request_digest,
                "helper4_grounding_rule_proxy_test_only",
                {"claim_count": len(claims), "unsupported_count": summary.unsupported_claim_count},
                "test_fallback",
                summary.fail_class,
            )
            return GroundingBundle(verdicts, summary, provider, summary.fail_class, receipt)

        try:
            if hasattr(helper4, "ground_claims"):
                # 박스 3 v1.3 (2026-06-04, real activation): bundled helper4 SDK 는 second arg
                # 로 EvidenceUnit 리스트 (iterable) 를 기대한다. 일부 외부 helper4 구현은
                # EvidenceBundle 자체를 기대할 수 있으므로 list 호출이 TypeError 면 bundle 로
                # 한 번 더 시도한다.
                evidence_records = evidence_bundle.evidence_units_runtime
                grounding_text = _draft_text_for_helper4_grounding(draft_text)
                try:
                    produced = helper4.ground_claims(grounding_text, evidence_records, embedder=embedder)
                except TypeError:
                    produced = helper4.ground_claims(grounding_text, evidence_bundle, embedder=embedder)
            elif hasattr(helper4, "verify_grounding"):
                produced = helper4.verify_grounding(draft_text, evidence_bundle)
            else:
                produced = None

            if isinstance(produced, GroundingBundle):
                return produced
            if isinstance(produced, dict) and isinstance(produced.get("claim_verdicts"), list):
                verdicts = [
                    ClaimVerdict(
                        item["claim_id"],
                        item["claim_digest"],
                        item["support_level"],
                        list(item.get("evidence_digests", [])),
                        float(item.get("confidence", 0.0)),
                        item["reason_code"],
                    )
                    for item in produced["claim_verdicts"]
                    if isinstance(item, dict)
                ]
            elif isinstance(produced, list):
                # bundled helper4 SDK 가 GroundedClaim 리스트를 반환하는 경로.
                # #852: SDK 의 좁은 factual 사전이 non_claim 오분류한 것을 real_grounding 의
                # (넓은) _is_factual 판정으로 승격한다. claim_digest 로 매칭(양쪽 동일 문장을
                # sha256_text 로 해싱 — feasibility 실측 확인). draft_text 는 이 메서드 인자.
                factual_digests = {c.claim_digest for c in extract_claims(draft_text) if c.is_factual}
                verdicts = []
                for idx, item in enumerate(produced, start=1):
                    if isinstance(item, ClaimVerdict):
                        verdicts.append(_promoted_verdict(item, factual_digests))
                        continue
                    claim_digest = getattr(item, "claim_digest", None) or sha256_text(str(item))
                    support_level = getattr(item, "support_level", "no_evidence")
                    evidence_digests = list(getattr(item, "evidence_digests", []) or [])
                    reason_code = getattr(item, "reason_code", "NO_MATCHING_EVIDENCE")
                    confidence = float(getattr(item, "confidence", 0.0))
                    claim_id = getattr(item, "claim_id", None) or f"h4-{idx}"
                    verdicts.append(_promoted_verdict(
                        ClaimVerdict(claim_id, claim_digest, support_level, evidence_digests, confidence, reason_code),
                        factual_digests,
                    ))
            else:
                claims = extract_claims(draft_text)
                verdicts = ground_claims(claims, evidence_bundle.evidence_units_runtime)
            summary = summarize_grounding(verdicts)
            fail = summary.fail_class
            if provider == "bge_m3" and fail is None:
                fail = PARTIAL_BGE_M3_FALLBACK_USED
            receipt = DigestOnlyReceipt(
                "box3.helper_sdk.receipt.v1_2",
                request_digest,
                "helper4_grounding",
                {
                    "claim_count": summary.factual_claim_count,
                    "unsupported_count": summary.unsupported_claim_count,
                    "no_evidence_count": summary.no_evidence_claim_count,
                },
                "pass" if fail is None else "partial",
                fail,
            )
            return GroundingBundle(verdicts, summary, provider, fail, receipt)
        except Exception:
            summary = summarize_grounding([])
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper4_grounding", {}, "block", BLOCK_GROUNDING_EMBEDDER_MISSING)
            return GroundingBundle([], summary, provider, BLOCK_GROUNDING_EMBEDDER_MISSING, receipt)

    def apply_company_style(self, draft_text: str, profile_ref: str | None = None) -> StyledDraft:
        request_digest = stable_json_digest({"draft_digest": sha256_text(draft_text), "profile_ref_digest": sha256_text(profile_ref or "default")})
        try:
            helper8 = self._load_helper8()
        except Exception:
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper8_style", {}, "partial", PARTIAL_HELPER_SDK_UNAVAILABLE)
            return StyledDraft(draft_text, False, PARTIAL_HELPER_SDK_UNAVAILABLE, receipt)
        try:
            if hasattr(helper8, "apply_company_style"):
                styled = helper8.apply_company_style(draft_text, profile_ref=profile_ref)
            elif hasattr(helper8, "apply_profile"):
                styled = helper8.apply_profile(draft_text, profile_ref)
            else:
                styled = draft_text
            styled_text, style_fail = _extract_helper8_styled_text(styled, original_draft=draft_text)
            if style_fail is not None:
                # 인식 불가/빈 값/ repr 문자열 → repr 오염 대신 원본 draft 유지(fail-closed).
                receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper8_style", {}, "partial", style_fail)
                return StyledDraft(styled_text, False, style_fail, receipt)
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper8_style", {"draft_digest_present": 1}, "pass", None)
            return StyledDraft(styled_text, True, None, receipt)
        except Exception:
            receipt = DigestOnlyReceipt("box3.helper_sdk.receipt.v1_2", request_digest, "helper8_style", {}, "partial", PARTIAL_HELPER_SDK_UNAVAILABLE)
            return StyledDraft(draft_text, False, PARTIAL_HELPER_SDK_UNAVAILABLE, receipt)
