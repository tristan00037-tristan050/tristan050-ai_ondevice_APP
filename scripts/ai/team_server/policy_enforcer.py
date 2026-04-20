from __future__ import annotations

from types import MappingProxyType
from typing import Any, Dict

from .team_audit_logger import TeamAuditLogger
from .team_contracts import ACCESS_ORDER, AccessLevel, PolicyDecision, ServerStatus, contains_sensitive_text


class PolicyEnforcer:
    def __init__(self, audit_logger: TeamAuditLogger) -> None:
        self.audit_logger = audit_logger
        self.config = MappingProxyType({
            "role_access": MappingProxyType({
                "member": AccessLevel.TEAM,
                "lead": AccessLevel.CONFIDENTIAL,
                "admin": AccessLevel.CONFIDENTIAL,
            })
        })

    def _allowed_for_role(self, role: str) -> AccessLevel:
        return self.config["role_access"].get(role, AccessLevel.PUBLIC)

    def check(self, user_id: str, team_id: str, action: str, resource: Dict[str, Any], context: Dict[str, Any], server_status: ServerStatus = ServerStatus.NORMAL) -> PolicyDecision:
        allowed = True
        blocked_fields: list[str] = []
        reason = "ALLOW"
        if server_status == ServerStatus.SAFE_MODE and action in {"collect", "finetune_trigger", "admin_write"}:
            allowed = False
            reason = "SAFE_MODE_READ_ONLY"
        elif contains_sensitive_text(resource):
            allowed = False
            reason = "SENSITIVE_KEY_BLOCK"
        elif "rollout" in action.lower():
            allowed = False
            reason = "ROLLOUT_POLICY_BLOCK"
        else:
            required = AccessLevel(resource.get("access_level", AccessLevel.PUBLIC.value))
            role = str(context.get("role", "member"))
            allowed_level = self._allowed_for_role(role)
            if ACCESS_ORDER[allowed_level] < ACCESS_ORDER[required]:
                allowed = False
                reason = "UNAUTHORIZED_ACCESS"
                blocked_fields.append("access_level")

        policy_id = "policy-ai31-v4"
        if not allowed:
            event = self.audit_logger.build_event(
                team_id=team_id,
                user_id=user_id,
                device_id=str(context.get("device_id", "unknown")),
                event_type="POLICY_BLOCK",
                policy_id=policy_id,
                data_digest16="0" * 16,
                access_granted=False,
                reason_code=reason,
                error_code="POLICY",
                selected_route=action,
                server_status=server_status.value,
                access_level=str(resource.get("access_level", AccessLevel.PUBLIC.value)),
                event_code="POLICY_BLOCKED",
            )
            self.audit_logger.append(event)
        return PolicyDecision(allowed, reason, policy_id, blocked_fields)
