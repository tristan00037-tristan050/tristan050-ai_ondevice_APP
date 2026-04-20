from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from .runtime_contracts import SessionRecord

TTL_MINUTES = 30


def _digest16(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


class SessionManager:
    def __init__(self, ttl_minutes: int = TTL_MINUTES):
        self.ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, SessionRecord] = {}

    def create_session(self, user_id: str, device_id: str, policy_id: str, selected_model: str, route_reason: str) -> SessionRecord:
        now = datetime.now(timezone.utc).isoformat()
        rec = SessionRecord(
            session_id=uuid.uuid4().hex[:16],
            user_id=user_id,
            device_id=device_id,
            created_at=now,
            last_turn_at=now,
            policy_id=policy_id,
            selected_model=selected_model,
            route_reason=route_reason,
        )
        self._sessions[rec.session_id] = rec
        return rec

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    def append_turn(self, session_id: str, role: str, text: str, task: str = '', selected_model: str = '') -> None:
        rec = self._sessions[session_id]
        if rec.closed:
            raise RuntimeError('session_closed')
        now = datetime.now(timezone.utc).isoformat()
        rec.last_turn_at = now
        rec.turns.append({'role': role, 'digest16': _digest16(text), 'text_len': len(text), 'timestamp': now, 'task': task, 'selected_model': selected_model})

    def close_session(self, session_id: str) -> None:
        self._sessions[session_id].closed = True

    def expire_session(self, session_id: str) -> bool:
        rec = self._sessions[session_id]
        last = datetime.fromisoformat(rec.last_turn_at)
        if datetime.now(timezone.utc) - last > self.ttl:
            rec.closed = True
            return True
        return False

    def summarize_session_state(self, session_id: str) -> dict[str, Any]:
        rec = self._sessions[session_id]
        return {
            'session_id': rec.session_id,
            'turn_count': len(rec.turns),
            'last_model': rec.selected_model,
            'last_route_reason': rec.route_reason,
            'closed': rec.closed,
        }
