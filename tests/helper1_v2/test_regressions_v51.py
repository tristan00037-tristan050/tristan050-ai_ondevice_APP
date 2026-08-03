from __future__ import annotations

from types import SimpleNamespace

from butler_pc_core.helper1.approval_closure import recompute_a4_rows
from butler_pc_core.helper1.measurement import MeasurementError
from butler_pc_core.helper1.pipeline import NativeIndexOperation
from butler_pc_core.helper1.service import Helper1Service

from .v51_support import rows


class _Trace:
    def terminal(self, _: str) -> None:
        pass

    def verify_complete(self) -> None:
        pass


def _pipeline(*, operation=None):
    manifest = SimpleNamespace(
        generation_id="00000000-0000-4000-8000-000000000061",
        digest="d" * 64,
    )
    observed = {"search": 0, "index": 0}

    def search(**_):
        observed["search"] += 1
        raise MeasurementError("MEASUREMENT_SUMMARY_MISMATCH")

    def index(**_):
        observed["index"] += 1
        raise MeasurementError("MEASUREMENT_SUMMARY_MISMATCH")

    return (
        SimpleNamespace(
            index=SimpleNamespace(manifest=manifest),
            index_operation=operation,
            observed_search=search,
            observed_index=index,
        ),
        observed,
    )


def _bypass_authorization(monkeypatch, service: Helper1Service, pipeline) -> None:
    monkeypatch.setattr(service, "_authorize_request", lambda **_: (pipeline, None))
    monkeypatch.setattr(service, "_start_trace", lambda **_: _Trace())


def test_answerable_false_abstention_remains_in_precision_denominator() -> None:
    counts, metrics, _ = recompute_a4_rows(rows("audit"))
    assert counts["predicted_abstention_count"] == 2
    assert counts["false_abstention_count"] == 1
    assert metrics["abstention_precision_ppm"] == 500_000


def test_search_cannot_return_success_without_verified_observation(monkeypatch) -> None:
    service = Helper1Service()
    pipeline, observed = _pipeline()
    _bypass_authorization(monkeypatch, service, pipeline)
    status, body = service.search(
        workspace_id="00000000-0000-4000-8000-000000000060",
        query="query",
        top_k=3,
        request_id="00000000-0000-4000-8000-000000000062",
        client_request_id="00000000-0000-4000-8000-000000000063",
        requested_generation_id=None,
        effect_intent="display_only",
        session_digest="e" * 64,
    )
    assert observed == {"search": 1, "index": 0}
    assert status == 503
    assert body["reason_code"] == "MEASUREMENT_INVALID"


def test_index_cannot_return_success_without_verified_observation(monkeypatch) -> None:
    service = Helper1Service()
    operation = object.__new__(NativeIndexOperation)
    pipeline, observed = _pipeline(operation=operation)
    _bypass_authorization(monkeypatch, service, pipeline)
    status, body = service.index(
        workspace_id="00000000-0000-4000-8000-000000000060",
        request_id="00000000-0000-4000-8000-000000000064",
        client_request_id="00000000-0000-4000-8000-000000000065",
        requested_generation_id=None,
        effect_intent="index_only",
        session_digest="f" * 64,
    )
    assert observed == {"search": 0, "index": 1}
    assert status == 503
    assert body["reason_code"] == "MEASUREMENT_INVALID"
