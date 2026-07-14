from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError

_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SafeEvent:
    event_id: str
    fixture_id: str
    state: str
    digests: Mapping[str, str]
    counters: Mapping[str, int]

    def as_dict(self) -> dict[str, object]:
        if not _ID.fullmatch(self.event_id) or not _ID.fullmatch(self.fixture_id) or not _ID.fullmatch(self.state):
            _block("SAFE_EVENT_ID")
        if any(not _ID.fullmatch(key) or not _SHA256.fullmatch(value) for key, value in self.digests.items()):
            _block("SAFE_EVENT_DIGEST")
        if any(not _ID.fullmatch(key) or type(value) is not int or value < 0 for key, value in self.counters.items()):
            _block("SAFE_EVENT_COUNTER")
        payload: dict[str, object] = {
            "schema_version": "butler.model-tier-b.safe-event.v2.8",
            "event_id": self.event_id,
            "fixture_id": self.fixture_id,
            "state": self.state,
            "digests": dict(sorted(self.digests.items())),
            "counters": dict(sorted(self.counters.items())),
        }
        payload["event_sha256"] = canonical_sha256(payload)
        return payload


def safe_exception_event(*, stable_error_code: str, module_id: str, line_id: int) -> dict[str, object]:
    if not _ID.fullmatch(stable_error_code) or not _ID.fullmatch(module_id) or type(line_id) is not int or line_id <= 0:
        _block("SAFE_EXCEPTION_FIELDS")
    return {"stable_error_code": stable_error_code, "module_id": module_id, "line_id": line_id, "message_recorded": False, "traceback_recorded": False}


def _block(detail: str) -> None:
    raise GateError(FailClass.SECURITY_PRIVACY, detail, exit_code=ExitCode.SECURITY)
