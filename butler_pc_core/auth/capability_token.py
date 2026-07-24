from __future__ import annotations

import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from butler_pc_core.fail_class import FailClass


DEFAULT_TOKEN_PATH = Path.home() / ".butler" / "sidecar_token"


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
    token_path: Path = DEFAULT_TOKEN_PATH
    _token: str | None = None

    def generate(self) -> str:
        self._token = secrets.token_urlsafe(32)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(self._token + "\n", encoding="utf-8")
        self.token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return self._token

    def clear(self) -> None:
        self._token = None
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

    def verify_authorization_header(self, authorization: str | None) -> None:
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


def auth_error_payload(error: CapabilityTokenError) -> dict[str, str]:
    return {"fail_class": error.fail_class.value, "message": error.message}
