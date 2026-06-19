from __future__ import annotations

import os
from dataclasses import dataclass

from .contracts import AdminContext, ContractValidationError
from .role_registry import RoleRegistryLoadError, get_default_role_registry_store

ZERO_DIGEST = "sha256:" + "0" * 64
TEST_ADMIN_AUTH_ENV = "BUTLER_ALLOW_TEST_ADMIN_AUTH"


@dataclass(frozen=True)
class AdminAuthError(PermissionError):
    fail_class: str
    message: str


def _test_admin_auth_allowed() -> bool:
    return os.environ.get(TEST_ADMIN_AUTH_ENV) == "1" and os.environ.get("PYTEST_CURRENT_TEST") is not None


def _verify_admin_context_base(context: AdminContext | None, *, operation: str) -> AdminContext:
    """Verify Admin RBAC without RoleRegistry registration.

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


def verify_admin_context(context: AdminContext | None, *, operation: str) -> AdminContext:
    """Verify Admin RBAC and device-local RoleRegistry registration."""

    verified = _verify_admin_context_base(context, operation=operation)
    try:
        registry = get_default_role_registry_store()
        if registry.is_empty():
            raise AdminAuthError("ADMIN_ROLE_REGISTRY_EMPTY", "admin role registry is not initialized")
        registered = registry.lookup_active(verified.admin_id_digest)
    except AdminAuthError:
        raise
    except RoleRegistryLoadError as exc:
        raise AdminAuthError("ADMIN_ROLE_REGISTRY_LOAD_FAILED", "admin role registry load failed") from exc
    if registered is None:
        raise AdminAuthError("ADMIN_ROLE_NOT_REGISTERED", "admin role is not registered")
    if registered.role != "admin":
        raise AdminAuthError("ADMIN_ROLE_MISMATCH", "registered admin role required")
    return verified


def admin_error_payload(exc: AdminAuthError) -> dict[str, str]:
    return {"fail_class": exc.fail_class, "message": exc.message}
