from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime

SCHEMA_VERSION = "central_server_v3"

class InsightType(str, Enum):
    FINETUNE_TRIGGER = "FINETUNE_TRIGGER"
    KB_UPDATE = "KB_UPDATE"
    COVERAGE_REPORT = "COVERAGE_REPORT"
    MODEL_FEEDBACK = "MODEL_FEEDBACK"

class ModelStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    DEPRECATED = "DEPRECATED"

class DeployTarget(str, Enum):
    ALL_TEAMS = "ALL_TEAMS"
    SPECIFIC_TEAMS = "SPECIFIC_TEAMS"
    ALL_DEVICES = "ALL_DEVICES"
    SPECIFIC_DEVICES = "SPECIFIC_DEVICES"

class ServerStatus(str, Enum):
    NORMAL = "NORMAL"
    SAFE_MODE = "SAFE_MODE"
    DEGRADED = "DEGRADED"

class EventType(str, Enum):
    INSIGHT_COLLECT = "INSIGHT_COLLECT"
    KB_UPDATE = "KB_UPDATE"
    LEARNING_TRIGGER = "LEARNING_TRIGGER"
    MODEL_APPROVE = "MODEL_APPROVE"
    DEPLOY = "DEPLOY"
    AUDIT = "AUDIT"
    POLICY_BLOCK = "POLICY_BLOCK"

class AccessLevel(str, Enum):
    PUBLIC = "PUBLIC"
    TEAM = "TEAM"
    DEPT = "DEPT"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"

@dataclass
class TeamInsight:
    team_id: str
    insight_type: str
    data_digest16: str
    record_count: int
    timestamp: str
    model_version: str
    source_server_id: str

@dataclass
class EnterpriseKBDoc:
    doc_id: str
    title_digest16: str
    summary: str
    tags: List[str]
    team_id: str
    version: int
    access_level: str
    created_at: str
    lineage_id: str

@dataclass
class LearningJob:
    job_id: str
    trigger_reason: str
    team_ids: List[str]
    data_digest16: str
    created_at: str
    status: str
    base_model_version: str
    eval_score: float = 0.0

@dataclass
class ModelVersion:
    version_id: str
    model_path_digest: str
    trained_at: str
    status: str
    eval_score: float
    deploy_approved: int
    source_job_id: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    approval_policy_version: Optional[str] = None
    approval_note_digest16: Optional[str] = None
    rollback_required_if: Optional[str] = None

@dataclass
class DeploymentOrder:
    order_id: str
    model_version_id: str
    target_type: str
    target_ids: List[str]
    issued_at: str
    status: str
    requested_by: str
    requested_at: Optional[str] = None
    deploy_order_digest16: Optional[str] = None
    rollback_required_if: Optional[str] = None

@dataclass
class CentralServerResponse:
    ok: bool
    event_type: str
    result_digest16: str
    model_version: str
    policy_code: str
    error_code: str
    safe_mode: bool

@dataclass
class CollectResult:
    ok: bool
    team_id: str
    count: int
    data_digest16: str
    error_code: str = ""

@dataclass
class IndexResult:
    ok: bool
    doc_id: str
    indexed_count: int
    error_code: str = ""

@dataclass
class RegistryResult:
    ok: bool
    version_id: str
    status: str
    error_code: str = ""

@dataclass
class DeployResult:
    ok: bool
    order_id: str
    model_version_id: str
    status: str
    error_code: str = ""

@dataclass
class AuditEntry:
    event_at: str
    team_id: str
    event_type: str
    model_version: str
    policy_code: str
    data_digest16: str
    reason_code: str
    approved_by: Optional[str] = None
    deploy_order_digest16: Optional[str] = None
