"""재검토팀 HOLD 3-블로커 회귀 시험.

1. self-transfer guard 가 shadow 에도 연결(상대계좌번호 → company_profile 대조 → REVIEW_SELF_TRANSFER,
   select_rule 미호출).
2. 승인 거래처 매칭이 registry 와 동일한 정규화·HMAC 방식(실제 거래 한 줄 → 토큰 생성 → registry
   대조 → AUTO_PROPOSE).
3. shadow 가 제품 응답을 기다리게 하지 않음(fire-and-forget, 느려도 제품 무영향).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from butler_pc_core.accounting.classify.models import DecisionState, ReasonCode
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.shadow.adapter import (
    AtlinkShadowPort,
    build_canonical_transaction,
)
from butler_pc_core.accounting.policy.vendor_descriptor import descriptor_hmac
from butler_pc_core.company_profile.contracts import make_runtime_profile

PROFILE = make_runtime_profile(
    own_bank_holder_aliases=["테스트대표"],
    own_company_aliases=["테스트회사"],
    own_account_numbers=["123-456-789"],
)


def _tx(**o):
    base = dict(
        index=0,
        amount_minor=-10000,
        booked_date=date(2026, 3, 1),
        value_date=date(2026, 3, 1),
        desc_text="d",
        vendor_text="아무개",
        counterparty_text="아무개",
    )
    base.update(o)
    return build_canonical_transaction(**base)


# ── Blocker 1: self-transfer guard ────────────────────────────────────────


def test_blocker1_own_account_becomes_review_self_transfer_and_skips_rule():
    port = AtlinkShadowPort(
        company_profile=PROFILE, counterparty_account_no="123-456-789"
    )
    draft = Stage3Classifier().classify(_tx(), port)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_SELF_TRANSFER
    # ★ select_rule must NOT be consulted once the self-transfer guard fires
    assert not any(c.startswith("rule:") for c in port._calls)
    assert draft.account_id is None


def test_blocker1_non_own_account_does_not_trigger_self_transfer():
    port = AtlinkShadowPort(
        company_profile=PROFILE, counterparty_account_no="999-888-777"
    )
    draft = Stage3Classifier().classify(_tx(), port)
    assert draft.reason_code is not ReasonCode.REVIEW_SELF_TRANSFER


def test_blocker1_no_profile_stays_conservative_no_crash():
    port = AtlinkShadowPort(company_profile=None, counterparty_account_no="123-456-789")
    draft = Stage3Classifier().classify(_tx(), port)
    assert draft.state is not DecisionState.AUTO_PROPOSE  # empty registry → review


# ── Blocker 2: registry-consistent HMAC vendor match → AUTO_PROPOSE ────────


def _approved_registry(vendor: str) -> dict:
    # ★ HMAC computed from the SAME function the registry uses — not a pre-inserted placeholder.
    return {
        "schema_version": "butler.box5.vendor_descriptor_registry.v1",
        "policy_profile_id": "atlink.smb.v1",
        "status": "APPROVED",
        "approval_id": "appr-test-001",
        "descriptors": [
            {
                "descriptor_id": "vendor.telecom.approved",
                "normalized_exact_value_hmac": descriptor_hmac(
                    vendor, policy_profile_id="atlink.smb.v1"
                ),
                "bank_direction": "OUTFLOW",
                "service_kind": "TELECOM",
                "management_tags": ["TELECOM"],
                "evidence_ref": "ev-1",
            }
        ],
    }


def test_blocker2_real_transaction_token_matches_registry_and_auto_proposes(
    monkeypatch,
):
    vendor = "케이티 서버 이용료"
    real_read = AtlinkShadowPort._read
    monkeypatch.setattr(
        AtlinkShadowPort,
        "_read",
        staticmethod(
            lambda rel: _approved_registry(vendor)
            if rel == "vendor_descriptor_registry.template.json"
            else real_read(rel)
        ),
    )
    # ★ REAL product path: build_canonical_transaction produces vendor_token; classify() makes the
    # pipeline call port.match_vendor_exact(tx.vendor_token). No direct descriptor_hmac shortcut.
    tx = _tx(vendor_text=vendor)
    assert tx.vendor_token == "tok_" + descriptor_hmac(
        vendor, policy_profile_id="atlink.smb.v1"
    )
    port = AtlinkShadowPort(
        company_profile=PROFILE, counterparty_account_no="999-888-777"
    )
    draft = Stage3Classifier().classify(tx, port)
    assert draft.state is DecisionState.AUTO_PROPOSE
    assert (
        draft.account_id == "PL.SGA.COMMUNICATION"
    )  # TELECOM → 통신비 (registry-bound)
    assert draft.reason_code is ReasonCode.AUTO_PROPOSE_EXACT_RULE
    # match_vendor_exact was actually reached WITH the tx token (a real hmac prefix, not "vendor:-")
    assert any(c.startswith("vendor:") and c != "vendor:-" for c in port._calls)


def test_blocker2_non_approved_vendor_still_reviews(monkeypatch):
    real_read = AtlinkShadowPort._read
    monkeypatch.setattr(
        AtlinkShadowPort,
        "_read",
        staticmethod(
            lambda rel: _approved_registry("케이티 서버 이용료")
            if rel == "vendor_descriptor_registry.template.json"
            else real_read(rel)
        ),
    )
    tx = _tx(vendor_text="전혀다른상호")  # token differs → no registry hit
    port = AtlinkShadowPort(
        company_profile=PROFILE, counterparty_account_no="999-888-777"
    )
    draft = Stage3Classifier().classify(tx, port)
    assert draft.state is not DecisionState.AUTO_PROPOSE


# ── Blocker 3: shadow does not make the product wait ──────────────────────


def test_blocker3_hook_is_fire_and_forget_not_awaited():
    src = Path("butler_sidecar.py").read_text(encoding="utf-8")
    assert re.search(
        r"(?m)^\s*loop\.run_in_executor\(\s*None,\s*run_and_write_shadow,", src
    )
    assert not re.search(
        r"await\s+loop\.run_in_executor\(\s*None,\s*run_and_write_shadow,", src
    )


def test_blocker3_scheduled_slow_shadow_does_not_block_caller():
    async def _run():
        loop = asyncio.get_event_loop()
        started = time.monotonic()
        loop.run_in_executor(None, lambda: time.sleep(1.0))  # slow shadow, NOT awaited
        # caller proceeds immediately instead of waiting ~1s
        return time.monotonic() - started

    elapsed = asyncio.run(_run())
    assert elapsed < 0.2
