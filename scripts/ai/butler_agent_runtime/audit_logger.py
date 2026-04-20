from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_path: str | Path = 'tmp/agent_runtime_audit.jsonl'):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **kwargs: Any) -> None:
        payload = {
            'event_at': datetime.now(timezone.utc).isoformat(),
            'session_id': kwargs.get('session_id', ''),
            'device_id': kwargs.get('device_id', ''),
            'selected_model': kwargs.get('selected_model', ''),
            'route_reason': kwargs.get('route_reason', ''),
            'policy_id': kwargs.get('policy_id', ''),
            'event_code': kwargs.get('event_code', ''),
            'input_digest16': kwargs.get('input_digest16', ''),
            'output_digest16': kwargs.get('output_digest16', ''),
            'blocked': int(bool(kwargs.get('blocked', False))),
            'backend': kwargs.get('backend', ''),
            'fallback_used': int(kwargs.get('fallback_used', 0) or 0),
            'fallback_reason': kwargs.get('fallback_reason', ''),
            'sensitive_hit_types': kwargs.get('sensitive_hit_types', []),
            'error_code': kwargs.get('error_code', ''),
            'message': kwargs.get('message', ''),
        }
        with self.log_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(payload, ensure_ascii=False) + '\n')
