"""Butler Company Policy/Format SSOT package.

Scope:
- CompanyPolicy.v1 / CompanyFormat.v1 / PolicyTaskEnvelope.v1 / PolicyGateResult.v1
- Admin RBAC separate from sidecar capability token
- Device-local encrypted company format vault
- Digest-only policy/format audit
"""
from .contracts import (
    CompanyPolicy,
    CompanyFormat,
    PolicyTaskEnvelope,
    PolicyGateResult,
    AdminContext,
    stable_json_digest,
)
from .policy_gate import PolicyGate, build_policy_task_envelope
from .admin_auth import verify_admin_context, AdminAuthError
from .role_registry import RoleRegistryStore, RoleRegistryLoadError

# helper3 format adapter 위치 정합 (표준 156): MAINDEV `company_policy/format_adapter.py`
# 위치는 폐기되었고, ALG 의 `butler_pc_core/cards/box3/adapters/company_format_adapter.py`
# 단일 경로(박스 3 real adapter 위치)가 정본이다. caller 는 그 경로에서 직접 import.

__all__ = [
    "CompanyPolicy",
    "CompanyFormat",
    "PolicyTaskEnvelope",
    "PolicyGateResult",
    "AdminContext",
    "PolicyGate",
    "build_policy_task_envelope",
    "verify_admin_context",
    "AdminAuthError",
    "RoleRegistryStore",
    "RoleRegistryLoadError",
    "stable_json_digest",
]
