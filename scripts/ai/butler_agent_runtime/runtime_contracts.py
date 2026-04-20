from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    DIALOGUE = 'dialogue'
    SUMMARIZE = 'summarize'
    REWRITE = 'rewrite'
    TOOL_CALL = 'tool_call'
    POLICY_SENSITIVE = 'policy_sensitive'
    RETRIEVAL_TRANSFORM = 'retrieval_transform'


@dataclass
class DeviceProfile:
    ok: int
    ram_avail_gb: float
    cpu_cores: int
    cpu_usage_pct: float
    battery_pct: int | None
    battery_plugged: int | None
    cuda_available: int
    vram_avail_gb: float
    thermal_state: str
    recommendation: str
    probe_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelSpec:
    name: str
    model_path: str
    adapter_path: str | None
    quant_mode: str
    runtime_backend: str
    selected_reason: str
    fallback_used: int = 0
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyConfig:
    policy_id: str
    allow_tool_call: bool = True
    allow_retrieval_transform: bool = True
    offline_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    has_sensitive: bool
    hit_types: list[str]
    masked_text: str
    digest16: str
    masked_preview_len: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BlockResult:
    blocked: bool
    code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskDecision:
    task: str
    reason_code: str
    fallback_to_dialogue: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionRecord:
    session_id: str
    user_id: str
    device_id: str
    created_at: str
    last_turn_at: str
    policy_id: str
    selected_model: str
    route_reason: str
    closed: bool = False
    turns: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoadMeta:
    loaded: int
    backend: str
    quant_mode: str
    device: str
    fallback_used: int = 0
    fallback_reason: str = ''
    primary_selected: str = ''
    selected: str = ''
    error: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResponse:
    ok: bool
    task: str
    selected_model: str
    response_digest16: str
    response_len: int
    policy_code: str
    fallback_used: int
    route_reason: str
    blocked: bool
    sensitive_hit_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeReport:
    schema_version: str
    generated_at: str
    execution_mode: str
    effective_backend: str
    quant_mode: str
    fallback_used: int
    fallback_reason: str
    product_ready: int
    selected_model: str
    route_reason: str
    audit_path: str
    response_digest16: str
    fail_codes: list[str] = field(default_factory=list)
    checks: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
