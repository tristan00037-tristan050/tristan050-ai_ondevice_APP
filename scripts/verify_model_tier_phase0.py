#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "3b442f93ae63c7a4f4b9b572298854e951bec5ca"
EXPECTED_SCHEMAS = {
    "model_variant_v1.schema.json",
    "device_profile_v1.schema.json",
    "task_profile_v1.schema.json",
    "tier_decision_v1.schema.json",
    "model_tier_shadow_record_v1.schema.json",
    "benchmark_result_v1.schema.json",
}
ALLOWED_CHANGED_PREFIXES = (
    "butler_pc_core/model_tier/",
    "schemas/model_tier/",
    "tests/model_tier/",
    "scripts/benchmark_model_tier_phase0.py",
    "scripts/verify_model_tier_phase0.py",
    "butler_pc_core/sidecar/routes/router_decide.py",
    "butler_pc_core/sidecar/routes/router_intake_decide.py",
    "butler_pc_core/sidecar/routes/box3_draft.py",
    "butler_sidecar.py",
    "butler-desktop/src-tauri/src/lib.rs",
    "tests/cards/box3/test_box3_model_scope_approval_scripts.py",
)
PROTECTED_PREFIXES = (
    "butler_pc_core/cards/box2/",
    "butler_pc_core/accounting/",
    "butler_pc_core/cards/box3/sdk/",
    "butler_pc_core/cards/box3/eval/",
)


def _git_paths(*args: str) -> set[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(ROOT), *args, "-z"],
        )
    except Exception:
        return set()
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in output.split(b"\0")
        if item
    }


def _changed_paths() -> set[str]:
    paths = _git_paths("diff", "--name-only", BASE)
    paths.update(_git_paths("ls-files", "--others", "--exclude-standard"))
    return paths


def _record(index: int) -> dict:
    from butler_pc_core.model_tier.contracts import sha256_text
    from butler_pc_core.model_tier.routing_audit import build_shadow_record

    digest = sha256_text(str(index))
    return build_shadow_record(
        timestamp_epoch_ms=index,
        request_digest=digest,
        box_id="3",
        task_profile_digest=digest,
        device_profile_digest=digest,
        policy_digest=digest,
        decision_digest=digest,
        recommended_tier="TIER_1P7B",
        recommended_variant_id="box3_v9_2_r2b_1p7_q4_k_m",
        reason_codes=("BOX3_SPECIALIZED_1P7B_PRIMARY",),
        high_eligible=False,
        gate_reason_code=None,
        would_escalate=False,
        actual_response_digest=digest,
    )


