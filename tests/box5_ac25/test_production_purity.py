"""조건부 허용 4항 — 시험 픽스처가 production 경로로 새지 않음을 정적으로 강제.

  ① production workflow 가 tests/box5_ac25/fixtures 를 절대 읽지 않는다
  ② production CLI 에 로컬 경로 입력 인자가 없다
  ③ 승인 바이트는 고정 repo·commit·path 의 API 응답으로만 얻는다
  ④ production 모듈에서 tests/ import·경로 참조가 0 이다

정적 시험이라 실행 없이도 성립한다. 사람이 지키기로 하는 약속이 아니라
어기면 빨간불이 켜지는 계약이다.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml
from ac25 import anchors, orchestrator

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = REPO_ROOT / "scripts" / "ci" / "ac25"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "box5-ac25-trusted-verification.yml"

PRODUCTION_MODULES = sorted(PRODUCTION_DIR.glob("*.py"))

# 승인 바이트를 파일로 읽으면 안 되는 모듈(원격 API 만 허용).
# approval_signature.py 는 제외한다 — ssh-keygen 에 넘기려고 ★자기가 방금 쓴
# 임시 파일★ 을 여는 것뿐이며, 아래 별도 시험이 그 성질을 따로 강제한다.
NO_FILESYSTEM_READ = ("approval_loader.py", "remote_facts.py")
_READ_CALLS = ("open", "read_bytes", "read_text", "readlines")


def _sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in PRODUCTION_MODULES}


def test_production_modules_exist():
    names = {path.name for path in PRODUCTION_MODULES}
    assert {"orchestrator.py", "anchors.py", "approval_loader.py", "remote_facts.py"} <= names


# ── ④ tests/ import·경로 참조 0 ────────────────────────────────────────
def test_no_production_module_imports_tests():
    for name, source in _sources().items():
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.split(".")[0] == "tests", f"{name}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                assert module != "tests", f"{name}: {node.module}"


@pytest.mark.parametrize("forbidden", ["fixtures", "conftest"])
def test_no_production_module_references_the_test_tree(forbidden):
    """★승인 픽스처를 production 경로에서 가리킬 수 없다."""
    for name, source in _sources().items():
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert forbidden not in node.value, f"{name} 안의 문자열: {node.value!r}"


def test_test_tree_is_named_only_as_the_ast_scan_root():
    """§5-1 은 시험 트리를 ★AST 로 전수 조사★ 하라고 정한다.

    그래서 시험 디렉터리 이름이 production 에 남는다. 다만 그 용도는 오직
    `test_root=` 인자여야 하며, 파일을 읽어 신뢰 판정에 쓰는 자리가 아니다.
    """
    allowed = {"orchestrator.py", "stage_b_runner.py", "verify_allowed_delta.py"}
    offenders = {name for name, source in _sources().items() if "box5_ac25" in source}
    assert offenders == allowed, offenders
    for name in sorted(allowed - {"verify_allowed_delta.py"}):
        source = (PRODUCTION_DIR / name).read_text(encoding="utf-8")
        occurrences = [line.strip() for line in source.splitlines() if "box5_ac25" in line]
        assert occurrences, name
        for line in occurrences:
            # 허용 용도는 둘뿐이다 — AST 조사 뿌리, 그리고 자기시험 대상 디렉터리
            assert "test_root=" in line or 'str(plan.trusted_root / "tests" / "box5_ac25")' in line, line


def test_the_only_tests_prefix_is_the_lock_derived_candidate_filter():
    """`tests/` 라는 글자가 남아 있어도 그것은 ★후보 저장소의 검사 목록★ 필터다.

    이 저장소의 시험 트리를 가리키는 것이 아니고, 승인 산출물을 읽는 경로도
    아니다. 한 모듈의 이름 붙은 상수 하나로만 존재해야 한다.
    """
    offenders = {name for name, source in _sources().items() if "tests/" in source}
    assert offenders == {"designated_checks.py", "verify_allowed_delta.py"}, offenders
    source = (PRODUCTION_DIR / "designated_checks.py").read_text(encoding="utf-8")
    occurrences = [line.strip() for line in source.splitlines() if "tests/" in line]
    assert occurrences == ['_TESTS_PREFIX = "tests/"']


# ── ③ 승인 바이트는 API 응답으로만 ────────────────────────────────────
@pytest.mark.parametrize("name", NO_FILESYSTEM_READ)
def test_approval_modules_never_read_the_filesystem(name):
    source = (PRODUCTION_DIR / name).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = getattr(func, "id", None) or getattr(func, "attr", None)
            assert called not in _READ_CALLS, f"{name} 이 {called}() 를 부른다"


def test_signature_verifier_can_only_be_given_bytes():
    """서명 검증기는 ★위치★ 를 받지 않는다. 파일을 가리킬 수 없으니 읽을 수도 없다."""
    import inspect

    from ac25.approval_signature import verify_approval_signature

    signature = inspect.signature(verify_approval_signature)
    assert list(signature.parameters) == [
        "document_bytes", "signature_bytes", "allowed_signers_bytes"
    ]
    for parameter in signature.parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.annotation == "bytes"


def test_signature_verifier_names_no_repository_artifact():
    """임시 디렉터리 밖의 경로를 문자열로도 갖고 있지 않다."""
    source = (PRODUCTION_DIR / "approval_signature.py").read_text(encoding="utf-8")
    assert "tempfile.TemporaryDirectory" in source
    tree = ast.parse(source, filename="approval_signature.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "/" in node.value:
                # 지문·지문 정규식만 '/' 를 담을 수 있다
                assert "SHA256:" in node.value, node.value


def test_orchestrator_reads_only_the_pinned_lock_path():
    """orchestrator 의 파일 읽기는 ★고정된 잠금 경로★ 뿐이다."""
    source = (PRODUCTION_DIR / "orchestrator.py").read_text(encoding="utf-8")
    reads = [line.strip() for line in source.splitlines() if "read_bytes" in line]
    assert reads == [
        "lock = lock_verifier.load_candidate_lock(lock_path.read_bytes())",
        "(root / anchors.CANDIDATE_LOCK_PATH).read_bytes()",
    ], reads
    assert "root / anchors.CANDIDATE_LOCK_PATH" in source


def test_approval_locations_are_pinned_constants():
    assert anchors.APPROVAL_REPOSITORY == "tristan00037-tristan050/butler-ct-shared"
    assert anchors.APPROVAL_PROTECTED_REF == "refs/heads/main"
    assert re.fullmatch(r"[0-9a-f]{40}", anchors.APPROVAL_COMMIT_SHA)
    assert re.fullmatch(r"[0-9a-f]{64}", anchors.APPROVAL_DOCUMENT_SHA256)
    assert anchors.APPROVAL_SIGNATURE_PATH == anchors.APPROVAL_DOCUMENT_PATH + ".sig"


def test_trust_anchor_takes_no_arguments():
    import inspect

    signature = inspect.signature(anchors.production_trust_anchor)
    assert signature.parameters == {}


# ── ② production CLI 에 경로 인자 금지 ────────────────────────────────
def test_cli_takes_no_values_at_all():
    """M-4 — 값은 인자가 아니라 env 로 온다. CLI 에는 경로도 좌표도 없다."""
    import argparse
    import io
    import contextlib

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), pytest.raises(SystemExit):
        orchestrator._main(["--help"])
    helptext = captured.getvalue()
    options = set(re.findall(r"--[a-z-]+", helptext))
    assert options == {"--help", "--mode"}, options
    assert not any(
        re.search(r"(path|file|dir|root|document|signers|signature|head|tree)", option)
        for option in options
    )
    assert argparse is not None


# ── ① workflow 가 픽스처를 읽지 않는다 ────────────────────────────────
def test_workflow_never_touches_the_test_fixtures():
    body = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("fixtures", "approval_document.md", "allowed_signers"):
        assert forbidden not in body, forbidden


def test_workflow_invokes_the_orchestrator():
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "ac25.orchestrator" in body


def test_workflow_declares_no_dispatch_inputs():
    """★R6-3 §6-5 — 좌표·PR 번호를 입력으로 노출하지 않는다."""
    workflow = _workflow()
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert triggers == {"workflow_dispatch": None}


def test_workflow_passes_no_path_arguments_to_the_orchestrator():
    body = WORKFLOW.read_text(encoding="utf-8")
    invocation = body.split("python3 -m ac25.orchestrator", 1)[1].split("STATUS=$?", 1)[0]
    assert "--lock-path" not in invocation
    assert "--repository-path" not in invocation
    assert "--document" not in invocation


# ── 워크플로 계약 ─────────────────────────────────────────────────────
def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_every_action_is_pinned_to_a_full_commit_sha():
    body = WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", body)
    assert uses, "actions 가 하나도 없다"
    for reference in uses:
        _, _, ref = reference.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", ref), reference


def test_unused_jsonschema_install_is_gone():
    assert "jsonschema" not in WORKFLOW.read_text(encoding="utf-8")


def test_two_credentials_are_configured_for_the_orchestrator_step():
    """★C5 — 단일 GH_TOKEN 이 아니라 두 credential 로 분리한다."""
    workflow = _workflow()
    steps = workflow["jobs"]["trusted-verification"]["steps"]
    orchestrate = next(step for step in steps if step.get("id") == "orchestrate")
    assert orchestrate["env"]["AC25_APPROVAL_TOKEN"].strip()
    assert orchestrate["env"]["AC25_CANDIDATE_TOKEN"].strip()
    assert "GH_TOKEN" not in orchestrate["env"]


def test_approval_token_is_exposed_only_to_protected_jobs():
    """승인 token 은 보호 environment 를 거치는 두 job 에만 노출한다(§6 · §6-5)."""
    body = WORKFLOW.read_text(encoding="utf-8")
    workflow = _workflow()
    allowed = {"token-preflight", "trusted-verification"}
    for name, job in workflow["jobs"].items():
        rendered = yaml.dump(job, allow_unicode=True)
        if name in allowed:
            assert "AC25_APPROVAL_READ_TOKEN" in rendered, name
        else:
            assert "AC25_APPROVAL_READ_TOKEN" not in rendered, name
    assert body.count("AC25_APPROVAL_READ_TOKEN") >= 1


def test_publish_depends_on_all_verification_jobs():
    workflow = _workflow()
    publish = workflow["jobs"]["publish-check"]
    assert set(publish["needs"]) == {
        "token-preflight", "trusted-verification", "candidate-lane", "integration-lane",
    }


def test_both_lanes_depend_on_preflight_and_trusted_verification():
    """사전점검·신뢰 검증이 실패하면 두 레인은 needs 로 자동 차단된다(§6-5)."""
    workflow = _workflow()
    for lane in ("candidate-lane", "integration-lane"):
        job = workflow["jobs"][lane]
        assert set(job["needs"]) == {"token-preflight", "trusted-verification"}
        # publish 와 달리 always() 를 갖지 않는다 — 선행 실패 시 돌면 안 된다
        assert "if" not in job


def test_lanes_run_checks_only_through_the_protected_runner():
    """★워크플로가 검사 명령을 조립하지 않는다(M-1 §5-3)."""
    workflow = _workflow()
    for lane in ("candidate-lane", "integration-lane"):
        script = "\n".join(
            step.get("run", "") for step in workflow["jobs"][lane]["steps"]
        )
        assert "stage_b_runner" in script, lane
        for forbidden in ("pip install", "pytest tests/", "vitest run"):
            assert forbidden not in script, (lane, forbidden)


def test_coverage_basis_stays_in_the_receipt():
    """조건 2(4차 라운드) — 근거 문장은 ★receipt★ 에 남는다.

    C6 이후 receipt 원문은 job output 으로 나가지 않으므로 check summary 가 아니라
    receipt 파일이 그 문장을 담는 자리다.
    """
    from ac25.designated_checks import COVERAGE_BASIS

    assert "static-reference" in COVERAGE_BASIS
    assert "실행 도달 증거가 아니" in COVERAGE_BASIS
    source = (PRODUCTION_DIR / "orchestrator.py").read_text(encoding="utf-8")
    assert '"coverage_basis": coverage.basis' in source


def test_coverage_gap_still_fails_the_run():
    """조건 1·3(4차 라운드) — 덮음 구멍은 여전히 전체 실패다."""
    source = (PRODUCTION_DIR / "orchestrator.py").read_text(encoding="utf-8")
    assert "DESIGNATED_CHECK_COVERAGE_GAP" in source
    assert "if not coverage.ok:" in source


def test_only_publish_job_can_write_checks():
    workflow = _workflow()
    for name, job in workflow["jobs"].items():
        permissions = job.get("permissions", {})
        if name == "publish-check":
            assert permissions.get("checks") == "write"
        else:
            assert "checks" not in permissions, name
