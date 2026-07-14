from __future__ import annotations

import hmac
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar

from .canonical import sha256_bytes
from .errors import ExitCode, FailClass, GateError

T = TypeVar("T")


class DraftState(StrEnum):
    FRESH = "FRESH"
    BORROWED = "BORROWED"
    DESTROYED = "DESTROYED"


class VolatileDraft:
    """Exactly-once raw buffer with best-effort overwrite.

    This class does not claim to erase copies created by CPython, a model
    runtime, or an approved callback.  The caller must give ownership of a
    bytearray and must terminate the dedicated worker after sensitive work.
    """

    __slots__ = ("_buf", "_request_sha256", "_draft_sha256", "_state", "_borrow_active")

    def __init__(self, owned_buffer: bytearray, request_sha256: bytes) -> None:
        if type(owned_buffer) is not bytearray or not owned_buffer:
            raise GateError(FailClass.SCHEMA_INVALID, "DRAFT_BUFFER_INVALID", exit_code=ExitCode.SCHEMA)
        if type(request_sha256) is not bytes or len(request_sha256) != 32:
            raise GateError(FailClass.SCHEMA_INVALID, "REQUEST_DIGEST_INVALID", exit_code=ExitCode.SCHEMA)
        self._buf = owned_buffer
        self._request_sha256 = request_sha256
        self._draft_sha256 = bytes.fromhex(sha256_bytes(owned_buffer))
        self._state = DraftState.FRESH
        self._borrow_active = False

    @property
    def state(self) -> DraftState:
        return self._state

    @property
    def draft_sha256(self) -> bytes:
        return self._draft_sha256

    def __repr__(self) -> str:
        return f"<VolatileDraft REDACTED state={self._state.value}>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("VolatileDraft is not serializable")

    def __reduce_ex__(self, protocol: int):
        raise TypeError("VolatileDraft is not serializable")

    def __copy__(self):
        raise TypeError("VolatileDraft is not copyable")

    def __deepcopy__(self, memo: object):
        raise TypeError("VolatileDraft is not copyable")

    def __getstate__(self):
        raise TypeError("VolatileDraft is not serializable")

    def __bytes__(self):
        raise TypeError("VolatileDraft does not expose bytes")

    def consume_into(
        self,
        request_sha256: bytes,
        expected_draft_sha256: bytes,
        callback: Callable[[memoryview], T],
    ) -> T:
        if self._state is not DraftState.FRESH or self._borrow_active:
            raise GateError(FailClass.RAW_REUSE, "EXACTLY_ONCE", exit_code=ExitCode.PROTOCOL)
        if not hmac.compare_digest(request_sha256, self._request_sha256):
            self.destroy()
            raise GateError(FailClass.RAW_BINDING_MISMATCH, "REQUEST_MISMATCH", exit_code=ExitCode.DIGEST)
        current = bytes.fromhex(sha256_bytes(self._buf))
        if not hmac.compare_digest(current, self._draft_sha256) or not hmac.compare_digest(
            expected_draft_sha256, self._draft_sha256
        ):
            self.destroy()
            raise GateError(FailClass.RAW_BINDING_MISMATCH, "DRAFT_MISMATCH", exit_code=ExitCode.DIGEST)
        if not callable(callback):
            self.destroy()
            raise GateError(FailClass.SCHEMA_INVALID, "CALLBACK_INVALID", exit_code=ExitCode.SCHEMA)
        self._state = DraftState.BORROWED
        self._borrow_active = True
        view = memoryview(self._buf).toreadonly()
        try:
            return callback(view)
        finally:
            try:
                view.release()
            finally:
                self.destroy()

    def destroy(self) -> None:
        if self._state is DraftState.DESTROYED:
            return
        for index in range(len(self._buf)):
            self._buf[index] = 0
        self._borrow_active = False
        self._state = DraftState.DESTROYED

    def destroyed_probe(self) -> bool:
        """Return only a boolean; never expose the buffer."""
        return self._state is DraftState.DESTROYED and not any(self._buf)

