from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

import butler_pc_core.accounting.rulebase_learning.diff_builder as diff_builder
import butler_pc_core.accounting.rulebase_learning.runner as runner
from butler_pc_core.accounting.classifier import classify_df
from butler_pc_core.accounting.rulebase_learning import (
    explain_drop_reason,
    gate_candidate,
    is_verified_rule_base_candidate,
    make_candidate,
    sha256_text,
)
from butler_pc_core.accounting.rulebase_learning.diff_builder import (
    RulePatchDiffError,
    build_pr_candidate_manifest,
    build_unified_diff,
    manifest_digest,
)
from butler_pc_core.accounting.rulebase_learning.queue import RulePatchQueue, RulePatchQueueError
from butler_pc_core.accounting.rulebase_learning.runner import (
    RuleBaseLearningRunError,
    run_verified_rule_base_flow,
)
from butler_pc_core.company_profile.contracts import make_runtime_profile
from butler_pc_core.connect_loop.learning_candidate_gate import _is_candidate_usage_log

REPO_ROOT = Path(__file__).resolve().parents[2]


def _digest(label: str) -> str:
    return sha256_text(f"box5-rulebase-learning:{label}")


def _candidate(**overrides):
    candidate = make_candidate(
        candidate_id="vrb-000000000001",
        approved_rule_token_ref="vault://box5/rule-token/2026-06-30/a",
        approved_rule_token_digest=_digest("approved-token"),
        group_a_report_digest=_digest("group-a-report"),
        source_usage_log_ids=["ulog-box5-verified-1"],
        expected_effect_digest=_digest("expected-effect"),
        tests_to_run=["python3 -m pytest tests/accounting/test_self_transfer_guard.py -q"],
    )
    candidate.update(overrides)
    return candidate


def _group_a_report(**overrides):
    report = {
        "candidate_id": "vrb-000000000002",
        "group_a_verified": True,
        "approved_rule_token_ref": "vault://box5/rule-token/2026-06-30/b",
        "approved_rule_token_digest": _digest("approved-token-b"),
        "group_a_report_digest": _digest("group-a-report-b"),
        "source_usage_log_ids": ["ulog-box5-verified-2"],
        "expected_effect_digest": _digest("expected-effect-b"),
        "tests_to_run": ["python3 -m pytest tests/accounting/test_self_transfer_guard.py -q"],
    }
    report.update(overrides)
    return report


def test_learning_usage_log_gate_is_unchanged_and_excludes_verified_rule_base():
    source = inspect.getsource(_is_candidate_usage_log)
    for required_fragment in (
        'usage_log.get("learning_candidate") is True',
        'usage_log.get("policy_decision") == "allow"',
        'usage_log.get("integration_mode") == "real"',
        'usage_log.get("real_validation_done") is True',
        'usage_log.get("external_send_zero") is True',
        'usage_log.get("raw_text_logged") is False',
        'usage_log.get("learning_event_created") is False',
        'usage_log.get("retention_class") == "audit_digest_only"',
    ):
        assert required_fragment in source
    assert "verified_rule_base" not in source

    verified_rule_base_like = {
        "learning_candidate": True,
        "policy_decision": "allow",
        "integration_mode": "verified_rule_base",
        "real_validation_done": True,
        "external_send_zero": True,
        "raw_text_logged": False,
        "learning_event_created": False,
        "retention_class": "audit_digest_only",
    }
    assert _is_candidate_usage_log(verified_rule_base_like) is False


def test_verified_rule_base_schema_self_validates_draft07():
    schema_path = REPO_ROOT / "schemas/box5/verified_rule_base_candidate_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    Draft7Validator.check_schema(schema)
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["additionalProperties"] is False


def test_verified_rule_base_candidate_accepts_group_a_verified_digest_only():
    candidate = _candidate()

    assert is_verified_rule_base_candidate(candidate) is True
    decision = gate_candidate(candidate)
    assert decision.accepted is True
    assert decision.drop_reason is None
    assert decision.candidate == candidate
    assert candidate["learning_source_type"] == "verified_rule_base"
    assert candidate["group_a_verified"] is True
    assert candidate["auto_apply_to_runtime"] is False
    assert candidate["rule_patch_created"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("integration_mode", "real"),
        ("learning_event_created", True),
        ("raw_text_logged", True),
        ("auto_apply_to_runtime", True),
        ("model_training", True),
        ("peft_training", True),
        ("group_a_verified", False),
    ),
)
def test_verified_rule_base_gate_rejects_spoof_or_unsafe_flags(field, value):
    candidate = _candidate()
    candidate[field] = value

    assert is_verified_rule_base_candidate(candidate) is False
    assert explain_drop_reason(candidate) is not None


