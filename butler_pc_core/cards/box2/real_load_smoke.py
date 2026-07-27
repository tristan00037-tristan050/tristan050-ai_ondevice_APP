from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .adapter_loader import sha_mismatch_count, verify_asset_contracts
from .model_chain import REQUIRED_OUTPUT_FIELDS
from .runtime_loader import load_runtime


@dataclass
class LoadedBox2Helper3Chain:
    model: Any
    tokenizer: Any
    multi_lora_strategy: str
    def generate_text(self, text: str, *, max_new_tokens: int = 256) -> str:
        import torch
        encoded = self.tokenizer(text, return_tensors="pt")
        device = next(self.model.parameters()).device if hasattr(self.model, "parameters") else None
        if device is not None:
            encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            generated = self.model.generate(**encoded, max_new_tokens=max_new_tokens)
        return self.tokenizer.decode(generated[0], skip_special_tokens=True)
    def generate_case(self, case: Mapping[str, Any]) -> dict[str, str] | None:
        # Codex P1 (2026-05-26, PR #755): fabricating {field: "확인 필요"} on parse
        # failure scored 1.0 across all five evaluator metrics, letting the run pass
        # PASS_V2_FULL_METRIC without ever emitting a parseable rewrite. Surface
        # parse failure as None; evaluator._output_mapping coerces None to {} so
        # structure/coverage/format/semantic scores fail honestly.
        return parse_labeled_output(self.generate_text(build_digest_safe_eval_prompt(case), max_new_tokens=256))


class VerifiedBox2Backend(Protocol):
    def load(self) -> LoadedBox2Helper3Chain: ...


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _base_evidence(runtime: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "box2.helper3.real_load_smoke.v3", "stages_loaded": [], "runtime_packages": runtime.get("runtime_packages", {}), "multi_lora_strategy": "not_attempted", "inference_count": 0, "output_digest_only": True, "raw_output_saved": False, "external_send_zero": True, "raw_persistence_zero": True, "load_time_seconds": 0.0, "fail_class": runtime.get("fail_class"), "status": runtime.get("fail_class") or "NOT_RUN"}


def _write_json(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_digest_safe_eval_prompt(case: Mapping[str, Any]) -> str:
    fields = ", ".join(REQUIRED_OUTPUT_FIELDS)
    return "Butler Box 2 Helper 3 digest-safe evaluation. Do not invent names, dates, money, or contract terms. When source facts are unavailable, write 확인 필요. Case=" + str(case.get("case_id", "unknown")) + ". Return exactly these fields in this order: " + fields + "."


def parse_labeled_output(text: str) -> dict[str, str] | None:
    result: dict[str, str] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for field in REQUIRED_OUTPUT_FIELDS:
        value = None
        for line in lines:
            for prefix in (f"{field}:", f"{field}：", f"- {field}:", f"## {field}"):
                if line.startswith(prefix):
                    value = line[len(prefix):].strip(); break
            if value is not None:
                break
        if value is None:
            return None
        result[field] = value
    return result


def _probe_set_adapter_list(model: Any) -> bool:
    if not hasattr(model, "set_adapter"):
        return False
    try:
        model.set_adapter(["default", "helper_3"]); return True
    except Exception:
        return False


def _probe_weighted_adapter(model: Any) -> bool:
    if not hasattr(model, "add_weighted_adapter") or not hasattr(model, "set_adapter"):
        return False
    try:
        model.add_weighted_adapter(["default", "helper_3"], [1.0, 1.0], adapter_name="butler_helper3_weighted")
        model.set_adapter("butler_helper3_weighted"); return True
    except Exception:
        return False


def _activate_multi_lora(model: Any) -> str:
    if _probe_set_adapter_list(model):
        return "set_adapter_list"
    if _probe_weighted_adapter(model):
        return "weighted_adapter"
    return "unsupported"


def load_real_model_chain(
    backend: VerifiedBox2Backend | None = None,
) -> tuple[LoadedBox2Helper3Chain | None, dict[str, Any]]:
    runtime = load_runtime(); evidence = _base_evidence(runtime)
    if not runtime.get("runtime_available"):
        return None, evidence
    asset_checks = verify_asset_contracts(allow_missing=False)
    if sha_mismatch_count(asset_checks):
        evidence.update({"fail_class": "BLOCK_V3_SHA_MISMATCH", "status": "BLOCK_V3_SHA_MISMATCH"}); return None, evidence
    blocked = [name for name, check in asset_checks.items() if check.status.startswith("BLOCK_")]
    if blocked:
        evidence.update({"fail_class": "PARTIAL_DONE_V3_ASSET_LOAD_BLOCKED", "status": "PARTIAL_DONE_V3_ASSET_LOAD_BLOCKED", "blocked_assets": blocked}); return None, evidence
    started = time.monotonic(); stages: list[str] = []
    if backend is None:
        evidence.update(
            {
                "fail_class": "PARTIAL_DONE_V3_ASSET_LOAD_BLOCKED",
                "status": "PARTIAL_DONE_V3_ASSET_LOAD_BLOCKED",
                "blocked_assets": ["verified_multi_file_loader"],
            }
        )
        return None, evidence
    try:
        chain = backend.load()
        evidence.update(
            {
                "stages_loaded": ["verified_native_backend"],
                "multi_lora_strategy": chain.multi_lora_strategy,
                "fail_class": None,
                "status": "PASS_V3_REAL_LOAD_READY",
                "load_time_seconds": round(time.monotonic() - started, 6),
            }
        )
        return chain, evidence
    except Exception as exc:  # pragma: no cover
        evidence.update({"stages_loaded": stages, "fail_class": "PARTIAL_DONE_V3_REAL_LOAD_ERROR", "status": "PARTIAL_DONE_V3_REAL_LOAD_ERROR", "error_class": exc.__class__.__name__, "error_message_digest": "sha256:" + _sha256_text(str(exc)), "load_time_seconds": round(time.monotonic()-started, 6)})
        return None, evidence


def run_real_load_smoke(*, evidence_path: str | Path | None = None) -> dict[str, Any]:
    chain, evidence = load_real_model_chain()
    if chain is None:
        _write_json(evidence_path, evidence); return evidence
    try:
        text = chain.generate_text("외부 문서 요약 본문 example", max_new_tokens=50)
        evidence.update({"inference_count": 1, "output_digest": "sha256:" + _sha256_text(text), "output_digest_only": True, "raw_output_saved": False, "fail_class": None, "status": "PASS_V3_REAL_LOAD_SMOKE"})
    except Exception as exc:  # pragma: no cover
        evidence.update({"fail_class": "PARTIAL_DONE_V3_SMOKE_INFERENCE_ERROR", "status": "PARTIAL_DONE_V3_SMOKE_INFERENCE_ERROR", "error_class": exc.__class__.__name__, "error_message_digest": "sha256:" + _sha256_text(str(exc))})
    _write_json(evidence_path, evidence); return evidence
