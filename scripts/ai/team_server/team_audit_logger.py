from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

from .team_contracts import digest16, scan_for_raw_payload, utcnow_iso


class TeamAuditLogger:
    def __init__(self, path: str = "tmp/team_audit.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")
        self._ids = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    self._ids.add(json.loads(line).get("event_id"))
                except Exception:
                    continue

    def build_event(self, *, team_id: str, user_id: str, device_id: str, event_type: str, policy_id: str, data_digest16: str, access_granted: bool, reason_code: str = "", error_code: str = "", selected_route: str = "", server_status: str = "NORMAL", access_level: str = "TEAM", product_ready_reason: str = "", event_code: str = "") -> Dict[str, Any]:
        event = {
            "event_at": utcnow_iso(),
            "team_id": team_id,
            "user_id": user_id,
            "device_id": device_id,
            "event_type": event_type,
            "policy_id": policy_id,
            "data_digest16": data_digest16,
            "access_granted": access_granted,
            "reason_code": reason_code,
            "error_code": error_code,
            "selected_route": selected_route,
            "server_status": server_status,
            "access_level": access_level,
            "product_ready_reason": product_ready_reason,
            "event_code": event_code,
        }
        event["event_id"] = digest16(event)
        return event

    def append(self, event: Dict[str, Any]) -> bool:
        found, reason = scan_for_raw_payload(event)
        if found:
            raise ValueError(f"RAW_AUDIT_REJECT:{reason}")
        event_id = event.get("event_id")
        if event_id in self._ids:
            return True
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        self._ids.add(event_id)
        return True

    def tail(self, count: int = 10) -> List[Dict[str, Any]]:
        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [json.loads(line) for line in lines[-count:]]

    def count(self) -> int:
        return len(self._ids)
