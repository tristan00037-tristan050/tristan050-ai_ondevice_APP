from __future__ import annotations

import hashlib
import hmac
import secrets

import pytest

from butler_pc_core.accounting.classify.account_column import (
    AccountRegistryEntry,
    AccountRegistrySnapshot,
)
from butler_pc_core.accounting.classify.registered_info import (
    LearnedRuleCandidate,
    LearnedRuleMatch,
    LearnedRuleMatcher,
    LearnedRuleMatchStatus,
    LearnedRuleState,
    RegisteredInfoContractError,
    RegisteredInfoReason,
)
from butler_pc_core.accounting.classify.vendor_match import (
    VENDOR_MATCH_CONTEXT,
    VendorMatchContractError,
    derive_vendor_match_token,
    derive_vendor_match_token_set,
    normalize_vendor_descriptor,
)

from .conftest import digest


def _test_root() -> bytes:
    return secrets.token_bytes(32)


class _SoftwareTestKey:
    """Test-only stand-in for the platform keystore contract."""

    def __init__(self, key_id: str, root: bytes) -> None:
        self._key_id = key_id
        self._root = root

    @property
    def key_id(self) -> str:
        return self._key_id

    def tenant_context_hmac_sha256(self, *, tenant_id, context, payload):
        assert context == VENDOR_MATCH_CONTEXT
        derived = hmac.new(
            self._root,
            context + b"\x00" + tenant_id.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return hmac.new(derived, payload, hashlib.sha256).digest()


class _UnavailableKey(_SoftwareTestKey):
    def tenant_context_hmac_sha256(self, *, tenant_id, context, payload):
        raise OSError("keystore unavailable")


def _registry() -> AccountRegistrySnapshot:
    return AccountRegistrySnapshot(
        digest("registered-info-registry"),
        digest("registered-info-overlay"),
        "ko-KR",
        (
            AccountRegistryEntry("PL.SGA.ADVERTISING", "5100", "광고 선전비", True),
            AccountRegistryEntry(
                "PL.SGA.GROUP", None, "판매관리비", False, "GROUP_NODE"
            ),
        ),
    )


def _tokens(*, tenant_id="tenant-one", active=None, retiring=()):
    return derive_vendor_match_token_set(
        "주식회사 Example  강남점 (123)",
        tenant_id=tenant_id,
        adapter_family="bank-csv",
        descriptor_schema_version="descriptor-v1",
        active_key=active or _SoftwareTestKey("key-v2", _test_root()),
        retiring_keys=retiring,
    )


def _candidate(tokens, **overrides) -> LearnedRuleCandidate:
    token = tokens.read_tokens[0]
    values = {
        "rule_id": "rule-registered-001",
        "tenant_digest": digest("tenant-one"),
        "account_id": "PL.SGA.ADVERTISING",
        "state": LearnedRuleState.ACTIVE_SUGGESTION,
        "registry_digest": _registry().registry_digest,
        "overlay_digest": _registry().overlay_digest,
        "match_key_id": token.key_id,
        "normalization_version": token.normalization_version,
        "adapter_family": token.adapter_family,
        "descriptor_schema_version": token.descriptor_schema_version,
        "resource_version": 1,
        "vendor_match_token": token.storage_value(),
    }
    values.update(overrides)
    return LearnedRuleCandidate(**values)


def test_normalization_is_non_destructive_and_version_narrow():
    value = normalize_vendor_descriptor("  ＡＣＭＥ  Co., Ltd.  강남점(123)  ")
    assert value == "acme co., ltd. 강남점(123)"
    assert "강남점" in value
    assert "123" in value
    assert "ltd." in value


def test_tenant_adapter_and_schema_are_cryptographically_bound():
    key = _SoftwareTestKey("key-v1", _test_root())
    base = derive_vendor_match_token(
        "Example Vendor",
        tenant_id="tenant-one",
        adapter_family="bank-csv",
        descriptor_schema_version="descriptor-v1",
        key_handle=key,
    )
    other_tenant = derive_vendor_match_token(
        "Example Vendor",
        tenant_id="tenant-two",
        adapter_family="bank-csv",
        descriptor_schema_version="descriptor-v1",
        key_handle=key,
    )
    other_adapter = derive_vendor_match_token(
        "Example Vendor",
        tenant_id="tenant-one",
        adapter_family="bank-xlsx",
        descriptor_schema_version="descriptor-v1",
        key_handle=key,
    )
    other_schema = derive_vendor_match_token(
        "Example Vendor",
        tenant_id="tenant-one",
        adapter_family="bank-csv",
        descriptor_schema_version="descriptor-v2",
        key_handle=key,
    )
    assert (
        len(
            {
                value.storage_value()
                for value in (base, other_tenant, other_adapter, other_schema)
            }
        )
        == 4
    )


def test_branch_number_and_corporate_suffix_are_not_removed_into_a_collision():
    key = _SoftwareTestKey("key-v1", _test_root())

    def token(value: str) -> str:
        return derive_vendor_match_token(
            value,
            tenant_id="tenant-one",
            adapter_family="bank-csv",
            descriptor_schema_version="descriptor-v1",
            key_handle=key,
        ).storage_value()

    assert token("주식회사 Example 강남점(123)") != token(
        "주식회사 Example 강남점(124)"
    )
    assert token("주식회사 Example 강남점(123)") != token("Example 강남점(123)")


def test_token_and_rule_repr_redact_internal_storage_value():
    tokens = _tokens()
    value = tokens.write_token.storage_value()
    candidate = _candidate(tokens)
    assert value not in repr(tokens.write_token)
    assert value not in repr(candidate)


def test_dual_read_new_write_matches_retiring_token():
    old = _SoftwareTestKey("key-v1", _test_root())
    current = _SoftwareTestKey("key-v2", _test_root())
    tokens = _tokens(active=current, retiring=(old,))
    candidate = _candidate(
        tokens,
        match_key_id=tokens.read_tokens[1].key_id,
        vendor_match_token=tokens.read_tokens[1].storage_value(),
    )
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(candidate,),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.EXACT
    assert tokens.write_token.key_id == "key-v2"


def test_exact_active_rule_returns_only_a_suggestion_match():
    tokens = _tokens()
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(_candidate(tokens),),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.EXACT
    assert result.reason is RegisteredInfoReason.USER_RULE_EXACT_MATCH
    assert result.account_id == "PL.SGA.ADVERTISING"


def test_one_character_token_difference_is_no_match_not_fuzzy_match():
    tokens = _tokens()
    value = tokens.write_token.storage_value()
    replacement = "A" if value[-1] != "A" else "B"
    candidate = _candidate(tokens, vendor_match_token=value[:-1] + replacement)
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(candidate,),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.NO_MATCH


def test_matching_token_with_adapter_metadata_drift_is_blocked():
    tokens = _tokens()
    candidate = _candidate(tokens, adapter_family="bank-xlsx")
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(candidate,),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.BLOCKED
    assert result.reason is RegisteredInfoReason.BLOCK_RULE_CONTRACT


@pytest.mark.parametrize(
    "state", [LearnedRuleState.INACTIVE_USER, LearnedRuleState.INACTIVE_REGISTRY]
)
def test_inactive_rules_never_suggest(state):
    tokens = _tokens()
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(_candidate(tokens, state=state),),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.NO_MATCH


def test_cross_tenant_candidate_is_a_boundary_block_not_an_oracle():
    tokens = _tokens()
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(_candidate(tokens, tenant_digest=digest("tenant-two")),),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.BLOCKED
    assert result.reason is RegisteredInfoReason.BLOCK_TENANT_BOUNDARY


def test_stale_registry_and_nonassignable_account_fail_closed():
    tokens = _tokens()
    stale = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(_candidate(tokens, registry_digest=digest("old-registry")),),
        registry=_registry(),
    )
    blocked_group = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(_candidate(tokens, account_id="PL.SGA.GROUP"),),
        registry=_registry(),
    )
    assert stale.reason is RegisteredInfoReason.BLOCK_REGISTRY_STALE
    assert blocked_group.reason is RegisteredInfoReason.BLOCK_ACCOUNT_NONASSIGNABLE


