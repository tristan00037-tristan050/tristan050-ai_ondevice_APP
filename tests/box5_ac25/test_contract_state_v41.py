from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ac25 import contract_parse as parser
from ac25 import contract_state as state


FIXTURE = Path(__file__).parent / "fixtures" / "r6_audit_35_guard_keys.json"
KEY_LIST_SHA256 = "3d2fbb8d6910ad5aecdeeedba0a96b92cdcd40ab72dcef60480dd6189c459f82"


def evaluate(exit_code, primary, keys=(), parse_error="NONE"):
    return state.evaluate_contract_state(
        exit_code=exit_code,
        primary_failed_guard=primary,
        failing_guard_keys=keys,
        parse_error_code=parse_error,
    )


def audit_keys() -> tuple[str, ...]:
    raw = FIXTURE.read_bytes()
    assert raw.endswith(b"\n")
    document = json.loads(raw)
    return tuple(document)


def test_exit_zero_none_zero_keys_passes():
    verdict = evaluate(0, "NONE")
    assert verdict == state.ContractStateVerdict(state.ContractOutcome.PASS, "NONE")


def test_exit_zero_none_one_zero_key_is_inconsistent():
    verdict = evaluate(0, "NONE", ("ONE_OK",))
    assert verdict.outcome is state.ContractOutcome.INVALID
    assert verdict.error_code == state.CONTRACT_EXIT_STATE_INCONSISTENT


def test_audit_35_key_fixture_is_inconsistent():
    keys = audit_keys()
    verdict = evaluate(0, "NONE", keys)
    assert len(keys) == 35
    assert verdict.outcome is state.ContractOutcome.INVALID
    assert verdict.error_code == state.CONTRACT_EXIT_STATE_INCONSISTENT


def test_audit_35_key_fixture_digest_is_exact():
    payload = json.dumps(
        sorted(audit_keys()),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == KEY_LIST_SHA256


def test_exit_zero_named_primary_is_inconsistent():
    assert evaluate(0, "named guard v1").outcome is state.ContractOutcome.INVALID


def test_exit_nonzero_none_zero_keys_is_inconsistent():
    assert evaluate(1, "NONE").outcome is state.ContractOutcome.INVALID


def test_exit_nonzero_named_primary_fails():
    verdict = evaluate(1, "named guard v1")
    assert verdict == state.ContractStateVerdict(
        state.ContractOutcome.FAIL,
        state.CONTRACT_FAILED,
    )


def test_exit_nonzero_with_zero_keys_fails():
    verdict = evaluate(1, "NONE", ("ONE_OK",))
    assert verdict.outcome is state.ContractOutcome.FAIL


@pytest.mark.parametrize("primary", ["UNPARSED", "UNPARSED_DUPLICATE"])
def test_unparsed_primary_never_passes(primary):
    assert evaluate(0, primary).outcome is state.ContractOutcome.INVALID
    assert evaluate(1, primary).outcome is state.ContractOutcome.INVALID


def test_duplicate_primary_never_passes():
    parsed = parser.parse_contract_output(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\n"
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\n"
    )
    assert parsed.primary_failed_guard == "UNPARSED_DUPLICATE"
    assert parsed.parse_error_code == parser.CONTRACT_DUPLICATE_PRIMARY
    assert evaluate(
        0,
        parsed.primary_failed_guard,
        parsed.failing_guard_keys,
        parsed.parse_error_code,
    ).outcome is state.ContractOutcome.INVALID


def test_duplicate_contract_key_is_rejected():
    parsed = parser.parse_contract_output(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\nONE_OK=1\nONE_OK=1\n"
    )
    assert parsed.parse_error_code == parser.CONTRACT_DUPLICATE_KEY


def test_conflicting_duplicate_contract_key_is_rejected():
    parsed = parser.parse_contract_output(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\nONE_OK=0\nONE_OK=1\n"
    )
    assert parsed.parse_error_code == parser.CONTRACT_DUPLICATE_KEY


def test_primary_with_spaces_is_preserved_whole():
    name = "mcp zero trust drift contract v1"
    parsed = parser.parse_contract_output(
        f"REPO_CONTRACTS_FAILED_GUARD={name}\n".encode()
    )
    assert parsed.primary_failed_guard == name
    assert parsed.parse_error_code == "NONE"


@pytest.mark.parametrize(
    "value",
    [
        (True, "NONE", ()),
        (-1, "NONE", ()),
        (0, "bad\nname", ()),
        (0, "NONE", ("BAD",)),
        (0, "NONE", ("Z_OK", "A_OK")),
        (0, "NONE", ("A_OK", "A_OK")),
    ],
)
def test_malformed_guard_key_is_rejected(value):
    verdict = evaluate(value[0], value[1], value[2])
    assert verdict.outcome is state.ContractOutcome.INVALID
    assert verdict.error_code == state.CONTRACT_INPUT_INVALID


def test_parser_rejects_malformed_zero_guard_key():
    parsed = parser.parse_contract_output(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\nbad_OK=0\n"
    )
    assert parsed.parse_error_code == parser.CONTRACT_MALFORMED_GUARD_KEY
