from __future__ import annotations

from dataclasses import replace

import pytest

from ac25.strict_receipt import StrictReceiptError, parse_junit_observation, parse_tap_observation
from ac25.strict_v44 import validate_strict_receipt
from ac25.v44_types import JUnitObservation, JUnitTestIdentity, TapObservation, TapTestIdentity
from tests.box5_ac25.v44_fixtures import valid_input


def _codes(inp):
    return validate_strict_receipt(inp).failures


def _candidate(**changes):
    original = valid_input()
    return original, replace(original.candidate_bundle, **changes)


def _junit(cases: str, *, tests="1", failures="0", errors="0", skipped="0") -> bytes:
    return (
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}">{cases}</testsuite></testsuites>'
    ).encode()


def _case(name="test_ok", children=""):
    return f'<testcase classname="suite.Case" name="{name}">{children}</testcase>'


def _parse_junit(raw):
    return parse_junit_observation(
        raw, artifact_logical_id="ac25-v44-python", shard_id="python", xml_path="junit.xml",
    )


def _parse_tap(raw):
    return parse_tap_observation(
        raw, artifact_logical_id="ac25-v44-node", shard_id="node", tap_path="publish.tap",
    )


def test_zero_guard_inventory_rejected():
    document = __import__("tests.box5_ac25.v44_fixtures", fromlist=["policy_document"]).policy_document()
    document["guard_inventory"] = []
    assert "GUARD_INVENTORY_EMPTY" in _codes(valid_input(document))


def test_invented_nonempty_guard_rejected():
    original, candidate = _candidate(guard_items=((0, "INVENTED_OK", "1"),))
    codes = _codes(replace(original, candidate_bundle=candidate))
    assert "GUARD_INVENTORY_MISSING" in codes and "GUARD_INVENTORY_EXTRA" in codes


def test_proper_subset_guard_rejected():
    original, candidate = _candidate(guard_items=())
    assert "GUARD_INVENTORY_MISSING" in _codes(replace(original, candidate_bundle=candidate))


def test_extra_guard_rejected():
    original, candidate = _candidate(guard_items=((0, "ONE_OK", "1"), (1, "TWO_OK", "1")))
    assert "GUARD_INVENTORY_EXTRA" in _codes(replace(original, candidate_bundle=candidate))


def test_duplicate_guard_rejected():
    original, candidate = _candidate(guard_items=((0, "ONE_OK", "1"), (1, "ONE_OK", "1")))
    assert "GUARD_INVENTORY_DUPLICATE" in _codes(replace(original, candidate_bundle=candidate))


def test_reordered_guard_rejected():
    from tests.box5_ac25.v44_fixtures import policy_document
    document = policy_document()
    document["guard_inventory"] = [{"ordinal": 0, "key": "ONE_OK"}, {"ordinal": 1, "key": "TWO_OK"}]
    inp = valid_input(document)
    candidate = replace(inp.candidate_bundle, guard_items=((0, "TWO_OK", "1"), (1, "ONE_OK", "1")))
    assert "GUARD_INVENTORY_ORDER_MISMATCH" in _codes(replace(inp, candidate_bundle=candidate))


def test_exact_guard_inventory_passes():
    assert "GUARD_INVENTORY_MISSING" not in _codes(valid_input())


def test_missing_required_junit_artifact_rejected():
    original, candidate = _candidate(junit=())
    assert "JUNIT_REQUIRED_SHARD_MISSING" in _codes(replace(original, candidate_bundle=candidate))


def test_zero_junit_tests_rejected():
    original = valid_input()
    empty = JUnitObservation(0, 0, 0, 0, (), "0" * 64)
    candidate = replace(original.candidate_bundle, junit=(empty,))
    assert "JUNIT_ZERO_TESTS" in _codes(replace(original, candidate_bundle=candidate))


