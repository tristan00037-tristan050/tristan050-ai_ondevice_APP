from __future__ import annotations

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from butler_pc_core.accounting.classifier import classify_df
from butler_pc_core.accounting.classify.models import BankDirection, EconomicEventKind
from butler_pc_core.accounting.classify.port import (
    RuleBasis,
    RuleFacts,
    VendorMatchState,
)
from butler_pc_core.accounting.policy.vendor_descriptor import descriptor_hmac
from butler_pc_core.accounting.classify.shadow.adapter import AtlinkShadowPort
from butler_pc_core.accounting.classify.shadow.runner import (
    rows_from_dataframe,
    run_shadow_over_dataframe,
)
from scripts import box5_shadow_compare


@pytest.mark.parametrize("amount_column", ["금액", "거래금액", "amount"])
def test_single_signed_amount_columns_are_not_dropped(amount_column):
    classified = classify_df(
        pd.DataFrame(
            [
                {
                    "거래일시": "2026-07-16",
                    "거래내용": "구독료",
                    amount_column: "-1,200",
                }
            ]
        )
    )
    assert "_amt" not in classified.columns

    rows = rows_from_dataframe(classified)
    assert len(rows) == 1
    assert rows[0]["amount_minor"] == -1_200
    assert len(run_shadow_over_dataframe(classified)) == 1


def test_cli_baseline_loads_and_passes_active_profile(monkeypatch):
    active_profile = object()
    captured: dict[str, object] = {}

    class Store:
        def load_active_profile(self):
            return active_profile

    def fake_classify_file(path, *, company_profile):
        captured["path"] = path
        captured["company_profile"] = company_profile
        return "classified"

    monkeypatch.setattr(box5_shadow_compare, "CompanyProfileStore", Store)
    monkeypatch.setattr(box5_shadow_compare, "classify_file", fake_classify_file)

    result = box5_shadow_compare._classify_product_baseline(Path("group-a.csv"))
    assert result == "classified"
    assert captured == {
        "path": "group-a.csv",
        "company_profile": active_profile,
    }


def _approved_bundle(rel: str) -> dict:
    if rel == "vendor_descriptor_registry.template.json":
        return {
            "schema_version": "butler.box5.vendor_descriptor_registry.v1",
            "policy_profile_id": "atlink.smb.v1",
            "status": "APPROVED",
            "approval_id": "finance-approval-20260716",
            "descriptors": [
                {
                    "descriptor_id": "vendor.saas.approved",
                    # ★ real HMAC of the approved vendor via the SAME function a producer uses.
                    "normalized_exact_value_hmac": descriptor_hmac("승인상호", policy_profile_id="atlink.smb.v1"),
                    "bank_direction": "OUTFLOW",
                    "service_kind": "SAAS",
                    "management_tags": ["SAAS"],
                    "evidence_ref": "evidence-approved-1",
                }
            ],
        }
    if rel == "upstream/chart_of_accounts.atlink.v1.json":
        return {"accounts": [{"account_id": "PL.SGA.PAYMENT_FEE"}]}
    if rel == "upstream/account_mapping_rules.v1.json":
        return {
            "rules": [
                {
                    "rule_id": "MAP-SAAS-001",
                    "management_tag": "SAAS",
                    "target_account_id": "PL.SGA.PAYMENT_FEE",
                    "direction": "DEBIT",
                }
            ]
        }
    raise AssertionError(f"unexpected bundle path: {rel}")


def _facts(direction: BankDirection) -> RuleFacts:
    return RuleFacts(
        direction=direction,
        event_kind=EconomicEventKind.NORMAL,
        vendor_match_id="vendor.saas.approved",
        purpose_code=None,
        purpose_evidence_digest=None,
        description_feature_digests=(),
        evidence_digests=(),
        service_period_start=None,
        service_period_end=None,
        accounting_period_end=None,
    )


def test_approved_registry_uses_schema_descriptor_fields(monkeypatch):
    monkeypatch.setattr(AtlinkShadowPort, "_read", staticmethod(_approved_bundle))
    port = AtlinkShadowPort(vendor_text="승인상호")

    matched = port.match_vendor_exact(None)
    assert matched.state is VendorMatchState.EXACT
    assert matched.match_id == "vendor.saas.approved"


def test_v1_rule_direction_maps_bank_outflow_to_debit(monkeypatch):
    monkeypatch.setattr(AtlinkShadowPort, "_read", staticmethod(_approved_bundle))
    port = AtlinkShadowPort()

    outflow = port.select_rule(_facts(BankDirection.OUTFLOW))
    assert outflow.basis is RuleBasis.EXACT_DETERMINISTIC
    assert outflow.account_id == "PL.SGA.PAYMENT_FEE"

    inflow = port.select_rule(_facts(BankDirection.INFLOW))
    assert inflow.basis is RuleBasis.NO_MATCH