def test_verified_rule_base_gate_rejects_forbidden_raw_field():
    candidate = _candidate()
    candidate["raw_memo"] = "digest-only contract must reject this field"

    assert is_verified_rule_base_candidate(candidate) is False
    assert explain_drop_reason(candidate) is not None


def test_rule_patch_queue_persists_digest_only_entries(tmp_path):
    queue_path = tmp_path / "box5-rulebase-candidates.jsonl"
    queue = RulePatchQueue(queue_path)
    written = queue.append(_candidate())

    loaded = queue.load()
    assert loaded == [written]
    assert queue.digests()[0].startswith("sha256:")
    saved_text = queue_path.read_text(encoding="utf-8")
    assert "raw_memo" not in saved_text
    assert "transaction_text" not in saved_text
    assert "account_number_plain" not in saved_text
    assert "amount_plain" not in saved_text
    assert "verified_rule_base" in saved_text


def test_rule_patch_queue_rejects_bad_candidates(tmp_path):
    bad = _candidate(group_a_verified=False)

    with pytest.raises(RulePatchQueueError):
        RulePatchQueue(tmp_path / "queue.jsonl").append(bad)


def test_rule_patch_diff_generator_allows_only_declared_targets(tmp_path):
    repo = tmp_path
    matcher_path = repo / "butler_pc_core/company_profile/matcher.py"
    matcher_path.parent.mkdir(parents=True)
    matcher_path.write_text("SAFE_SYMBOL = 'old'\n", encoding="utf-8")

    diff = build_unified_diff(
        repo,
        {
            "butler_pc_core/company_profile/matcher.py": "SAFE_SYMBOL = 'new'\n",
        },
        expected_current_digest_by_path={
            "butler_pc_core/company_profile/matcher.py": sha256_text("SAFE_SYMBOL = 'old'\n"),
        },
    )

    assert diff.changed_paths == ("butler_pc_core/company_profile/matcher.py",)
    assert diff.diff_digest.startswith("sha256:")
    assert "SAFE_SYMBOL = 'new'" in diff.diff_text
    with pytest.raises(RulePatchDiffError):
        build_unified_diff(
            repo,
            {"butler_pc_core/accounting/classifier.py": "# forbidden\n"},
            expected_current_digest_by_path={
                "butler_pc_core/accounting/classifier.py": sha256_text(""),
            },
        )
    with pytest.raises(RulePatchDiffError):
        build_unified_diff(
            repo,
            {"butler_pc_core/connect_loop/usage_log.py": "# forbidden\n"},
            expected_current_digest_by_path={
                "butler_pc_core/connect_loop/usage_log.py": sha256_text(""),
            },
        )


def test_rule_patch_diff_generator_requires_current_sha_match(tmp_path):
    repo = tmp_path
    matcher_path = repo / "butler_pc_core/company_profile/matcher.py"
    matcher_path.parent.mkdir(parents=True)
    matcher_path.write_text("SAFE_SYMBOL = 'old'\n", encoding="utf-8")

    with pytest.raises(RulePatchDiffError, match="PATCH_TARGET_SHA_REQUIRED"):
        build_unified_diff(
            repo,
            {"butler_pc_core/company_profile/matcher.py": "SAFE_SYMBOL = 'new'\n"},
            expected_current_digest_by_path={},
        )
    with pytest.raises(RulePatchDiffError, match="PATCH_TARGET_SHA_MISMATCH"):
        build_unified_diff(
            repo,
            {"butler_pc_core/company_profile/matcher.py": "SAFE_SYMBOL = 'new'\n"},
            expected_current_digest_by_path={
                "butler_pc_core/company_profile/matcher.py": sha256_text("different"),
            },
        )


