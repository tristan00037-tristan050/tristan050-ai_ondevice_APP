from __future__ import annotations

import os
from dataclasses import dataclass

from .contracts import AdminContext, ContractValidationError

ZERO_DIGEST = "sha256:" + "0" * 64
TEST_ADMIN_AUTH_ENV = "BUTLER_ALLOW_TEST_ADMIN_AUTH"


@dataclass(frozen=True)
class AdminAuthError(PermissionError):
    fail_class: str
    message: str


def _test_admin_auth_allowed() -> bool:
    return os.environ.get(TEST_ADMIN_AUTH_ENV) == "1" and os.environ.get("PYTEST_CURRENT_TEST") is not None


def verify_admin_context(context: AdminContext | None, *, operation: str) -> AdminContext:
    """Verify Admin RBAC.

    Local sidecar capability token is intentionally not accepted here. Token only
    proves transport authorization. Policy/format mutation requires admin RBAC.
    """

    if context is None:
        raise AdminAuthError("ADMIN_AUTH_REQUIRED", "admin context required")
    try:
        context.to_dict()
    except ContractValidationError as exc:
        raise AdminAuthError("ADMIN_CONTEXT_INVALID", "admin context invalid") from exc
    if context.role != "admin":
        raise AdminAuthError("ADMIN_RBAC_DENIED", f"admin role required for {operation}")
    if context.admin_id_digest == ZERO_DIGEST or context.admin_session_digest == ZERO_DIGEST:
        raise AdminAuthError("ADMIN_DIGEST_PLACEHOLDER", "admin digest placeholder is not allowed")
    if context.auth_method == "test_only" and not _test_admin_auth_allowed():
        raise AdminAuthError("ADMIN_AUTH_METHOD_NOT_ALLOWED", "admin auth method is not allowed")
    return context


def admin_error_payload(exc: AdminAuthError) -> dict[str, str]:
    return {"fail_class": exc.fail_class, "message": exc.message}