def test_partial_junit_inventory_rejected():
    original = valid_input()
    identity = JUnitTestIdentity("ac25-v44-python", "python", "junit.xml", "suite.Case", "other")
    observation = replace(original.candidate_bundle.junit[0], identities=(identity,))
    candidate = replace(original.candidate_bundle, junit=(observation,))
    assert "JUNIT_IDENTITY_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_extra_junit_test_rejected():
    original = valid_input()
    extra = JUnitTestIdentity("ac25-v44-python", "python", "junit.xml", "suite.Case", "extra")
    observation = replace(
        original.candidate_bundle.junit[0], total=2,
        identities=original.candidate_bundle.junit[0].identities + (extra,),
    )
    candidate = replace(original.candidate_bundle, junit=(observation,))
    assert "JUNIT_IDENTITY_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_duplicate_normalized_junit_id_rejected():
    raw = _junit(_case() + _case(), tests="2")
    with pytest.raises(StrictReceiptError, match="JUNIT_DUPLICATE_IDENTITY"):
        _parse_junit(raw)


def test_nested_junit_suite_rejected():
    raw = b'<testsuites><testsuite tests="0" failures="0" errors="0" skipped="0"><testsuite/></testsuite></testsuites>'
    with pytest.raises(StrictReceiptError, match="JUNIT_MALFORMED"):
        _parse_junit(raw)


def test_unsupported_junit_namespace_rejected():
    raw = b'<testsuite xmlns="urn:x" tests="1" failures="0" errors="0" skipped="0"><testcase classname="a" name="b"/></testsuite>'
    with pytest.raises(StrictReceiptError, match="JUNIT_MALFORMED"):
        _parse_junit(raw)


def test_multiple_junit_terminal_states_rejected():
    raw = _junit(_case(children="<failure/><error/>"), failures="1", errors="1")
    with pytest.raises(StrictReceiptError, match="JUNIT_MALFORMED"):
        _parse_junit(raw)


def test_exact_nonempty_junit_inventory_passes():
    observed = _parse_junit(_junit(_case()))
    assert observed.total == 1 and observed.identities == valid_input().candidate_bundle.junit[0].identities


def test_missing_required_tap_artifact_rejected():
    original, candidate = _candidate(tap=())
    assert "TAP_REQUIRED_SHARD_MISSING" in _codes(replace(original, candidate_bundle=candidate))


def test_zero_tap_tests_rejected():
    with pytest.raises(StrictReceiptError, match="TAP_ZERO_TESTS"):
        _parse_tap(b"TAP version 13\n1..0\n")


def test_partial_tap_inventory_rejected():
    original = valid_input()
    observation = replace(original.candidate_bundle.tap[0], identities=())
    candidate = replace(original.candidate_bundle, tap=(observation,))
    assert "TAP_IDENTITY_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_duplicate_tap_number_rejected():
    raw = b"TAP version 13\nok 1 - a\nok 1 - b\n1..2\n"
    with pytest.raises(StrictReceiptError, match="TAP_MALFORMED"):
        _parse_tap(raw)


def test_empty_normalized_tap_name_rejected():
    with pytest.raises(StrictReceiptError, match="TAP_MALFORMED"):
        _parse_tap(b"TAP version 13\nok 1 -    \n1..1\n")


def test_nested_subtest_identity_stable():
    raw = b"TAP version 13\n# Subtest: child\n    ok 1 - inner\n    1..1\nok 1 - child\n1..1\n"
    observed = _parse_tap(raw)
    assert tuple(item.subtest_path for item in observed.identities) == (("child",), ())
    assert tuple(item.name for item in observed.identities) == ("inner", "child")


def test_tap_bailout_rejected():
    with pytest.raises(StrictReceiptError, match="TAP_MALFORMED"):
        _parse_tap(b"TAP version 13\nBail out! stop\n1..1\n")


def test_unexpected_skip_or_todo_rejected():
    original = valid_input()
    skipped = replace(original.candidate_bundle.tap[0], skipped=1)
    candidate = replace(original.candidate_bundle, tap=(skipped,))
    assert "TAP_IDENTITY_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_exact_nonempty_tap_inventory_passes():
    observed = _parse_tap(b"TAP version 13\nok 1 - publishes safely\n1..1\n")
    assert observed.identities == valid_input().candidate_bundle.tap[0].identities