def test_pr_candidate_manifest_is_digest_only_and_human_review_required(tmp_path):
    repo = tmp_path
    target_path = repo / "tests/accounting/test_self_transfer_guard.py"
    target_path.parent.mkdir(parents=True)
    target_path.write_text("def test_old():\n    assert True\n", encoding="utf-8")
    diff = build_unified_diff(
        repo,
        {"tests/accounting/test_self_transfer_guard.py": "def test_new():\n    assert True\n"},
        expected_current_digest_by_path={
            "tests/accounting/test_self_transfer_guard.py": sha256_text("def test_old():\n    assert True\n"),
        },
    )

    manifest = build_pr_candidate_manifest(
        candidate=_candidate(),
        rule_patch_diff=diff,
        base_sha="a" * 40,
        head_sha="b" * 40,
    )

    assert manifest["human_review_required"] is True
    assert manifest["auto_apply_to_runtime"] is False
    assert manifest["rule_patch_created"] is True
    assert manifest["model_training"] is False
    assert manifest["peft_training"] is False
    assert manifest_digest(manifest).startswith("sha256:")
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    assert "raw_memo" not in manifest_text
    assert "transaction_text" not in manifest_text
    assert "vault://" not in manifest_text


def test_runner_queues_verified_candidate_and_stops_at_pr_candidate(tmp_path):
    repo = tmp_path
    target_path = repo / "butler_pc_core/accounting/rulebase_learning/rule_token_config.json"
    target_path.parent.mkdir(parents=True)
    target_path.write_text('{"tokens":[]}\n', encoding="utf-8")

    result = run_verified_rule_base_flow(
        group_a_report=_group_a_report(),
        queue_path=tmp_path / "queue" / "candidates.jsonl",
        repo_root=repo,
        replacement_text_by_path={
            "butler_pc_core/accounting/rulebase_learning/rule_token_config.json": '{"tokens":["digest:approved"]}\n',
        },
        expected_current_digest_by_path={
            "butler_pc_core/accounting/rulebase_learning/rule_token_config.json": sha256_text('{"tokens":[]}\n'),
        },
        base_sha="c" * 40,
        head_sha="d" * 40,
    )

    assert result.queued_candidate["learning_source_type"] == "verified_rule_base"
    assert result.queue_entry_digest.startswith("sha256:")
    assert result.rule_patch_diff is not None
    assert result.pr_candidate_manifest is not None
    assert result.pr_candidate_manifest["auto_apply_to_runtime"] is False
    assert result.pr_candidate_manifest_digest is not None
    assert target_path.read_text(encoding="utf-8") == '{"tokens":[]}\n'


def test_runner_rejects_unverified_group_a_report(tmp_path):
    with pytest.raises(RuleBaseLearningRunError):
        run_verified_rule_base_flow(
            group_a_report=_group_a_report(group_a_verified=False),
            queue_path=tmp_path / "queue.jsonl",
        )


def test_rulebase_learning_modules_do_not_commit_push_or_train():
    source = "\n".join(
        [
            inspect.getsource(runner),
            inspect.getsource(diff_builder),
        ]
    )
    forbidden_fragments = (
        "git commit",
        "git push",
        "subprocess.run",
        "subprocess.Popen",
        "auto_apply_to_runtime\": True",
        "model_training\": True",
        "peft_training\": True",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_box5_accuracy_no_regression():
    pd = pytest.importorskip("pandas")
    profile = make_runtime_profile(
        own_bank_holder_aliases=["주식회사 에이티링크", "(주)에이티링크"],
        own_company_aliases=["주식회사 에이티링크", "(주)에이티링크", "에이티링크"],
        own_account_numbers=["123-456789-01-029"],
    )
    out = classify_df(
        pd.DataFrame(
            [
                {
                    "적요": "타행이체",
                    "입금": "10000",
                    "출금": "",
                    "상대계좌예금주명": "주식회사 에이티링크",
                },
                {
                    "적요": "ABC컨설팅 용역 수입",
                    "입금": "1000000",
                    "출금": "",
                    "상대계좌예금주명": "ABC컨설팅",
                },
                {
                    "적요": "타행이체",
                    "입금": "50000",
                    "출금": "",
                    "상대계좌예금주명": "외부표기",
                    "상대계좌번호": "123-456789-01-029",
                },
            ]
        ).fillna(""),
        company_profile=profile,
    )

    assert list(out["분류과목"]) == ["미분류", "용역매출", "미분류"]
    assert list(out["_guard_reason"]) == ["SELF_HOLDER_MATCH", "", "OWN_ACCOUNT_MATCH"]


def test_rulebase_learning_does_not_import_or_call_subprocess_for_git():
    assert "subprocess" not in inspect.getsource(runner)
