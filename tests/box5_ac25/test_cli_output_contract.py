"""§15 M-5 — 공개 출력 규약 시험.

검증기가 실패 상세와 경로 목록을 로그로 쏟으면, 그 로그 자체가 우리가 감추려던
것을 드러낸다. AGENTS.md 의 meta-only 규율을 따른다.

★내부 API 의 FailureEvidence 와 offending_paths 는 유지한다. CLI 가 그것을 공개
  로그로 내지 않을 뿐이다. 둘 다 시험한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from ac25 import lock_verifier, orchestrator, stage_b_runner

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]

_ASCII_CODE = re.compile(r"\A[A-Z][A-Z0-9_]{1,63}\Z")


def _lines(captured) -> list[str]:
    return captured.out.splitlines()


# ══ 실패: 정확히 두 줄 ═════════════════════════════════════════════════
def test_failure_output_is_exactly_two_lines(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "trusted_repository_root", lambda: tmp_path)
    assert orchestrator._main([]) == 1
    captured = capsys.readouterr()
    lines = _lines(captured)
    assert len(lines) == 2, lines
    assert lines[0] == "VERDICT=0"
    assert lines[1].startswith("ERROR_CODE=")
    assert captured.err == ""


def test_failure_error_code_is_a_short_ascii_token(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "trusted_repository_root", lambda: tmp_path)
    orchestrator._main([])
    code = _lines(capsys.readouterr())[1].split("=", 1)[1]
    assert _ASCII_CODE.match(code), code
    assert len(code) <= 64
    assert code.isascii()


def test_no_traceback_or_paths_in_failure_output(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "trusted_repository_root", lambda: tmp_path)
    orchestrator._main([])
    text = capsys.readouterr().out
    for forbidden in ("Traceback", "File \"", ".py", "/", "\\", "expected", "observed"):
        assert forbidden not in text, forbidden


def test_input_failure_reports_only_its_code(capsys, monkeypatch):
    monkeypatch.setattr(
        orchestrator, "trusted_repository_root", lambda: REPO_ROOT
    )
    monkeypatch.delenv("AC25_EXPECTED_HEAD", raising=False)
    monkeypatch.setenv("AC25_PR_NUMBER", "$(id)")
    assert orchestrator._main([]) == 1
    lines = _lines(capsys.readouterr())
    # ★R6-3 §6-5 — 좌표·PR 번호를 env 로 주는 경로 자체가 닫혔다. payload 는
    #   해석되기도 전에 "그 이름이 존재한다" 는 사실만으로 거부된다.
    assert lines == ["VERDICT=0", "ERROR_CODE=INPUT_USER_SUPPLIED_COORDINATE_PRESENT"]
    assert "$(id)" not in "\n".join(lines)


# ══ 성공 형태 ══════════════════════════════════════════════════════════
def test_success_output_shape(capsys):
    orchestrator._emit(1, "OK")
    assert _lines(capsys.readouterr()) == ["VERDICT=1", "ERROR_CODE=OK"]


def test_runner_uses_the_same_two_line_contract(capsys, tmp_path):
    assert stage_b_runner._main(
        ["--trusted-root", str(tmp_path / "absent"),
         "--worktree", str(tmp_path), "--mode", "plan"]
    ) == 1
    lines = _lines(capsys.readouterr())
    assert len(lines) == 2
    assert lines[0] == "VERDICT=0"
    assert _ASCII_CODE.match(lines[1].split("=", 1)[1])


# ══ 내부 API 는 증거를 유지한다 ════════════════════════════════════════
def test_internal_lock_verdict_still_carries_offending_paths(tmp_path):
    """★공개 로그에 내지 않을 뿐, 내부 반환 객체에는 남아 있다."""
    verdict = lock_verifier.verify_integration_lock(
        repository_path=str(tmp_path),
        lock_path=str(tmp_path / "absent.json"),
        expected_head="a" * 40,
        expected_tree="b" * 40,
        execution_commit="c" * 40,
    )
    assert verdict.ok is False
    assert verdict.failures
    assert hasattr(verdict, "offending_paths")
    for failure in verdict.failures:
        assert failure.code
        assert hasattr(failure, "expected")
        assert hasattr(failure, "observed")


def test_orchestrator_result_keeps_full_failure_evidence(monkeypatch, tmp_path):
    from ac25 import remote_facts as rf

    dead = lambda path: rf.TransportResult(status=404)  # noqa: E731
    result = orchestrator.run_verification(
        router=rf.TransportRouter(approval=dead, candidate=dead, run=dead),
        run_id=1,
        expected_head="a" * 40,
        expected_tree="b" * 40,
        verifier_commit="c" * 40,
        repository_root=tmp_path,
    )
    assert result.ok is False
    assert result.failures[0].code
    assert result.error_code == result.failures[0].code


# ══ receipt 는 meta-only ═══════════════════════════════════════════════
ALLOWED_RECEIPT_SUFFIXES = ("_count", "_sha256", "_commit", "_tree", "_at", "_head")
ALLOWED_RECEIPT_KEYS = {
    "verdict", "error_code", "verifier_commit", "protected_state", "pr_number",
    "approval_repository", "candidate_repository", "protected_ref",
    "signing_key_fingerprint", "coverage_basis", "dependency_manifest_path",
    "dependency_hash_pinned", "approval_commit_reachable", "effective_expiry",
}


def test_receipt_contains_only_meta_values(tmp_path):
    from ac25 import remote_facts as rf

    dead = lambda path: rf.TransportResult(status=404)  # noqa: E731
    result = orchestrator.run_verification(
        router=rf.TransportRouter(approval=dead, candidate=dead, run=dead),
        run_id=1,
        expected_head="a" * 40,
        expected_tree="b" * 40,
        verifier_commit="c" * 40,
        repository_root=REPO_ROOT,
    )
    for key, value in result.receipt.items():
        assert not isinstance(value, (list, tuple, dict)), f"{key} 가 묶음이다"
        if key in ALLOWED_RECEIPT_KEYS:
            continue
        assert key.endswith(ALLOWED_RECEIPT_SUFFIXES), key


def test_receipt_is_written_atomically(tmp_path):
    target, digest = orchestrator.write_receipt({"verdict": 1}, directory=tmp_path)
    assert target.name == orchestrator.RECEIPT_FILENAME
    assert json.loads(target.read_text())["verdict"] == 1
    assert len(digest) == 64
    # ★C6 — receipt 파일은 0600 이다
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    # 임시 파일이 남지 않는다
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".ac25-receipt-")]
    assert leftovers == []


def test_receipt_write_replaces_previous_content(tmp_path):
    orchestrator.write_receipt({"verdict": 0, "error_code": "X"}, directory=tmp_path)
    orchestrator.write_receipt({"verdict": 1, "error_code": "OK"}, directory=tmp_path)
    written = json.loads((tmp_path / orchestrator.RECEIPT_FILENAME).read_text())
    assert written == {"verdict": 1, "error_code": "OK"}


def test_path_manifest_digest_replaces_the_list():
    digest = orchestrator.path_manifest_sha256(["b/x.py", "a/y.py"])
    assert len(digest) == 64
    # 순서가 달라도 같은 값
    assert digest == orchestrator.path_manifest_sha256(["a/y.py", "b/x.py"])
    # 내용이 다르면 다른 값
    assert digest != orchestrator.path_manifest_sha256(["a/y.py"])


# ══ 워크플로가 원문을 쏟지 않는다 ══════════════════════════════════════
def test_workflow_never_cats_the_receipt_to_the_log():
    trusted = (
        REPO_ROOT / ".github" / "workflows" / "box5-ac25-trusted-verification.yml"
    ).read_text(encoding="utf-8")
    # GITHUB_OUTPUT 으로는 보내지만 로그로 cat 하지 않는다
    for line in trusted.splitlines():
        stripped = line.strip()
        if stripped.startswith("cat ") and "ac25-receipt.json" in stripped:
            assert "GITHUB_OUTPUT" in trusted.split(stripped)[1][:200], stripped


def test_no_verification_json_dump_in_workflows():
    for name in ("box5-ac25-trusted-verification.yml", "box5-ac25-stage-a-smoke.yml"):
        body = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "cat verification.json" not in body
        assert "verification.json" not in body
