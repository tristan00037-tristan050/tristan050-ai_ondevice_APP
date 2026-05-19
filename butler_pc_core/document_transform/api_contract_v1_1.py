"""D-4 Card 2 document transform sidecar API contract v1.1.

This module defines the canonical endpoint contract required by
D4_CARD2_DOCUMENT_TRANSFORM_v1_1. The existing sidecar implementation may keep
legacy `/document_transform/*` routes, but all D-4 v1.1 verification targets
must reference the `/api/document_transform/*` contract defined here.

No raw source text is persisted by this contract. Request/response audit data
must use digest or metadata-only fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


StepName = Literal["extract", "parse_template", "map", "compose", "stream"]


@dataclass(frozen=True)
class EndpointContract:
    step: StepName
    method: str
    path: str
    timeout_sec: int
    raw_log_allowed: bool
    external_egress_allowed: bool


CARD2_ENDPOINTS_V1_1: tuple[EndpointContract, ...] = (
    EndpointContract("extract", "POST", "/api/document_transform/extract", 60, False, False),
    EndpointContract("parse_template", "POST", "/api/document_transform/parse_template", 60, False, False),
    EndpointContract("map", "POST", "/api/document_transform/map", 60, False, False),
    EndpointContract("compose", "POST", "/api/document_transform/compose", 60, False, False),
    EndpointContract("stream", "GET", "/api/document_transform/stream", 180, False, False),
)


def endpoint_matrix() -> list[dict[str, object]]:
    """Return a JSON-serializable endpoint matrix for evidence generation."""
    return [
        {
            "step": item.step,
            "method": item.method,
            "path": item.path,
            "timeout_sec": item.timeout_sec,
            "raw_log_allowed": item.raw_log_allowed,
            "external_egress_allowed": item.external_egress_allowed,
        }
        for item in CARD2_ENDPOINTS_V1_1
    ]


def assert_contract_complete() -> None:
    """Fail closed if any D-4 v1.1 endpoint is missing or unsafe."""
    expected = {"extract", "parse_template", "map", "compose", "stream"}
    actual = {item.step for item in CARD2_ENDPOINTS_V1_1}
    missing = sorted(expected - actual)
    if missing:
        raise AssertionError(f"missing document transform endpoints: {missing}")
    for item in CARD2_ENDPOINTS_V1_1:
        if item.raw_log_allowed:
            raise AssertionError(f"raw log allowed for {item.path}")
        if item.external_egress_allowed:
            raise AssertionError(f"external egress allowed for {item.path}")
        if item.step == "stream" and item.timeout_sec != 180:
            raise AssertionError("SSE stream timeout must be 180 seconds")
        if item.step != "stream" and item.timeout_sec != 60:
            raise AssertionError(f"{item.step} timeout must be 60 seconds")
