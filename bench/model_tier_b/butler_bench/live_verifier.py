from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from .canonical import canonical_sha256, sha256_file
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = {
    "schema_version", "module_sha256", "dlp_symbol", "grounding_symbol",
    "quality_symbol", "manifest_sha256",
}


class LiveSemanticVerifier:
    __slots__ = ("_manifest", "_dlp", "_grounding", "_quality")

    def __init__(self, *_: object, **__: object) -> None:
        raise GateError(FailClass.INDEPENDENT_VERIFY, "CALLER_SUPPLIED_VALIDATOR_FORBIDDEN", exit_code=ExitCode.EVIDENCE)

    @classmethod
    def from_approved_artifact(
        cls,
        *,
        module_path: Path,
        manifest: dict[str, Any],
        producer_root: Path,
    ) -> "LiveSemanticVerifier":
        if set(manifest) != _MANIFEST_KEYS or manifest["schema_version"] != "butler.model-tier-b.evaluator-manifest.v2.8":
            _block("EVALUATOR_MANIFEST_KEYS", ExitCode.SCHEMA)
        unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if not isinstance(manifest["manifest_sha256"], str) or canonical_sha256(unsigned) != manifest["manifest_sha256"]:
            _block("EVALUATOR_MANIFEST_DIGEST", ExitCode.DIGEST)
        if not isinstance(manifest["module_sha256"], str) or not _SHA256.fullmatch(manifest["module_sha256"]):
            _block("EVALUATOR_MODULE_DIGEST", ExitCode.SCHEMA)
        module_path = module_path.resolve(strict=True)
        producer_root = producer_root.resolve(strict=True)
        if module_path == producer_root or producer_root in module_path.parents:
            _block("EVALUATOR_INSIDE_PRODUCER")
        if sha256_file(module_path) != manifest["module_sha256"]:
            _block("EVALUATOR_ARTIFACT_MISMATCH", ExitCode.DIGEST)
        module = _load_verified_module(module_path, manifest["module_sha256"])
        functions = []
        for key in ("dlp_symbol", "grounding_symbol", "quality_symbol"):
            symbol = manifest[key]
            if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", symbol):
                _block("EVALUATOR_SYMBOL", ExitCode.SCHEMA)
            function = getattr(module, symbol, None)
            if not callable(function) or getattr(function, "__module__", None) != module.__name__:
                _block("EVALUATOR_CALLABLE_OWNER")
            functions.append(function)
        instance = object.__new__(cls)
        instance._manifest = manifest
        instance._dlp, instance._grounding, instance._quality = functions
        return instance

    def evaluate(self, output_view: memoryview, *, fixture_id: str, task_id: str, quality_floor_scaled: int) -> dict[str, Any]:
        if output_view.readonly is not True or not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", fixture_id) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", task_id):
            _block("LIVE_VERIFIER_INPUT", ExitCode.SCHEMA)
        if type(quality_floor_scaled) is not int:
            _block("QUALITY_FLOOR", ExitCode.SCHEMA)
        dlp_passed = self._dlp(output_view)
        grounding_passed = self._grounding(output_view, fixture_id)
        score = self._quality(output_view, fixture_id)
        if type(dlp_passed) is not bool or type(grounding_passed) is not bool or type(score) is not int:
            _block("EVALUATOR_RETURN_TYPE", ExitCode.SCHEMA)
        payload = {
            "schema_version": "butler.model-tier-b.live-semantic-verify.v2.8",
            "fixture_id": fixture_id,
            "task_id": task_id,
            "evaluator_manifest_sha256": self._manifest["manifest_sha256"],
            "evaluator_module_sha256": self._manifest["module_sha256"],
            "dlp_passed": dlp_passed,
            "grounding_passed": grounding_passed,
            "quality_score_scaled": score,
            "quality_floor_scaled": quality_floor_scaled,
            "quality_passed": score >= quality_floor_scaled,
        }
        payload["semantic_receipt_sha256"] = canonical_sha256(payload)
        return payload


def _load_verified_module(path: Path, digest: str) -> ModuleType:
    name = f"butler_verified_evaluator_{digest[:16]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        _block("EVALUATOR_IMPORT")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        _block("EVALUATOR_IMPORT")
    return module


def _block(detail: str, exit_code: ExitCode = ExitCode.EVIDENCE) -> None:
    raise GateError(FailClass.INDEPENDENT_VERIFY, detail, exit_code=exit_code)
