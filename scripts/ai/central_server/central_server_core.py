from __future__ import annotations
import argparse, json, hashlib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .central_contracts import (
    CentralServerResponse, TeamInsight, EnterpriseKBDoc, DeploymentOrder,
    EventType, ServerStatus, ModelStatus
)
from .central_persistence import PersistenceManager, SCHEMA_VERSION
from .central_report_writer import CentralReportWriter
from .egress_guard import EgressGuard, EgressPolicyGuard, EgressBlockedError
from .insight_collector import InsightCollector
from .enterprise_kb import EnterpriseKB
from .continuous_learner import ContinuousLearner
from .model_registry import ModelRegistry
from .deployment_controller import DeploymentController
from .enterprise_audit import EnterpriseAudit

def digest16(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]

class CentralServer:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.tmp_dir = self.base_dir / "tmp"
        self.state_dir = self.tmp_dir / "central_state"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.persistence = PersistenceManager(self.state_dir)
        self.audit = EnterpriseAudit(self.tmp_dir / "central_audit.jsonl")
        self.registry = ModelRegistry()
        self.learner = ContinuousLearner(self.registry)
        self.collector = InsightCollector(self.learner)
        self.kb = EnterpriseKB()
        self.deployer = DeploymentController(self.registry, self.audit)
        self.egress_guard = EgressGuard()
        self.egress_policy = EgressPolicyGuard()
        self.report_writer = CentralReportWriter(self.persistence)
        self.server_status = ServerStatus.NORMAL.value
        self.safe_mode_entered = False
        self.safe_mode_reason = ""
        self.safe_mode_entered_at = None
        self.safe_mode_block_count = 0
        self.safe_mode_last_reason = ""
        self.egress_block_count = 0
        self.deploy_block_count = 0
        self._restore()

    def _persist_all(self):
        self.persistence.save_state("enterprise_kb_snapshot.json", {"docs": {k: asdict(v) for k,v in self.kb.docs.items()}})
        self.persistence.save_state("learning_jobs.json", {"jobs": [asdict(j) for j in self.learner.jobs]})
        self.persistence.save_state("model_registry.json", {"versions": {k: asdict(v) for k,v in self.registry.versions.items()}})
        self.persistence.save_state("central_state.json", {
            "server_status": self.server_status,
            "safe_mode_entered": self.safe_mode_entered,
            "safe_mode_reason": self.safe_mode_reason,
            "safe_mode_entered_at": self.safe_mode_entered_at,
            "safe_mode_block_count": self.safe_mode_block_count,
            "safe_mode_last_reason": self.safe_mode_last_reason,
            "egress_block_count": self.egress_block_count,
            "deploy_block_count": self.deploy_block_count,
        })

    def _restore(self):
        docs_state = self.persistence.load_state("enterprise_kb_snapshot.json", empty_state={"docs": {}})
        for key, data in docs_state.get("docs", {}).items():
            self.kb.docs[key] = EnterpriseKBDoc(**data)
            self.kb.lineage[data["lineage_id"]].append(key)
        jobs_state = self.persistence.load_state("learning_jobs.json", empty_state={"jobs": []})
        from .central_contracts import LearningJob, ModelVersion
        self.learner.jobs = [LearningJob(**j) for j in jobs_state.get("jobs", [])]
        registry_state = self.persistence.load_state("model_registry.json", empty_state={"versions": {}})
        self.registry.versions = {k: ModelVersion(**v) for k, v in registry_state.get("versions", {}).items()}
        state = self.persistence.load_state("central_state.json", empty_state={})
        self.server_status = state.get("server_status", self.server_status)
        self.safe_mode_entered = state.get("safe_mode_entered", False)
        self.safe_mode_reason = state.get("safe_mode_reason", "")
        self.safe_mode_entered_at = state.get("safe_mode_entered_at")
        self.safe_mode_block_count = state.get("safe_mode_block_count", 0)
        self.safe_mode_last_reason = state.get("safe_mode_last_reason", "")
        self.egress_block_count = state.get("egress_block_count", 0)
        self.deploy_block_count = state.get("deploy_block_count", 0)

    def _raw_detected(self, request: Dict[str, Any]) -> bool:
        forbidden_keys = {"prompt", "output", "content", "audio", "raw_text", "raw_payload", "document_text"}
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    if lk in forbidden_keys:
                        return True
                    if walk(v):
                        return True
            elif isinstance(obj, list):
                return any(walk(x) for x in obj)
            return False
        return walk(request)

    def enter_safe_mode(self, reason: str):
        self.server_status = ServerStatus.SAFE_MODE.value
        if not self.safe_mode_entered:
            self.safe_mode_entered = True
            self.safe_mode_entered_at = datetime.utcnow().isoformat()
        self.safe_mode_reason = reason
        self.safe_mode_last_reason = reason

    def _block_in_safe_mode(self, route: str) -> bool:
        if self.server_status != ServerStatus.SAFE_MODE.value:
            return False
        allowed = {EventType.INSIGHT_COLLECT.value, EventType.KB_UPDATE.value}
        if route not in allowed:
            self.safe_mode_block_count += 1
            self.safe_mode_last_reason = "SAFE_MODE_READ_ONLY"
            return True
        return False

    def run(self, request: Dict[str, Any]) -> CentralServerResponse:
        route = request.get("route", "")
        if self._raw_detected(request):
            self.audit.append({
                "event_at": datetime.utcnow().isoformat(),
                "team_id": request.get("team_id",""),
                "event_type": "POLICY_BLOCK",
                "model_version": request.get("model_version",""),
                "policy_code": "RAW_FORBIDDEN",
                "data_digest16": request.get("data_digest16",""),
                "reason_code": "RAW_FORBIDDEN",
            })
            return CentralServerResponse(False, "POLICY_BLOCK", request.get("data_digest16",""), request.get("model_version",""), "RAW_FORBIDDEN", "RAW_FORBIDDEN", self.server_status == ServerStatus.SAFE_MODE.value)

        if self._block_in_safe_mode(route):
            return CentralServerResponse(False, "POLICY_BLOCK", digest16(route), request.get("model_version",""), "SAFE_MODE_READ_ONLY", "SAFE_MODE_ACTIVE", True)

        try:
            with self.egress_guard.patch_all():
                if route == EventType.INSIGHT_COLLECT.value:
                    insight = TeamInsight(**request["payload"])
                    res = self.collector.receive(insight)
                    self._persist_all()
                    return CentralServerResponse(res.ok, route, res.data_digest16, insight.model_version, "", res.error_code, False)
                if route == EventType.KB_UPDATE.value:
                    doc = EnterpriseKBDoc(**request["payload"])
                    res = self.kb.index_document(doc)
                    self._persist_all()
                    return CentralServerResponse(res.ok, route, digest16(res.doc_id), "", "", "", False)
                if route == EventType.LEARNING_TRIGGER.value:
                    teams = request["payload"]["team_ids"]
                    total = request["payload"]["total_count"]
                    job = self.learner.check_and_trigger(teams, total)
                    self._persist_all()
                    return CentralServerResponse(True, route, digest16(job.job_id if job else "none"), "", "", "", False)
                if route == EventType.MODEL_APPROVE.value:
                    payload = request["payload"]
                    rr = self.registry.approve(payload["version_id"], payload.get("approved_by","admin"), payload.get("approval_policy_version","policy-v1"), payload.get("approval_note_digest16","note"))
                    self._persist_all()
                    return CentralServerResponse(rr.ok, route, digest16(rr.version_id), rr.version_id, "", rr.error_code, False)
                if route == EventType.DEPLOY.value:
                    payload = request["payload"]
                    order = DeploymentOrder(**payload)
                    rr = self.deployer.deploy(order, safe_mode=self.server_status == ServerStatus.SAFE_MODE.value)
                    if not rr.ok:
                        self.deploy_block_count += 1
                    self._persist_all()
                    return CentralServerResponse(rr.ok, route, digest16(rr.order_id), rr.model_version_id, "", rr.error_code, self.server_status == ServerStatus.SAFE_MODE.value)
                raise ValueError("UNKNOWN_ROUTE")
        except EgressBlockedError:
            self.egress_block_count += 1
            self._persist_all()
            return CentralServerResponse(False, "POLICY_BLOCK", digest16(route), "", "EGRESS_BLOCKED", "EGRESS_BLOCKED", self.server_status == ServerStatus.SAFE_MODE.value)
        except Exception as exc:
            self.enter_safe_mode(type(exc).__name__)
            self._persist_all()
            return CentralServerResponse(False, "POLICY_BLOCK", digest16(route), "", "SAFE_MODE_READ_ONLY", type(exc).__name__, True)

    def build_report(self):
        latest_approved = self.registry.get_latest_approved()
        latest_version = latest_approved.version_id if latest_approved else (max(self.registry.versions.keys()) if self.registry.versions else "")
        report = {
            "schema_version": SCHEMA_VERSION,
            "execution_mode": "offline-demo",
            "server_status": self.server_status,
            "safe_mode_entered": self.safe_mode_entered,
            "safe_mode_reason": self.safe_mode_reason,
            "safe_mode_entered_at": self.safe_mode_entered_at,
            "safe_mode_exit_condition": "manual_reset or restart",
            "safe_mode_block_count": self.safe_mode_block_count,
            "safe_mode_last_reason": self.safe_mode_last_reason,
            "learning_jobs_count": len(self.learner.jobs),
            "latest_model_version": latest_version,
            "approved_version_count": len([v for v in self.registry.versions.values() if v.status == ModelStatus.APPROVED.value]),
            "pending_version_count": len([v for v in self.registry.versions.values() if v.status == ModelStatus.PENDING.value]),
            "deploy_block_count": self.deploy_block_count,
            "egress_block_count": self.egress_block_count,
            "product_ready_reason": "offline_control_plane_ready",
        }
        self.report_writer.write_report(self.tmp_dir / "central_server_report.json", report)
        return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-demo", action="store_true")
    parser.add_argument("--json-out", type=str, default="")
    parser.add_argument("--state-dir", type=str, default="")
    args = parser.parse_args()
    base_dir = Path(args.json_out).resolve().parent.parent if args.json_out else Path.cwd()
    server = CentralServer(base_dir)
    if args.offline_demo:
        from .central_contracts import EventType
        server.run({"route": EventType.INSIGHT_COLLECT.value, "payload": {
            "team_id":"team-a","insight_type":"KB_UPDATE","data_digest16":"d1","record_count":5000,"timestamp":datetime.utcnow().isoformat(),"model_version":"m0","source_server_id":"ts1"
        }})
        job = server.learner.jobs[0]
        mv = server.learner.complete_job(job.job_id)
        server.registry.approve(mv.version_id)
        server.run({"route": EventType.DEPLOY.value, "payload": {
            "order_id":"order-1","model_version_id":mv.version_id,"target_type":"ALL_TEAMS","target_ids":["team-a"],"issued_at":datetime.utcnow().isoformat(),"status":"CREATED","requested_by":"admin","requested_at":datetime.utcnow().isoformat(),"deploy_order_digest16":"d-order","rollback_required_if":"post_deploy_regression"
        }})
        report = server.build_report()
        if args.json_out:
            server.report_writer.write_report(Path(args.json_out), report)
        print("CENTRAL_SERVER_OK=1")
        print(f"STATUS={server.server_status}")

if __name__ == "__main__":
    main()