def test_multiple_active_matches_require_explicit_conflict_resolution():
    tokens = _tokens()
    candidates = (
        _candidate(tokens),
        _candidate(tokens, rule_id="rule-registered-002", resource_version=2),
    )
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=candidates,
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.CONFLICT
    assert result.reason is RegisteredInfoReason.LEARNED_RULE_CONFLICT


def test_degraded_rotation_match_blocks_instead_of_falling_back():
    tokens = _tokens()
    result = LearnedRuleMatcher().match(
        tenant_digest=digest("tenant-one"),
        tokens=tokens,
        candidates=(_candidate(tokens, state=LearnedRuleState.DEGRADED_KEY_ROTATION),),
        registry=_registry(),
    )
    assert result.status is LearnedRuleMatchStatus.BLOCKED
    assert result.reason is RegisteredInfoReason.BLOCK_KEY_ROTATION


def test_unavailable_keystore_and_invalid_digest_fail_closed():
    with pytest.raises(VendorMatchContractError, match="SECURE_KEY_UNAVAILABLE"):
        _tokens(active=_UnavailableKey("key-v2", _test_root()))

    class WrongLengthKey(_SoftwareTestKey):
        def tenant_context_hmac_sha256(self, *, tenant_id, context, payload):
            return b"short"

    with pytest.raises(
        VendorMatchContractError, match="SECURE_KEY_INVALID_HMAC_RESULT"
    ):
        _tokens(active=WrongLengthKey("key-v2", _test_root()))


def test_key_ring_rejects_duplicate_key_ids():
    with pytest.raises(VendorMatchContractError, match="DUPLICATE_MATCH_KEY_ID"):
        _tokens(
            active=_SoftwareTestKey("same-key", _test_root()),
            retiring=(_SoftwareTestKey("same-key", _test_root()),),
        )


def test_rule_match_status_cannot_carry_a_contradictory_reason():
    with pytest.raises(RegisteredInfoContractError, match="RULE_MATCH_REASON_INVALID"):
        LearnedRuleMatch(
            LearnedRuleMatchStatus.NO_MATCH,
            RegisteredInfoReason.USER_RULE_EXACT_MATCH,
        )
