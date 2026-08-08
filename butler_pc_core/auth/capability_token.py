from __future__ import annotations

import hashlib
import os
import secrets
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from butler_pc_core.fail_class import FailClass


def _default_token_path() -> Path:
    app_data = os.environ.get("BUTLER_APP_DATA_DIR", "").strip()
    if app_data:
        root = Path(app_data).expanduser()
        if root.is_absolute():
            return root / "ipc" / "sidecar.capability"
    return Path.home() / ".butler" / "sidecar_token"


# Exception classes must not be frozen: Python 3.11+ assigns __traceback__ on
# the raised instance, which a frozen dataclass rejects (FrozenInstanceError).
@dataclass(eq=False)
class CapabilityTokenError(Exception):
    fail_class: FailClass
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass
class CapabilityTokenManager:
    token_path: Path = field(default_factory=_default_token_path)
    _token: str | None = None
    _session: "LocalIpcSession | None" = None

    def generate(self) -> str:
        self._token = secrets.token_urlsafe(32)
        self.token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token_path.parent.chmod(0o700)
        temporary = self.token_path.with_name(
            f".{self.token_path.name}.{secrets.token_hex(8)}.tmp"
        )
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(self._token + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.token_path)
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise
        self.token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self._session = LocalIpcSession.from_token(self._token)
        return self._token

    def clear(self) -> None:
        self._token = None
        self._session = None
        try:
            self.token_path.unlink()
        except FileNotFoundError:
            pass

    @property
    def token(self) -> str | None:
        if self._token:
            return self._token
        if self.token_path.exists():
            try:
                value = self.token_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                # fail-closed: 토큰 파일이 존재하나 읽기 불가
                # (권한 drift / transient I/O / 손상 등).
                # generic 500으로 escape하지 않고 CapabilityTokenError로
                # 변환하여 인증 분류의 deterministic 본질을 유지한다.
                raise CapabilityTokenError(
                    FailClass.CAPABILITY_TOKEN_INVALID,
                    f"capability token file unreadable: {self.token_path} "
                    f"({exc.__class__.__name__})",
                ) from exc
            self._token = value or None
        return self._token

    def verify_authorization_header(self, authorization: str | None) -> "LocalIpcSession":
        if not authorization:
            raise CapabilityTokenError(FailClass.CAPABILITY_TOKEN_MISSING, "capability token missing")
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            raise CapabilityTokenError(FailClass.CAPABILITY_TOKEN_INVALID, "capability token invalid")
        presented = authorization[len(prefix):].strip()
        expected = self.token
        if not expected:
            raise CapabilityTokenError(FailClass.CAPABILITY_TOKEN_MISSING, "capability token not initialized")
        if not secrets.compare_digest(presented, expected):
            raise CapabilityTokenError(FailClass.CAPABILITY_TOKEN_INVALID, "capability token invalid")
        session = self._session
        if session is None:
            session = LocalIpcSession.from_token(expected)
            self._session = session
        if session.expires_at <= datetime.now(timezone.utc):
            raise CapabilityTokenError(FailClass.CAPABILITY_TOKEN_INVALID, "capability token expired")
        return session


@dataclass(frozen=True)
class LocalIpcSession:
    """Transport-only identity for the local desktop/sidecar channel.

    This object deliberately has no human actor, role, or accounting
    permission. Those properties can only come from the separately verified
    user authorization authority at the Box5 product boundary.
    """

    session_id: str
    device_id: str
    session_digest: str
    device_binding_digest: str
    audience: str
    expires_at: datetime

    @classmethod
    def from_token(cls, token: str) -> "LocalIpcSession":
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        device_id = "device_" + digest[32:48]
        return cls(
            session_id="session_" + digest[:32],
            device_id=device_id,
            session_digest=digest,
            device_binding_digest=hashlib.sha256(device_id.encode("utf-8")).hexdigest(),
            audience="butler-local-sidecar-ipc",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )


def auth_error_payload(error: CapabilityTokenError) -> dict[str, str]:
    return {"fail_class": error.fail_class.value, "message": error.message}