def main() -> int:
    sys.path.insert(0, str(ROOT))
    errors: list[str] = []
    changed = _changed_paths()

    v1 = bool(changed) and all(
        any(path.startswith(prefix) for prefix in ALLOWED_CHANGED_PREFIXES)
        for path in changed
    )
    v1 = v1 and not any(
        path.startswith(prefix) for path in changed for prefix in PROTECTED_PREFIXES
    )
    if not v1:
        errors.append("MT0_V1_SCOPE_OR_PROTECTED_DIFF")

    schema_names = {
        path.name for path in (ROOT / "schemas" / "model_tier").glob("*.json")
    }
    v2 = schema_names == EXPECTED_SCHEMAS
    production_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "butler_pc_core" / "model_tier").glob("*.py")
    )
    v2 = v2 and "actual_model_selection_unchanged" in production_text
    v2 = v2 and "actual_model_invocations=0" in production_text
    if not v2:
        errors.append("MT0_V2_SHADOW_INVARIANT_MISSING")

    from butler_pc_core.model_tier.device_profiler import collect_device_profile

    profile = collect_device_profile()
    v3 = bool(
        profile.platform == "darwin"
        and profile.architecture in {"arm64", "aarch64"}
        and profile.validity.value == "VALID"
        and profile.total_memory_bytes
        and profile.available_memory_bytes is not None
        and profile.total_memory_bytes > 0
        and 0 <= profile.available_memory_bytes <= profile.total_memory_bytes
    )
    if not v3:
        errors.append("MT0_V3_MACOS_PROFILE_NOT_VALID")

    from butler_pc_core.model_tier.box_policies import phase0_box3_policy
    from butler_pc_core.model_tier.cascade_policy import plan_shadow_cascade
    from butler_pc_core.model_tier.contracts import GateResult, stable_digest

    def gate(reason: str) -> GateResult:
        payload = {
            "passed": False,
            "reason_code": reason,
            "severity": "hard",
            "quality_vector": {},
        }
        return GateResult(
            schema_version="butler.gate_result.v1",
            passed=False,
            reason_code=reason,
            severity="hard",
            quality_vector={},
            result_digest=stable_digest(payload),
        )

    hard_plans = [
        plan_shadow_cascade(
            box_id="3",
            gate=gate(reason),
            policy=phase0_box3_policy(),
            high_eligible=True,
        )
        for reason in ("BLOCK_DLP_OUTBOUND_DRAFT", "UNREGISTERED_FAIL_CLASS")
    ]
    forbidden_calls = (".generate(", ".generate_text(", ".generate_with_cancel(")
    v4 = all(
        not plan.would_escalate and plan.actual_model_invocations == 0
        for plan in hard_plans
    ) and not any(token in production_text for token in forbidden_calls)
    if not v4:
        errors.append("MT0_V4_CASCADE_EXECUTION_OR_HARD_ESCALATION")

    v5 = "BUTLER_FORCE_MODEL" not in production_text
    if not v5:
        errors.append("MT0_V5_PRODUCTION_FORCE_ENV_REFERENCE")

    from butler_pc_core.model_tier.routing_audit import (
        ALLOWED_SHADOW_KEYS,
        HashChainJsonlWriter,
        validate_shadow_record,
    )

    v6 = False
    try:
        # macOS /tmp is itself a symlink to /private/tmp; use the physical path so
        # the audit writer's component-level symlink guard remains meaningful.
        with tempfile.TemporaryDirectory(
            prefix="butler-mt0-",
            dir="/private/tmp",
        ) as temp_dir:
            path = Path(temp_dir) / "audit" / "model_tier_shadow_v1.jsonl"
            writer = HashChainJsonlWriter(path)
            writer.append(_record(1))
            writer.append(_record(2))
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                validate_shadow_record(row)
            v6 = bool(
                len(rows) == 2
                and all(set(row) == ALLOWED_SHADOW_KEYS for row in rows)
                and rows[1]["previous_record_digest"] == rows[0]["record_digest"]
                and all(row["raw_text_logged"] is False for row in rows)
                and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
                and stat.S_IMODE(path.stat().st_mode) == 0o600
            )
    except Exception:
        v6 = False
    if not v6:
        errors.append("MT0_V6_AUDIT_SECURITY_FAILED")

    print(f"MODEL_TIER_PHASE0_VERIFY_OK={0 if errors else 1}")
    print(f"MODEL_TIER_PHASE0_V1_GOLDEN_SCOPE_OK={1 if v1 else 0}")
    print(f"MODEL_TIER_PHASE0_V2_SHADOW_INVARIANT_OK={1 if v2 else 0}")
    print(f"MODEL_TIER_PHASE0_V3_MACOS_PROFILE_OK={1 if v3 else 0}")
    print(f"MODEL_TIER_PHASE0_V4_CASCADE_SAFETY_OK={1 if v4 else 0}")
    print(f"MODEL_TIER_PHASE0_V5_FORCE_DISABLED_OK={1 if v5 else 0}")
    print(f"MODEL_TIER_PHASE0_V6_AUDIT_SECURITY_OK={1 if v6 else 0}")
    for error in errors:
        print(f"ERROR_CODE={error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
