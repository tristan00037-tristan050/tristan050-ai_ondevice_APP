from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping

from .data_collector import DataCollector
from .egress_guard import EgressBlockedError, EgressGuard, EgressPolicyGuard
from .finetune_trigger import FinetuneTrigger
from .knowledge_base import KnowledgeBase
from .policy_enforcer import PolicyEnforcer
from .rag_engine import RAGEngine
from .team_audit_logger import TeamAuditLogger
from .team_contracts import AccessLevel, DeviceMeta, EventType, RAGRequest, ServerStatus, TeamServerResponse, digest16, scan_for_raw_payload
from .team_persistence import PersistenceError, TeamPersistence


class TeamServer:
    def __init__(self, *, audit_path: str = "tmp/team_audit.jsonl", offline_only: bool = True, threshold: int = 1000, state_dir: str = "tmp/team_state") -> None:
        self.offline_only = offline_only
        self.persistence = TeamPersistence(state_dir=state_dir)
        self.audit_logger = TeamAuditLogger(audit_path)
        self.egress_guard = EgressGuard()
        self.egress_policy = EgressPolicyGuard()
        self.status = ServerStatus.NORMAL
        self.safe_mode_entered = False
        self.safe_mode_reason = ""
        self.safe_mode_entered_at: str | None = None
        self._persist_fail_count = 0
        self._route_fail_count = 0
        self._shutdown = False
        try:
            state = self.persistence.load_state()
            self.knowledge_base = KnowledgeBase(self.persistence)
            self.finetune_trigger = FinetuneTrigger(threshold=threshold, persistence=self.persistence)
            prior_status = (state.get("server_state", {}) or {}).get("status")
            if prior_status == ServerStatus.SAFE_MODE.value:
                self.status = ServerStatus.SAFE_MODE
                self.safe_mode_entered = True
                self.safe_mode_reason = (state.get("server_state", {}) or {}).get("safe_mode_reason", "restored")
                self.safe_mode_entered_at = (state.get("server_state", {}) or {}).get("safe_mode_entered_at")
        except PersistenceError:
            self.status = ServerStatus.SAFE_MODE
            self.safe_mode_entered = True
            self.safe_mode_reason = "SAFE_MODE_ENTERED_KB_CORRUPT"
            self.knowledge_base = KnowledgeBase(None)
            self.finetune_trigger = FinetuneTrigger(threshold=threshold, persistence=None)
        self.policy_enforcer = PolicyEnforcer(self.audit_logger)
        self.data_collector = DataCollector(self.knowledge_base, self.finetune_trigger, self.audit_logger)
        self.rag_engine = RAGEngine(self.knowledge_base, self.policy_enforcer)
        self._persist_server_state()

    def _server_state_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "safe_mode_entered": self.safe_mode_entered,
            "safe_mode_reason": self.safe_mode_reason,
            "safe_mode_entered_at": self.safe_mode_entered_at,
        }

    def _persist_server_state(self) -> None:
        try:
            state = self.persistence.load_state()
            self.persistence.save_state(
                kb_snapshot=state.get("kb_snapshot", {}),
                finetune_jobs=state.get("finetune_jobs", {}),
                coverage_stats=state.get("coverage_stats", {}),
                server_state=self._server_state_payload(),
            )
            self._persist_fail_count = 0
        except Exception:
            self._persist_fail_count += 1
            if self._persist_fail_count >= 3:
                self.set_safe_mode("SAFE_MODE_ENTERED_PERSIST_FAIL", persist=False)

    def graceful_shutdown(self) -> bool:
        self._shutdown = True
        return True

    def set_safe_mode(self, reason: str, persist: bool = True) -> None:
        if not self.safe_mode_entered:
            self.safe_mode_entered = True
        self.status = ServerStatus.SAFE_MODE
        self.safe_mode_reason = reason
        if self.safe_mode_entered_at is None:
            from .team_contracts import utcnow_iso
            self.safe_mode_entered_at = utcnow_iso()
        event = self.audit_logger.build_event(
            team_id="system",
            user_id="system",
            device_id="server",
            event_type="AUDIT",
            policy_id="policy-ai31-v4",
            data_digest16=digest16(reason),
            access_granted=False,
            reason_code=reason,
            error_code="SAFE_MODE_ACTIVE",
            selected_route="system",
            server_status=self.status.value,
            event_code=reason,
        )
        self.audit_logger.append(event)
        if persist:
            self._persist_server_state()

    def _response(self, ok: bool, event_type: str, team_id: str, policy_code: str, error_code: str = "") -> Dict[str, Any]:
        payload = TeamServerResponse(ok, event_type, team_id, digest16({"ok": ok, "event_type": event_type, "team": team_id, "policy": policy_code, "error": error_code}), policy_code, error_code)
        data = asdict(payload)
        data["status"] = self.status.value
        return data

    def _scan_raw(self, payload: Mapping[str, Any]) -> None:
        found, reason = scan_for_raw_payload(dict(payload))
        if found:
            raise ValueError(f"RAW_BLOCK:{reason}")

    def _maybe_safe_mode_block(self, team_id: str, user_id: str, device_id: str, route: str) -> Dict[str, Any] | None:
        if self.status != ServerStatus.SAFE_MODE:
            return None
        action = route if route != "rag_query" else "rag_query"
        decision = self.policy_enforcer.check(user_id, team_id, action, {"access_level": AccessLevel.TEAM.value}, {"role": "member", "device_id": device_id}, server_status=self.status)
        if route == "rag_query":
            return None
        return self._response(False, EventType.POLICY_BLOCK.value, team_id, decision.reason_code, "SAFE_MODE_ACTIVE")

    def run(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        if self._shutdown:
            return self._response(False, EventType.AUDIT.value, str(request.get("team_id", "unknown")), "SERVER_SHUTDOWN", "SHUTDOWN")
        req = dict(request)
        route = str(req.get("route", "collect")).lower()
        team_id = str(req.get("team_id", "unknown"))
        user_id = str(req.get("user_id", req.get("session_id", "unknown")))
        device_id = str(req.get("device_id", "unknown"))
        context = {"role": req.get("role", "member"), "dept": req.get("dept", "default"), "device_id": device_id}
        try:
            self._scan_raw(req)
            block_resp = self._maybe_safe_mode_block(team_id, user_id, device_id, route)
            if block_resp is not None:
                return block_resp
            destination = str(req.get("destination", "team-server-internal"))
            with self.egress_guard.patch_all():
                self.egress_policy.check_outbound(destination)
                if route == "collect":
                    decision = self.policy_enforcer.check(user_id, team_id, "collect", {"access_level": AccessLevel.TEAM.value}, context, server_status=self.status)
                    if not decision.allowed:
                        return self._response(False, EventType.POLICY_BLOCK.value, team_id, decision.reason_code, "POLICY")
                    meta = DeviceMeta(
                        device_id=device_id,
                        team_id=team_id,
                        session_id=str(req["session_id"]),
                        task=str(req["task"]),
                        input_digest16=str(req["input_digest16"]),
                        output_digest16=str(req["output_digest16"]),
                        selected_model=str(req["selected_model"]),
                        timestamp=str(req["timestamp"]),
                    )
                    result = self.data_collector.receive(meta)
                    self._scan_raw(asdict(result))
                    self._persist_server_state()
                    return self._response(result.accepted, EventType.COLLECT.value, team_id, digest16(asdict(result)), "")
                if route == "rag_query":
                    rag_req = RAGRequest(str(req["query_digest16"]), team_id, user_id, str(req.get("policy_id", "policy-ai31-v4")), int(req.get("top_k", 3)))
                    result = self.rag_engine.query(rag_req, context)
                    self._scan_raw(asdict(result))
                    event = self.audit_logger.build_event(
                        team_id=team_id,
                        user_id=user_id,
                        device_id=device_id,
                        event_type="RAG_QUERY",
                        policy_id=rag_req.policy_id,
                        data_digest16=digest16(asdict(result)),
                        access_granted=True,
                        selected_route="rag_query",
                        server_status=self.status.value,
                        access_level="TEAM",
                        event_code="RAG_QUERY_COMPLETED",
                    )
                    self.audit_logger.append(event)
                    self._persist_server_state()
                    return self._response(True, EventType.RAG_QUERY.value, team_id, digest16(asdict(result)), "")
                if route == "finetune_trigger":
                    decision = self.policy_enforcer.check(user_id, team_id, "finetune_trigger", {"access_level": AccessLevel.TEAM.value}, context, server_status=self.status)
                    if not decision.allowed:
                        return self._response(False, EventType.POLICY_BLOCK.value, team_id, decision.reason_code, "POLICY")
                    job = self.finetune_trigger.check_and_trigger(team_id, coverage_delta=len(self.knowledge_base.get_coverage(team_id).get("topics", {})))
                    payload = {"job_id": getattr(job, "job_id", "")}
                    self._scan_raw(payload)
                    self._persist_server_state()
                    return self._response(bool(job), EventType.FINETUNE_TRIGGER.value, team_id, digest16(payload), "")
                return self._response(False, EventType.POLICY_BLOCK.value, team_id, "UNKNOWN_ROUTE", "ROUTE")
        except EgressBlockedError:
            return self._response(False, EventType.POLICY_BLOCK.value, team_id, "EGRESS_BLOCKED", "EGRESS")
        except Exception:
            self._route_fail_count += 1
            if self._route_fail_count >= 5:
                self.set_safe_mode("SAFE_MODE_ENTERED_ROUTE_FAIL")
            else:
                self.set_safe_mode("SAFE_MODE_ENTERED_ROUTE_FAIL")
            return self._response(False, EventType.POLICY_BLOCK.value, team_id, "SAFE_MODE_READ_ONLY", "SAFE_MODE_ACTIVE")

    def offline_demo(self, json_out: str) -> Dict[str, Any]:
        collect_resp = self.run({
            "route": "collect",
            "destination": "team-server-internal",
            "device_id": "dev-alpha",
            "team_id": "team-red",
            "session_id": "sess-001",
            "task": "meeting_summary",
            "input_digest16": "a" * 16,
            "output_digest16": "b" * 16,
            "selected_model": "butler-edge-v2",
            "timestamp": "2026-04-20T00:00:00+00:00",
            "role": "member",
            "dept": "default",
        })
        rag_resp = self.run({
            "route": "rag_query",
            "destination": "team-server-internal",
            "team_id": "team-red",
            "user_id": "user-lead",
            "device_id": "dev-alpha",
            "query_digest16": "a" * 16,
            "policy_id": "policy-ai31-v4",
            "top_k": 3,
            "role": "lead",
            "dept": "research",
        })
        report = {
            "TEAM_SERVER_OK": 1 if collect_resp["ok"] and rag_resp["ok"] else 0,
            "status": self.status.value,
            "offline_only": self.offline_only,
            "safe_mode_entered": self.safe_mode_entered,
            "safe_mode_reason": self.safe_mode_reason,
            "safe_mode_entered_at": self.safe_mode_entered_at,
            "safe_mode_exit_condition": "manual_reset or restart",
            "collect": collect_resp,
            "rag": rag_resp,
            "metrics": self.rag_engine.metrics,
            "audit_events": self.audit_logger.count(),
            "model_versions": {"team-red": self.finetune_trigger.current_model_version("team-red")},
        }
        out = Path(json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-demo", action="store_true")
    parser.add_argument("--json-out", default="tmp/team_server_report.json")
    parser.add_argument("--state-dir", default="tmp/team_state")
    args = parser.parse_args()
    server = TeamServer(audit_path="tmp/team_audit.jsonl", state_dir=args.state_dir)
    if args.offline_demo:
        report = server.offline_demo(args.json_out)
        print(f"TEAM_SERVER_OK={report['TEAM_SERVER_OK']}")
        print(f"STATUS={report['status']}")
        return 0 if report["TEAM_SERVER_OK"] == 1 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
