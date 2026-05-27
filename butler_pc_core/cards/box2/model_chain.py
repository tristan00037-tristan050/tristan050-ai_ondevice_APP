from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .adapter_loader import DEFAULT_BASE_MODEL_PATH, DEFAULT_BUTLER_V3_GGUF_F16_PATH, DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH, DEFAULT_BUTLER_V3_LORA_PATH, DEFAULT_HANDOFF_ROOT, DEFAULT_HELPER_3_PATH, sha_mismatch_count, verify_asset_contracts
from .runtime_loader import detect_runtime_packages as detect_runtime_packages_dict
from .runtime_loader import load_runtime

REQUIRED_OUTPUT_FIELDS = ["제목", "발행일", "담당자", "핵심 내용", "합의사항", "금액/일정", "확인 필요", "최종 문안"]


@dataclass(frozen=True)
class RuntimePackageStatus:
    mlx_lm: bool
    peft: bool
    transformers: bool
    @property
    def all_available(self) -> bool:
        return self.mlx_lm and self.peft and self.transformers
    def to_dict(self) -> dict[str, bool]:
        return {"mlx_lm": self.mlx_lm, "peft": self.peft, "transformers": self.transformers}


@dataclass(frozen=True)
class ModelChainStatus:
    schema_version: str = "box2.helper3.model_chain_status.v3"
    default_handoff_root: str = DEFAULT_HANDOFF_ROOT
    base_model_path: str = DEFAULT_BASE_MODEL_PATH
    butler_v3_lora_path: str = DEFAULT_BUTLER_V3_LORA_PATH
    butler_v3_gguf_f16_path: str = DEFAULT_BUTLER_V3_GGUF_F16_PATH
    butler_v3_gguf_q4_k_m_path: str = DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH
    helper_3_path: str = DEFAULT_HELPER_3_PATH
    runtime_available: bool = False
    runtime_packages: dict[str, bool] = field(default_factory=dict)
    load_mode: str = "contract_only"
    status: str = "PARTIAL_DONE_V3_RUNTIME_INSTALL_FAILED"
    external_send: int = 0
    raw_persistence: int = 0
    retraining: bool = False
    adapter_changed: bool = False
    model_weight_changed: bool = False
    sha_mismatch_count: int = 0
    blocking_reasons: list[str] = field(default_factory=list)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_runtime_packages() -> RuntimePackageStatus:
    payload = detect_runtime_packages_dict()
    return RuntimePackageStatus(**payload["runtime_packages"])


