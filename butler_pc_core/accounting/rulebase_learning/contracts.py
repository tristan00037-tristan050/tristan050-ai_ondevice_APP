from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material

SCHEMA_VERSION = "verified_rule_base_candidate.v1"
LEARNING_SOURCE_TYPE = "verified_rule_base"
TARGET_BOX5_SELF_TRANSFER = "box5_self_transfer_guard"
CANDIDATE_KIND_DETERMINISTIC_RULE_PATCH = "deterministic_rule_patch"
RETENTION_CLASS = "audit_digest_only"

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
APPROVED_RULE_TOKEN_REF_RE = re.compile(r"^(vault|keyring)://[^\s]{1,240}$")

FORBIDDEN_CANDIDATE_FIELDS = {
    "raw_memo",
    "filename",
    "md_content",
    "transaction_text",
    "customer_name",
    "account_number_plain",
    "amount_plain",
    "file_path",
    "prompt",
    "response_text",
}


class VerifiedRuleBaseContractError(ValueError):
    pass


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / "schemas" / "box5" / "verified_rule_base_candidate_v1.schema.json"


def _schema() -> dict[str, Any]:
    return json.loads(_schema_path().read_text(encoding="utf-8"))


def _validator() -> Draft7Validator:
    return Draft7Validator(_schema())


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def is_approved_rule_token_ref(value: object) -> bool:
    return isinstance(value, str) and bool(APPROVED_RULE_TOKEN_REF_RE.fullmatch(value))


def _assert_forbidden_keys_absent(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) in FORBIDDEN_CANDIDATE_FIELDS:
                raise VerifiedRuleBaseContractError("FORBIDDEN_RAW_FIELD")
            _assert_forbidden_keys_absent(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_forbidden_keys_absent(item)


def validate_candidate_dict(candidate: dict[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(candidate)
    try:
        _validator().validate(copied)
    except ValidationError as exc:
        raise VerifiedRuleBaseContractError(f"SCHEMA_INVALID:{exc.path}") from None
    _assert_forbidden_keys_absent(copied)
    try:
        assert_no_raw_or_secret_material(copied)
    except ValueError as exc:
        raise VerifiedRuleBaseContractError(str(exc)) from None
    return copied


@dataclass(frozen=True)
class VerifiedRuleBaseCandidate:
    approved_rule_token_ref: str
    approved_rule_token_digest: str
    group_a_report_digest: str
    source_usage_log_ids: list[str]
    expected_effect_digest: str
    candidate_id: str = field(default_factory=lambda: "vrb-" + uuid.uuid4().hex)
    proposed_diff_digest: str | None = None
    tests_to_run: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "learning_source_type": LEARNING_SOURCE_TYPE,
            "target": TARGET_BOX5_SELF_TRANSFER,
            "candidate_kind": CANDIDATE_KIND_DETERMINISTIC_RULE_PATCH,
            "rule_patch_created": False,
            "model_training": False,
            "peft_training": False,
            "raw_text_logged": False,
            "external_send_zero": True,
            "group_a_verified": True,
            "human_review_required": True,
            "auto_apply_to_runtime": False,
            "retention_class": RETENTION_CLASS,
            "policy_decision": "allow",
            "approved_rule_token_ref": self.approved_rule_token_ref,
            "approved_rule_token_digest": self.approved_rule_token_digest,
            "group_a_report_digest": self.group_a_report_digest,
            "source_usage_log_ids": list(self.source_usage_log_ids),
            "expected_effect_digest": self.expected_effect_digest,
        }
        if self.proposed_diff_digest is not None:
            data["proposed_diff_digest"] = self.proposed_diff_digest
        if self.tests_to_run:
            data["tests_to_run"] = list(self.tests_to_run)
        return validate_candidate_dict(data)


def make_candidate(
    *,
    approved_rule_token_ref: str,
    approved_rule_token_digest: str,
    group_a_report_digest: str,
    source_usage_log_ids: list[str],
    expected_effect_digest: str,
    candidate_id: str | None = None,
    proposed_diff_digest: str | None = None,
    tests_to_run: list[str] | None = None,
) -> dict[str, Any]:
    candidate = VerifiedRuleBaseCandidate(
        candidate_id=candidate_id or "vrb-" + uuid.uuid4().hex,
        approved_rule_token_ref=approved_rule_token_ref,
        approved_rule_token_digest=approved_rule_token_digest,
        group_a_report_digest=group_a_report_digest,
        source_usage_log_ids=list(source_usage_log_ids),
        expected_effect_digest=expected_effect_digest,
        proposed_diff_digest=proposed_diff_digest,
        tests_to_run=list(tests_to_run or []),
    )
    return candidate.to_dict()
