from __future__ import annotations

import uuid

import pytest

from butler_pc_core.helper1.trace import PRODUCT_SEQUENCE, RunTrace, TraceError


def _trace() -> RunTrace:
    return RunTrace(
        request_id=str(uuid.uuid4()),
        workspace_id=str(uuid.uuid4()),
        generation_id=str(uuid.uuid4()),
        session_digest="a" * 64,
        action="ask",
    )


def test_trace_is_hash_chained_and_commits_exactly_one_terminal() -> None:
    trace = _trace()
    for name in PRODUCT_SEQUENCE[:-1]:
        trace.append(name, {"status": "OK"})
    trace.terminal("ANSWERED")
    trace.verify_complete()
    assert trace.terminal_count == 1
    assert trace.root != "0" * 64
    with pytest.raises(TraceError, match="TRACE_AFTER_TERMINAL"):
        trace.append("TERMINAL_COMMITTED", {"kind": "ANSWERED"})


def test_trace_rejects_reordered_stage_and_early_failure_is_explicit() -> None:
    trace = _trace()
    with pytest.raises(TraceError, match="TRACE_ORDER_INVALID"):
        trace.append("RETRIEVAL_COMPLETED", {})
    trace.append("STRICT_REQUEST_DECODED", {})
    trace.terminal("REFUSED_POLICY")
    trace.verify_complete()
    assert trace.terminal_count == 1
