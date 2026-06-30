from __future__ import annotations

import copy
import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material

from .contracts import sha256_text, validate_candidate_dict

ALLOWED_PATCH_TARGETS = frozenset(
    {
        "butler_pc_core/company_profile/matcher.py",
        "tests/accounting/test_self_transfer_guard.py",
        "butler_pc_core/accounting/rulebase_learning/rule_token_config.json",
    }
)

DISALLOWED_PATCH_PREFIXES = (
    "butler_pc_core/connect_loop/",
    "butler_pc_core/prompts/",
    "butler_pc_core/inference/",
    "butler_pc_core/output_safety/",
    "butler_pc_core/cards/",
    "butler_pc_core/sidecar/",
    "butler-desktop/",
    "models/",
    "schemas/connect_loop/",
)


class RulePatchDiffError(ValueError):
    pass


@dataclass(frozen=True)
class RulePatchDiff:
    changed_paths: tuple[str, ...]
    diff_text: str
    diff_digest: str

    def to_manifest_fragment(self) -> dict[str, Any]:
        return {
            "changed_paths": list(self.changed_paths),
            "proposed_diff_digest": self.diff_digest,
        }


def _normalize_relative_path(path: str | Path) -> str:
    value = Path(path).as_posix().lstrip("/")
    if ".." in Path(value).parts:
        raise RulePatchDiffError("PATCH_PATH_TRAVERSAL_FORBIDDEN")
    return value


def assert_patch_target_allowed(path: str | Path) -> str:
    normalized = _normalize_relative_path(path)
    if any(normalized.startswith(prefix) for prefix in DISALLOWED_PATCH_PREFIXES):
        raise RulePatchDiffError("PATCH_TARGET_FORBIDDEN")
    if normalized not in ALLOWED_PATCH_TARGETS:
        raise RulePatchDiffError("PATCH_TARGET_NOT_ALLOWLISTED")
    return normalized


def build_unified_diff(
    repo_root: str | Path,
    replacement_text_by_path: Mapping[str, str],
    *,
    expected_current_digest_by_path: Mapping[str, str],
) -> RulePatchDiff:
    repo = Path(repo_root)
    pieces: list[str] = []
    changed: list[str] = []

    for raw_path in sorted(replacement_text_by_path):
        rel_path = assert_patch_target_allowed(raw_path)
        new_text = replacement_text_by_path[raw_path]
        try:
            assert_no_raw_or_secret_material({"path": rel_path, "new_text": new_text})
        except ValueError as exc:
            raise RulePatchDiffError("RAW_OR_SECRET_MATERIAL_FORBIDDEN") from exc

        old_path = repo / rel_path
        old_text = old_path.read_text(encoding="utf-8") if old_path.exists() else ""
        expected_current_digest = expected_current_digest_by_path.get(rel_path)
        if expected_current_digest is None:
            raise RulePatchDiffError("PATCH_TARGET_SHA_REQUIRED")
        if expected_current_digest != sha256_text(old_text):
            raise RulePatchDiffError("PATCH_TARGET_SHA_MISMATCH")
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        if old_lines == new_lines:
            continue
        changed.append(rel_path)
        pieces.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="",
            )
        )

    if not changed:
        raise RulePatchDiffError("EMPTY_PATCH_FORBIDDEN")

    diff_text = "\n".join(pieces)
    try:
        assert_no_raw_or_secret_material({"changed_paths": changed, "diff_text": diff_text})
    except ValueError as exc:
        raise RulePatchDiffError("RAW_OR_SECRET_MATERIAL_FORBIDDEN") from exc
    return RulePatchDiff(tuple(changed), diff_text, sha256_text(diff_text))


def build_pr_candidate_manifest(
    *,
    candidate: dict[str, Any],
    rule_patch_diff: RulePatchDiff,
    base_sha: str,
    head_sha: str,
    tests_to_run: list[str] | None = None,
) -> dict[str, Any]:
    safe_candidate = validate_candidate_dict(candidate)
    manifest = {
        "manifest_version": "box5_rule_patch_pr_candidate.v1",
        "candidate_id": safe_candidate["candidate_id"],
        "learning_source_type": safe_candidate["learning_source_type"],
        "target": safe_candidate["target"],
        "human_review_required": True,
        "auto_apply_to_runtime": False,
        "rule_patch_created": True,
        "model_training": False,
        "peft_training": False,
        "raw_text_logged": False,
        "external_send_zero": True,
        "retention_class": safe_candidate["retention_class"],
        "base_sha": base_sha,
        "head_sha": head_sha,
        "approved_rule_token_digest": safe_candidate["approved_rule_token_digest"],
        "group_a_report_digest": safe_candidate["group_a_report_digest"],
        "source_usage_log_ids": list(safe_candidate["source_usage_log_ids"]),
        "expected_effect_digest": safe_candidate["expected_effect_digest"],
        "changed_paths": list(rule_patch_diff.changed_paths),
        "proposed_diff_digest": rule_patch_diff.diff_digest,
        "tests_to_run": list(tests_to_run or safe_candidate.get("tests_to_run", [])),
    }
    try:
        assert_no_raw_or_secret_material(manifest)
    except ValueError as exc:
        raise RulePatchDiffError("RAW_OR_SECRET_MATERIAL_FORBIDDEN") from exc
    return copy.deepcopy(manifest)


def manifest_digest(manifest: dict[str, Any]) -> str:
    try:
        assert_no_raw_or_secret_material(manifest)
    except ValueError as exc:
        raise RulePatchDiffError("RAW_OR_SECRET_MATERIAL_FORBIDDEN") from exc
    return sha256_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
