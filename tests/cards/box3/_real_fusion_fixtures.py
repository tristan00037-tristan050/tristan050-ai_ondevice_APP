"""Box3 real 융합 테스트 공유 픽스처(테스트 전용).

passing_asset_manifest 는 real 경로 로직을 검증하기 위한 fixture 이며, 실제 자산
SHA/인터페이스 인벤토리는 PENDING 이다(production 자산 아님). 기본 경로는 항상
contract_only(real claim closed)로 동작한다.
"""
from __future__ import annotations

from dataclasses import asdict

from butler_pc_core.cards.box3.asset_manifest import (
    Box3AssetRecord,
    build_contract_only_asset_manifest,
)
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope

_FIXTURE_SHA = "a" * 64
PASSING_REF = (
    "프로젝트 알파 납품 일정 표 | 납품일 2026년 3월 31일 | 계약 금액 1억원 | 담당자 검토 완료 | 합의 완료 보고"
)
PASSING_DRAFT = (
    "제목: 프로젝트 알파 납품 보고\n"
    "배경: 프로젝트 알파 납품 일정 보고\n"
    "핵심 내용: 납품일 2026년 3월 31일 계약 금액 1억원\n"
    "근거: 담당자 검토 완료 합의 완료\n"
    "확인 필요: 없음\n"
    "최종 문안: 프로젝트 알파 납품 일정 계약 금액 담당자 검토 완료 보고\n"
)


def _passing_row(name: str) -> Box3AssetRecord:
    return Box3AssetRecord(
        asset_name=name,
        role="fixture",
        display_sha_prefix=_FIXTURE_SHA[:8] + "...",
        asset_path="ref:FIXTURE",
        sha256_full=_FIXTURE_SHA,
        sha_scope="file",
        measured_at="2026-06-02T00:00:00+00:00",
        measured_by="fixture",
        source_metadata_files=["adapter_config.json"],
        interface_inventory_status="pass",
        real_claim_allowed=True,
        fail_class=None,
    )


def passing_asset_manifest() -> dict:
    rows = [
        _passing_row("helper3_format"),
        _passing_row("helper4_grounding"),
        _passing_row("helper7_table_figure"),
        _passing_row("helper8_company_style"),
    ]
    return {
        "schema_version": "box3.asset_manifest.v1",
        "status": "ASSET_INVENTORY_PASS",
        "real_claim_allowed": True,
        "state_gate": "REAL",
        "created_at": "2026-06-02T00:00:00+00:00",
        "assets": [asdict(row) for row in rows],
    }


def contract_only_manifest() -> dict:
    return build_contract_only_asset_manifest("2026-06-02T00:00:00+00:00")


def supported_runner(_envelope: Box3RealRuntimeEnvelope) -> str:
    return PASSING_DRAFT


def passing_envelope() -> Box3RealRuntimeEnvelope:
    return Box3RealRuntimeEnvelope.from_raw(
        drafting_request="납품 보고서를 작성하라",
        reference_texts=[PASSING_REF],
    )
