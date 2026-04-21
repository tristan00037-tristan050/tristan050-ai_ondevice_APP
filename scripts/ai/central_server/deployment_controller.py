from __future__ import annotations
from .central_contracts import DeployResult, ModelStatus, DeploymentOrder

class DeploymentController:
    def __init__(self, registry, audit):
        self.registry = registry
        self.audit = audit
        self.history = []

    def deploy(self, order: DeploymentOrder, safe_mode: bool = False) -> DeployResult:
        version = self.registry.versions.get(order.model_version_id)
        if safe_mode:
            return DeployResult(ok=False, order_id=order.order_id, model_version_id=order.model_version_id, status="BLOCKED", error_code="SAFE_MODE_ACTIVE")
        if not version:
            return DeployResult(ok=False, order_id=order.order_id, model_version_id=order.model_version_id, status="BLOCKED", error_code="MODEL_NOT_FOUND")
        if not (version.status == ModelStatus.APPROVED.value and version.deploy_approved == 1):
            return DeployResult(ok=False, order_id=order.order_id, model_version_id=order.model_version_id, status="BLOCKED", error_code="MODEL_NOT_APPROVED")
        order.status = "DEPLOYED"
        self.history.append(order)
        version.status = ModelStatus.DEPLOYED.value
        return DeployResult(ok=True, order_id=order.order_id, model_version_id=order.model_version_id, status="DEPLOYED")
