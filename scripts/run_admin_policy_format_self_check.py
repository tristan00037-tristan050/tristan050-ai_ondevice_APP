from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.company_policy.contracts import AccessRule, AdminContext, make_company_policy, sha256_text
from butler_pc_core.company_policy.policy_gate import PolicyGate, build_policy_task_envelope
from butler_pc_core.company_policy.storage import CompanyFormatStore, PolicyStore
# helper3 format adapter 위치 정합 (표준 156): MAINDEV `company_policy/format_adapter.py`
# 위치 폐기, ALG `cards/box3/adapters/company_format_adapter` 단일 경로가 정본.
from butler_pc_core.cards.box3.adapters.company_format_adapter import apply_company_format_runtime


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        admin = AdminContext(
            admin_id_digest=sha256_text("admin"),
            role="admin",
            admin_session_digest=sha256_text("session"),
            auth_method="test_only",
        )
        dept = sha256_text("dept")
        policy = make_company_policy(
            registered_by_digest=admin.admin_id_digest,
            access_rules=[AccessRule(dept_digest=dept, role="employee", doc_grade="internal", decision="allow", reason_code="RULE_MATCHED")],
        )
        policy_store = PolicyStore(root=root / "policy")
        policy_store.save_policy(policy, admin)
        env = build_policy_task_envelope(
            request_id="req-self-check",
            tenant_digest=sha256_text("tenant"),
            dept_digest=dept,
            user_role="employee",
            target_box_id="3",
            operation="draft_write",
            doc_grade="internal",
        )
        gate = PolicyGate.evaluate(env, policy_store.load_active_policy())
        assert gate.allowed is True

        format_store = CompanyFormatStore(root=root / "format")
        fmt, audit = format_store.register_format(
            template_runtime_text="제목\\n본문\\n결재",
            format_kind="report",
            title_runtime_text="보고서",
            language="ko",
            dept_digest=dept,
            admin=admin,
        )
        adapter = apply_company_format_runtime(
            draft_text_runtime_only="draft 본문(runtime only)",
            format_id=fmt.format_id,
            store=format_store,
        ).to_dict()
        assert adapter["format_applied"] is True
        assert adapter["needs_review"] is False
        assert adapter["raw_saved_zero"] is True
        assert adapter["external_send_zero"] is True
        print("SELF_CHECK_PASS=1")
        print(f"policy_digest={policy.policy_digest}")
        print(f"format_digest={fmt.format_digest}")
        print(f"template_digest={fmt.template_digest}")
        print(f"policy_gate_allowed={1 if gate.allowed else 0}")
        print(f"audit_raw_saved_zero={1 if audit['raw_saved_zero'] else 0}")
        print("external_send_zero=1")


if __name__ == "__main__":
    main()
