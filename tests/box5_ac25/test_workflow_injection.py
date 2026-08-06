"""§15 M-4 — script injection 공격 payload 시험.

검증기를 실행하는 사람이 입력에 명령을 심을 수 있다면, M-2 로 막으려던 것이
입구에서 뚫린다.

★payload 는 실행되지 않고 INPUT_* 오류 코드로 끝나야 한다.
★워크플로 원문에도 직접 표현식이 남아 있으면 안 된다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from ac25 import workflow_inputs as wi

# ★R6-2 §5-1 — 좌표를 이 시험이 다시 적지 않는다. 보호된 단일 원본에서 읽는다.
from ac25 import stage_b_coordinates as _sbc  # noqa: E402

_COORDINATES = _sbc.load_trusted_coordinates()

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
TRUSTED = WORKFLOW_DIR / "box5-ac25-trusted-verification.yml"
SMOKE = WORKFLOW_DIR / "box5-ac25-stage-a-smoke.yml"
AC25_WORKFLOWS = (TRUSTED, SMOKE)

HEAD = _COORDINATES.stage_b.candidate_commit
TREE = _COORDINATES.stage_b.candidate_tree

# 공격 payload — §8 이 나열한 일곱 형태
PAYLOADS = [
    pytest.param(f"$(id)", id="command-substitution"),
    pytest.param(f"`id`", id="backtick-substitution"),
    pytest.param(f"{HEAD}$(id)", id="oid-then-substitution"),
    pytest.param(f'{HEAD}"; id; echo "', id="quote-break-then-command"),
    pytest.param(f"{HEAD}; id", id="semicolon-command"),
    pytest.param(f"{HEAD} && id", id="and-command"),
    pytest.param(f"{HEAD}|id", id="pipe-command"),
    pytest.param(f"{HEAD}\nid", id="newline-command"),
    pytest.param(f"{HEAD}\n::set-output name=x::y", id="workflow-command"),
    pytest.param(f"{HEAD}\n::error::pwned", id="workflow-error-command"),
    pytest.param("$IFS$(id)", id="field-separator"),
    pytest.param("61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd0а", id="non-ascii-cyrillic-a"),
    pytest.param("61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd0​4", id="zero-width-space"),
    pytest.param(f"{HEAD}\r\nid", id="crlf-command"),
    pytest.param("--upload-pack=id", id="git-option-injection"),
    pytest.param("refs/heads/main:refs/heads/main", id="refspec"),
]


def _validate(**overrides):
    values = {
        "pr_number": "903",
        "expected_head": HEAD,
        "expected_tree": TREE,
        "run_id": "1",
        "repository": wi.EXPECTED_REPOSITORY,
        "ref": wi.EXPECTED_REF,
        "event_name": "workflow_dispatch",
        "locked_head": HEAD,
        "locked_tree": TREE,
    }
    values.update(overrides)
    return wi.validate_dispatch_inputs(**values)


# ══ payload 가 어느 칸에 들어와도 코드로 닫힌다 ════════════════════════
@pytest.mark.parametrize("payload", PAYLOADS)
def test_payload_in_head_is_rejected(payload):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(expected_head=payload)
    assert caught.value.code.startswith("INPUT_")


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payload_in_tree_is_rejected(payload):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(expected_tree=payload)
    assert caught.value.code.startswith("INPUT_")


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payload_in_pr_number_is_rejected(payload):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(pr_number=payload)
    assert caught.value.code == wi.INPUT_PR_NUMBER_MISMATCH


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payload_in_run_id_is_rejected(payload):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(run_id=payload)
    assert caught.value.code == wi.INPUT_RUN_ID_MALFORMED


def test_no_payload_is_ever_executed(monkeypatch):
    """★검증 과정에서 하위 프로세스를 만들지 않는다."""
    import subprocess

    def forbidden(*args, **kwargs):  # pragma: no cover - 불려서는 안 된다
        raise AssertionError("검증 중에 하위 프로세스를 만들었다")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for payload in ("$(id)", "`id`", f"{HEAD}; id"):
        with pytest.raises(wi.WorkflowInputError):
            _validate(expected_head=payload)


# ══ 워크플로 원문 계약 ═════════════════════════════════════════════════
def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run_blocks(path: Path):
    for job_name, job in _workflow(path)["jobs"].items():
        for step in job.get("steps", []):
            if "run" in step:
                yield job_name, step.get("name", "?"), step["run"]


@pytest.mark.parametrize("path", AC25_WORKFLOWS, ids=lambda p: p.name)
def test_no_direct_input_expression_in_run_blocks(path):
    """★run 본문에 inputs·github.event.inputs·needs output 표현식 0."""
    pattern = re.compile(r"\$\{\{\s*(inputs|github\.event\.inputs|needs)\b")
    offenders = [
        (job, name) for job, name, body in _run_blocks(path) if pattern.search(body)
    ]
    assert offenders == [], offenders


@pytest.mark.parametrize("path", AC25_WORKFLOWS, ids=lambda p: p.name)
def test_no_eval_or_dynamic_shell(path):
    body = path.read_text(encoding="utf-8")
    for forbidden in ("eval ", "bash -c", "sh -c", "shell=True", "os.system"):
        assert forbidden not in body, forbidden


@pytest.mark.parametrize("path", AC25_WORKFLOWS, ids=lambda p: p.name)
def test_no_dynamic_refspec(path):
    """동적 문자열 git refspec 금지 — fetch 대상은 고정 상수여야 한다."""
    for _job, _name, run in _run_blocks(path):
        for line in run.splitlines():
            if "git fetch" in line:
                assert "${{" not in line, line


def test_no_user_supplied_coordinate_reaches_python():
    """§6-5 R6-3 — 좌표·PR 번호를 사용자 입력으로 받는 경로가 남아 있지 않다.

    이전 판은 workflow_dispatch inputs 를 env(AC25_PR_NUMBER 등)로 넘겼다.
    그 값을 바꾸면 검증 대상을 바꿀 수 있으므로 입력 자체를 없앴다.
    """
    workflow = _workflow(TRUSTED)
    body = TRUSTED.read_text(encoding="utf-8")
    on_block = workflow[True] if True in workflow else workflow.get("on")
    assert on_block == {"workflow_dispatch": None}, on_block

    for forbidden in ("AC25_PR_NUMBER", "AC25_EXPECTED_HEAD", "AC25_EXPECTED_TREE",
                      "inputs.pr_number", "inputs.expected_head", "inputs.expected_tree"):
        assert forbidden not in body, forbidden

    steps = workflow["jobs"]["trusted-verification"]["steps"]
    orchestrate = next(step for step in steps if step.get("id") == "orchestrate")
    assert "${{" not in orchestrate["run"]
    # 남은 env 는 credential 과 Python 설정뿐이다
    assert set(orchestrate["env"]) == {
        "PYTHONPATH", "PYTHONNOUSERSITE", "AC25_APPROVAL_TOKEN", "AC25_CANDIDATE_TOKEN",
    }


def test_coordinates_come_from_the_protected_step_output():
    """좌표는 보호된 코드가 낸 step output 으로만 흐른다(§5-1)."""
    workflow = _workflow(TRUSTED)
    steps = workflow["jobs"]["trusted-verification"]["steps"]
    resolve = next(step for step in steps if step.get("id") == "coordinates")
    assert "ac25.stage_b_coordinates" in resolve["run"]
    assert "--emit-github-output" in resolve["run"]

    lane = workflow["jobs"]["candidate-lane"]["steps"]
    checkout = next(
        step for step in lane
        if step.get("with", {}).get("path") == "ac25-worktree"
    )
    assert checkout["with"]["ref"] == (
        "${{ needs.trusted-verification.outputs.coordinate_candidate_commit }}"
    )


def _publish_script_step() -> dict:
    steps = _workflow(TRUSTED)["jobs"]["publish-check"]["steps"]
    return next(step for step in steps if "script" in step.get("with", {}))


def test_github_script_receives_values_through_env_not_source():
    """★job output 을 JavaScript 소스에 직접 삽입하지 않는다."""
    step = _publish_script_step()
    script = step["with"]["script"]
    assert "${{" not in script, "script 본문에 표현식이 삽입돼 있다"
    # 값은 전부 env 로만 들어온다
    assert "process.env" in script
    assert all(key.startswith("AC25_") for key in step["env"])


def test_github_script_delegates_judgement_to_the_protected_module():
    """판정 로직을 inline 문자열로 두지 않는다. 보호된 모듈이 한다(C3)."""
    script = _publish_script_step()["with"]["script"]
    assert "publish_check.mjs" in script
    assert "pathToFileURL" in script
    # inline 에서 결론을 계산하지 않는다
    assert "conclusion" not in script
    assert "checks.create" not in script


def test_shell_true_count_is_zero_in_production_modules():
    production = REPO_ROOT / "scripts" / "ci" / "ac25"
    for path in sorted(production.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "shell=True" not in source, path.name
        assert "os.system(" not in source, path.name
