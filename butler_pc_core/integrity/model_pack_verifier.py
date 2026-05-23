from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from butler_pc_core.fail_class import FailClass

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_DETAIL_KEYS = {"expected_sha", "actual_sha", "file_size", "manifest_sha", "reason"}
_FORBIDDEN_DETAIL_KEYS = {"raw_file_content", "raw_model_bytes", "raw_tokenizer_text", "raw_adapter_bytes"}


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    fail_class: Optional[FailClass]
    details: dict[str, Any]
    verified_at: str
    target_path: Optional[str] = None


class ModelPackVerifier:
    def __init__(self, base_dir: Path, allow_symlinks: bool = False):
        self.base_dir = base_dir.resolve()
        self.allow_symlinks = allow_symlinks

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
        if any(key in details for key in _FORBIDDEN_DETAIL_KEYS):
            raise ValueError("forbidden raw detail key present")
        return {key: value for key, value in details.items() if key in _ALLOWED_DETAIL_KEYS}

    def _result(self, ok: bool, fail_class: Optional[FailClass], details: dict[str, Any], target_path: Optional[Path] = None) -> VerifyResult:
        return VerifyResult(
            ok=ok,
            fail_class=fail_class,
            details=self._sanitize_details(details),
            verified_at=self._now(),
            target_path=str(target_path) if target_path else None,
        )

    def _resolve_target(self, candidate: str | Path, manifest_dir: Optional[Path] = None) -> Path:
        raw = Path(candidate)
        base = (manifest_dir or self.base_dir).resolve()
        pre_resolve = raw if raw.is_absolute() else base / raw
        if pre_resolve.is_symlink() and not self.allow_symlinks:
            raise ValueError("symlink blocked")
        resolved = pre_resolve.resolve()
        try:
            resolved.relative_to(self.base_dir)
        except ValueError:
            raise ValueError("path traversal outside base_dir")
        return resolved

    def load_manifest(self, manifest_path: Path) -> tuple[Optional[dict[str, Any]], VerifyResult]:
        try:
            target = self._resolve_target(manifest_path, manifest_path.parent)
            if not target.exists():
                return None, self._result(False, FailClass.MODEL_PACK_MISSING, {"reason": "manifest_missing"}, target)
            if not target.is_file():
                return None, self._result(False, FailClass.MODEL_PACK_MISSING, {"reason": "manifest_not_file"}, target)
            raw = target.read_bytes()
            manifest_sha = hashlib.sha256(raw).hexdigest()
            parsed = json.loads(raw.decode("utf-8"))
            return parsed, self._result(True, None, {"manifest_sha": manifest_sha}, target)
        except json.JSONDecodeError:
            return None, self._result(False, FailClass.MANIFEST_SHA_MISMATCH, {"reason": "manifest_json_invalid"}, manifest_path)
        except ValueError as exc:
            return None, self._result(False, FailClass.SIGNATURE_INVALID, {"reason": str(exc)}, manifest_path)
        except PermissionError:
            return None, self._result(False, FailClass.MODEL_PACK_MISSING, {"reason": "permission_denied"}, manifest_path)
        except IsADirectoryError:
            return None, self._result(False, FailClass.MODEL_PACK_MISSING, {"reason": "is_directory"}, manifest_path)

    def verify_file(self, path_value: str | Path, expected_sha: str, fail_class_on_mismatch: FailClass, manifest_dir: Optional[Path] = None) -> VerifyResult:
        if not _HEX64.fullmatch(expected_sha):
            return self._result(False, FailClass.SIGNATURE_INVALID, {"expected_sha": expected_sha, "reason": "expected_sha_not_lower_hex64"})
        try:
            target = self._resolve_target(path_value, manifest_dir)
            if not target.exists():
                return self._result(False, FailClass.MODEL_PACK_MISSING, {"reason": "file_missing"}, target)
            if not target.is_file():
                return self._result(False, FailClass.MODEL_PACK_MISSING, {"reason": "not_file"}, target)
            actual_sha = self._compute_sha256(target)
            file_size = target.stat().st_size
            if actual_sha != expected_sha:
                return self._result(False, fail_class_on_mismatch, {"expected_sha": expected_sha, "actual_sha": actual_sha, "file_size": file_size, "reason": "sha_mismatch"}, target)
            return self._result(True, None, {"expected_sha": expected_sha, "actual_sha": actual_sha, "file_size": file_size}, target)
        except ValueError as exc:
            return self._result(False, FailClass.SIGNATURE_INVALID, {"reason": str(exc)})
        except FileNotFoundError:
            return self._result(False, FailClass.MODEL_PACK_MISSING, {"expected_sha": expected_sha, "reason": "file_not_found"})
        except PermissionError:
            return self._result(False, FailClass.MODEL_PACK_MISSING, {"expected_sha": expected_sha, "reason": "permission_denied"})
        except IsADirectoryError:
            return self._result(False, FailClass.MODEL_PACK_MISSING, {"expected_sha": expected_sha, "reason": "is_directory"})

    def verify_all(self, manifest_dict: dict[str, Any], manifest_dir: Optional[Path] = None) -> VerifyResult:
        base = (manifest_dir or self.base_dir).resolve()
        targets = [
            ("model_path", "model_sha256", FailClass.MODEL_PACK_SHA_MISMATCH),
            ("adapter_path", "adapter_sha256", FailClass.ADAPTER_SHA_MISMATCH),
            ("tokenizer_path", "tokenizer_sha256", FailClass.TOKENIZER_SHA_MISMATCH),
        ]
        for path_key, sha_key, fail_class in targets:
            if path_key not in manifest_dict or sha_key not in manifest_dict:
                continue
            result = self.verify_file(manifest_dict[path_key], manifest_dict[sha_key], fail_class, base)
            if not result.ok:
                return result
        return self._result(True, None, {"reason": "all_targets_verified"})
