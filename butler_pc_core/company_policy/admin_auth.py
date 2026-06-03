from __future__ import annotations

from dataclasses import dataclass

from .contracts import AdminContext, ContractValidationError


@dataclass(frozen=True)
class AdminAuthError(PermissionError):
    fail_class: str
    message: str


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
    return context


def admin_error_payload(exc: AdminAuthError) -> dict[str, str]:
    return {"fail_class": exc.fail_class, "message": exc.message}