def determine_load_mode(
    runtime: RuntimePackageStatus,
    asset_statuses: Mapping[str, Any],
    *,
    runtime_fail_class: str | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not runtime.all_available:
        missing = ",".join([name for name, ok in runtime.to_dict().items() if not ok])
        if runtime_fail_class:
            reasons.append(f"{runtime_fail_class}:{missing}")
        else:
            reasons.append("runtime_package_missing:" + missing)
    for name, check in asset_statuses.items():
        status = getattr(check, "status", "")
        if status.startswith("BLOCK_"):
            reasons.append(f"{name}:{status}")
        elif status == "MISSING_ALLOWED":
            reasons.append(f"{name}:asset_missing_contract_only")
        elif status.startswith("PARTIAL_DONE"):
            reasons.append(f"{name}:{status}")
    if any("BLOCK_" in reason for reason in reasons):
        return "blocked", reasons
    if runtime.all_available and not reasons:
        return "real_load_ready", reasons
    return "contract_only", reasons


def build_model_chain_status(*, allow_missing_assets: bool = True) -> ModelChainStatus:
    runtime_payload = load_runtime()
    runtime = RuntimePackageStatus(**runtime_payload["runtime_packages"])
    asset_statuses = verify_asset_contracts(allow_missing=allow_missing_assets)
    load_mode, reasons = determine_load_mode(
        runtime,
        asset_statuses,
        runtime_fail_class=runtime_payload.get("fail_class"),
    )
    mismatch_count = sha_mismatch_count(asset_statuses)
    if mismatch_count:
        status = "BLOCK_V3_SHA_MISMATCH"
    elif any("PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR" in reason for reason in reasons):
        status = "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR"
    elif any("runtime_package_missing" in reason or "PARTIAL_DONE_V3_RUNTIME_INSTALL_FAILED" in reason for reason in reasons):
        status = "PARTIAL_DONE_V3_RUNTIME_INSTALL_FAILED"
    elif any("asset_missing_contract_only" in reason for reason in reasons):
        status = "PARTIAL_DONE_CONTRACT_ONLY_ASSET_MISSING"
    elif any("PARTIAL_DONE_V3_SHA_SCOPE_PENDING" in reason for reason in reasons):
        status = "PARTIAL_DONE_V3_SHA_SCOPE_PENDING"
    elif load_mode == "real_load_ready":
        status = "PASS_V3_REAL_LOAD_READY"
    else:
        status = "PARTIAL_DONE_V3_RUNTIME_OR_ASSET_PENDING"
    return ModelChainStatus(runtime_available=runtime.all_available, runtime_packages=runtime.to_dict(), load_mode=load_mode, status=status, sha_mismatch_count=mismatch_count, blocking_reasons=reasons)


def build_rewrite_system_prompt() -> str:
    fields = ", ".join(REQUIRED_OUTPUT_FIELDS)
    return "You are Butler Box 2 Helper 3. Rewrite a foreign document into our internal format. Never transmit content externally. Never persist raw source text, filenames, or local paths. Return exactly these fields in Korean: " + fields + ". When uncertain, fill '확인 필요' instead of inventing facts."


def compose_rewrite_runner_input(
    *,
    system_prompt: str,
    foreign_doc_text: str,
    our_format_text: str,
) -> str:
    """Compose the single-string runner input for the real-load rewrite path.

    The runner is typed Callable[[str], str]; the system instruction alone
    cannot drive a rewrite — the foreign document and the target format must
    be present in the input or a backend can return schema-shaped JSON that
    is unrelated to the caller's document.
    """
    return (
        f"{system_prompt}\n\n"
        f"[FOREIGN_DOCUMENT]\n{foreign_doc_text}\n\n"
        f"[TARGET_FORMAT]\n{our_format_text}\n"
    )


def validate_rewrite_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_OUTPUT_FIELDS if field not in payload]
    extra = [field for field in payload.keys() if field not in REQUIRED_OUTPUT_FIELDS]
    valid = not missing and not extra and all(isinstance(payload[field], str) for field in REQUIRED_OUTPUT_FIELDS)
    return {"schema_version": "box2.helper3.rewrite_output_validation.v3", "valid": valid, "missing_fields": missing, "extra_fields": extra, "required_fields": list(REQUIRED_OUTPUT_FIELDS)}


def contract_only_rewrite(*, foreign_doc_text: str, our_format_text: str, runner: Callable[[str], str] | None = None) -> dict[str, Any]:
    status = build_model_chain_status(allow_missing_assets=True)
    prompt = build_rewrite_system_prompt()
    if status.load_mode != "real_load_ready" or runner is None:
        return {"schema_version": "box2.helper3.rewrite_response.v3", "load_mode": status.load_mode, "status": status.status, "contract_only": True, "mock_result": False, "external_send": 0, "raw_persistence": 0, "prompt_digest": _sha256_text(prompt), "input_digests": {"foreign_doc_digest": "sha256:" + _sha256_text(foreign_doc_text), "our_format_digest": "sha256:" + _sha256_text(our_format_text)}, "result": None, "blocking_reasons": status.blocking_reasons}
    runner_input = compose_rewrite_runner_input(
        system_prompt=prompt,
        foreign_doc_text=foreign_doc_text,
        our_format_text=our_format_text,
    )
    raw = runner(runner_input)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"schema_version": "box2.helper3.rewrite_response.v3_1", "load_mode": "blocked", "status": "BLOCK_V2_INVALID_JSON", "contract_only": False, "mock_result": False, "external_send": 0, "raw_persistence": 0, "result": None, "error": str(exc)}
    validation = validate_rewrite_output(parsed)
    return {"schema_version": "box2.helper3.rewrite_response.v3_1", "load_mode": "real_load_ready", "status": "PASS_V2_REWRITE_OUTPUT_VALID" if validation["valid"] else "BLOCK_V2_REWRITE_OUTPUT_INVALID", "contract_only": False, "mock_result": False, "external_send": 0, "raw_persistence": 0, "result": parsed if validation["valid"] else None, "validation": validation}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def export_model_chain_status(path: str | Path) -> None:
    Path(path).write_text(json.dumps(build_model_chain_status(allow_missing_assets=True).to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# Backward-compat shim: remote v1 rewrite_service.py imports `inspect_model_chain`.
# v2 renamed the entry point to `build_model_chain_status`; alias preserves coexistence.
inspect_model_chain = build_model_chain_status
