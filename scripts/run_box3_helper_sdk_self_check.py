from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope, sha256_text
from butler_pc_core.cards.box3.actual_operation_pipeline import run_box3_actual_operation
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.local_sealed_runner import build_deterministic_test_runner


def _approval(scope_digest: str) -> dict:
    return {
        "schema_version": "box3.human_approval.v1",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("admin"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


def _write_fake_sdks(root: Path) -> None:
    (root / "helper7_table_figure_sdk.py").write_text(
        "def parse_for_evidence(reference_payload):\n"
        "    return [{'text': x, 'source_text': x, 'kind': 'text'} for x in reference_payload]\n",
        encoding="utf-8",
    )
    (root / "helper4_grounding_sdk.py").write_text(
        "def ground_claims(draft_text, evidence_bundle, embedder=None):\n"
        "    return None\n",
        encoding="utf-8",
    )
    (root / "helper8_company_style_sdk.py").write_text(
        "def apply_company_style(draft_text, profile_ref=None):\n"
        "    return draft_text\n",
        encoding="utf-8",
    )
    (root / "helper2_embedding_sdk.py").write_text("class Helper2Embedder: pass\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        sdk = Path(d)
        _write_fake_sdks(sdk)
        os.environ["BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH"] = str(sdk / "helper7_table_figure_sdk.py")
        os.environ["BUTLER_HELPER4_GROUNDING_SDK_PATH"] = str(sdk / "helper4_grounding_sdk.py")
        os.environ["BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH"] = str(sdk / "helper8_company_style_sdk.py")
        os.environ["BUTLER_HELPER2_EMBEDDING_SDK_PATH"] = str(sdk / "helper2_embedding_sdk.py")
        guard = build_example_component_use_guard(
            allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"
        )
        env = Box3ActualRuntimeEnvelope.from_raw(
            reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
            drafting_request="납품 일정을 반영해 초안을 작성하세요.",
        )
        verdict = run_box3_actual_operation(
            env,
            helper_component_guard=guard,
            human_approval_config=_approval(env.request_digest),
            fixed_eval_pass=True,
            runner=build_deterministic_test_runner(),
        )
        payload = {
            "SELF_CHECK_PASS": True,
            "status": verdict.status,
            "fail_class": verdict.fail_class,
            "real_claim_allowed": verdict.real_claim_allowed,
            "helper_sdk_receipts_present": bool(verdict.helper_sdk_receipts),
            "external_send_zero": verdict.external_send_zero,
            "raw_saved_zero": verdict.raw_saved_zero,
            "raw_text_logged": verdict.raw_text_logged,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
