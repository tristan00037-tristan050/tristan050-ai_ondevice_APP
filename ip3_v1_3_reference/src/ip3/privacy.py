from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, List, Mapping

FORBIDDEN_RAW_KEYS = {
    "raw_content", "raw_prompt", "prompt", "raw_user_text", "user_text", "raw_log", "raw_path",
    "original_text", "training_input_text", "transformed_text", "hostname", "ip_address", "device_id"
}
# keys that may legitimately include a digest or flag name, not raw value
ALLOWED_KEY_EXCEPTIONS = {
    "hostname_digest", "device_id_digest", "raw_hostname_recorded", "raw_ip_recorded", "raw_device_id_recorded",
    "raw_prompt_recorded", "raw_user_text_recorded", "raw_log_recorded", "raw_path_recorded"
}

HEX_RE = re.compile(r"^[0-9a-f]{64}$")

def sha256_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def walk_forbidden_keys(obj: Any, path: str = "$", errors: List[str] | None = None) -> List[str]:
    if errors is None:
        errors = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_s = str(key)
            key_l = key_s.lower()
            if key_l in FORBIDDEN_RAW_KEYS and key_l not in ALLOWED_KEY_EXCEPTIONS:
                errors.append(f"forbidden raw key at {path}.{key_s}")
            walk_forbidden_keys(value, f"{path}.{key_s}", errors)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            walk_forbidden_keys(value, f"{path}[{idx}]", errors)
    return errors


def assert_digest(value: str, label: str = "digest") -> None:
    if not isinstance(value, str) or not HEX_RE.match(value):
        raise ValueError(f"{label} must be sha256 hex digest")
