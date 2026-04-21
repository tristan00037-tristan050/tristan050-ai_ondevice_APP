from __future__ import annotations
from datetime import datetime
from .central_contracts import ModelVersion, RegistryResult, ModelStatus

class ModelRegistry:
    def __init__(self):
        self.versions: dict[str, ModelVersion] = {}

    def register(self, version: ModelVersion) -> RegistryResult:
        self.versions[version.version_id] = version
        return RegistryResult(ok=True, version_id=version.version_id, status=version.status)

    def approve(self, version_id: str, approved_by: str = "admin", policy_version: str = "policy-v1", note_digest16: str = "note-digest") -> RegistryResult:
        version = self.versions[version_id]
        version.status = ModelStatus.APPROVED.value
        version.deploy_approved = 1
        version.approved_by = approved_by
        version.approved_at = datetime.utcnow().isoformat()
        version.approval_policy_version = policy_version
        version.approval_note_digest16 = note_digest16
        version.rollback_required_if = "post_deploy_regression"
        return RegistryResult(ok=True, version_id=version_id, status=version.status)

    def get_latest_approved(self):
        approved = [v for v in self.versions.values() if v.status == ModelStatus.APPROVED.value and v.deploy_approved == 1]
        if not approved:
            return None
        approved.sort(key=lambda x: x.trained_at)
        return approved[-1]

    def deprecate(self, version_id: str) -> RegistryResult:
        version = self.versions[version_id]
        version.status = ModelStatus.DEPRECATED.value
        return RegistryResult(ok=True, version_id=version_id, status=version.status)
