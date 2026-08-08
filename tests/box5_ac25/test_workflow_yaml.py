"""stdlib 워크플로 파서가 PyYAML 과 ★같은 값을 내는가★.

왜 이 파서가 있는가
  F-04 canonical 추출은 신뢰 경로에서 돈다. PyYAML 에 의존한 판이 원격에서
  `ModuleNotFoundError: No module named 'yaml'` 로 죽었다. 실행되지 않는
  검증기는 검증기가 아니다.

왜 이 시험이 있는가
  손으로 쓴 파서는 ★조용히 틀리게 읽는 것★ 이 가장 위험하다. 그래서 저장소의
  ★모든 워크플로★ 를 두 파서로 읽어 결과가 완전히 같은지 대조한다.
  PyYAML 은 시험에만 있고 production 에는 없다.

  실제로 이 대조가 두 결함을 잡았다.
    · `1e-6` 을 float 으로 읽었다 (PyYAML 은 문자열로 둔다 — YAML 1.1 은
      지수부에 부호가 필수다)
    · `{python-version: '${{ env.X }}'}` 에서 인용 안의 중괄호를 중첩으로 오해했다
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml  # ★시험 전용. production 은 쓰지 않는다.
from ac25 import workflow_yaml as wy

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
PRODUCTION_DIR = REPO_ROOT / "scripts" / "ci" / "ac25"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


# ══ ★모든 워크플로에서 PyYAML 과 같은 값을 낸다 ════════════════════════
@pytest.mark.parametrize("path", WORKFLOWS, ids=[p.name for p in WORKFLOWS])
def test_matches_pyyaml_on_every_workflow(path):
    raw = path.read_text(encoding="utf-8")
    mine = wy.load_workflow(raw)
    theirs = yaml.safe_load(raw)
    # ★jobs 서브트리가 계획 추출이 쓰는 전부다. 그것이 정확히 같아야 한다.
    assert mine.get("jobs") == theirs.get("jobs"), path.name


def test_every_workflow_is_parsed_not_closed():
    """하나라도 닫히면 그 워크플로는 계획 추출 대상이 될 수 없다."""
    closed = []
    for path in WORKFLOWS:
        try:
            wy.load_workflow(path.read_text(encoding="utf-8"))
        except wy.WorkflowYamlError as exc:
            closed.append((path.name, exc.code, exc.line_number))
    assert closed == [], closed


def test_local_actions_match_pyyaml():
    actions = sorted((REPO_ROOT / ".github" / "actions").rglob("action.y*ml"))
    assert actions, "로컬 action 이 하나도 없다"
    for path in actions:
        raw = path.read_text(encoding="utf-8")
        assert wy.load_workflow(raw) == yaml.safe_load(raw), path


# ══ production 에 PyYAML 의존이 없다 ═══════════════════════════════════
def test_no_production_module_imports_yaml():
    """★이것이 원격 실패의 직접 원인이었다. 다시 들어오면 여기서 잡는다."""
    offenders = []
    for path in sorted(PRODUCTION_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{path.name}: {a.name}" for a in node.names if a.name == "yaml"]
            elif isinstance(node, ast.ImportFrom) and (node.module or "") == "yaml":
                offenders.append(f"{path.name}: from yaml")
    assert offenders == [], offenders


def test_canonical_plan_uses_the_stdlib_parser():
    source = (PRODUCTION_DIR / "canonical_plan.py").read_text(encoding="utf-8")
    assert "load_workflow" in source
    assert "yaml.safe_load" not in source


def test_parser_uses_only_the_standard_library():
    tree = ast.parse((PRODUCTION_DIR / "workflow_yaml.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"re", "dataclasses", "__future__"}, imported


# ══ 지원하지 않는 문법은 ★닫는다★ (조용히 틀리게 읽지 않는다) ══════════
@pytest.mark.parametrize(
    "text",
    [
        "a: &anchor value\nb: *anchor\n",       # 앵커·별칭
        "a: !!python/object x\n",                # 태그
        "--- \na: 1\n",                          # 복수 문서
        "a: [nested, [inner]]\n",                # 중첩 흐름
        "a: {outer: {inner: 1}}\n",              # 중첩 흐름 맵
    ],
)
def test_unsupported_syntax_is_closed(text):
    with pytest.raises(wy.WorkflowYamlError):
        wy.load_workflow(text)


@pytest.mark.parametrize("text", ["", "   \n\n", "\ta: 1\n", "novalue\n"])
def test_malformed_input_is_closed(text):
    with pytest.raises(wy.WorkflowYamlError):
        wy.load_workflow(text)


def test_error_carries_only_a_code_and_line():
    with pytest.raises(wy.WorkflowYamlError) as caught:
        wy.load_workflow("a: &x 1\n")
    assert caught.value.code == wy.WORKFLOW_YAML_UNSUPPORTED
    assert caught.value.line_number == 1
    assert "&" not in str(caught.value)


# ══ 스칼라 해석이 PyYAML 과 같다 ═══════════════════════════════════════
@pytest.mark.parametrize(
    "literal",
    [
        "1", "0", "-3", "3.14", "1e-6", "1.0e-6", ".5", "0x1F", "0o17", "010",
        "true", "false", "True", "yes", "no", "on", "off", "null", "~",
        "'1'", '"1"', "'true'", '"true"', "plain text", "a#b", '"2026-08-06"',
        "ubuntu-24.04", "3.11", "v1.2.3", "postgres://u:p@localhost:5432/app",
    ],
)
def test_scalar_typing_matches_pyyaml(literal):
    text = f"key: {literal}\n"
    assert wy.load_workflow(text) == yaml.safe_load(text), literal


@pytest.mark.parametrize(
    "text",
    [
        "key: |\n  line one\n  line two\n",
        "key: |-\n  no trailing newline\n",
        "key: >\n  folded one\n  folded two\n",
        "key: >-\n  folded stripped\n",
    ],
)
def test_block_scalars_match_pyyaml(text):
    assert wy.load_workflow(text) == yaml.safe_load(text), text


@pytest.mark.parametrize(
    "text",
    [
        "needs: [a, b]\n",
        "with: {fetch-depth: 0}\n",
        "with: {python-version: '3.11'}\n",
        "needs: []\n",
    ],
)
def test_flow_collections_match_pyyaml(text):
    assert wy.load_workflow(text) == yaml.safe_load(text), text


@pytest.mark.parametrize("literal", ["2026-08-06", "2026-8-6", "2026-08-06T10:00:00Z"])
def test_unquoted_dates_are_closed_not_guessed(literal):
    """PyYAML 은 이것을 date 객체로 읽는다. 흉내내지 않고 ★닫는다★.

    문자열로 조용히 읽으면 두 파서가 다른 값을 내고, 그 사실을 아무도 모른다.
    인용하면(`"2026-08-06"`) 문자열로 정상 처리된다.
    """
    with pytest.raises(wy.WorkflowYamlError) as caught:
        wy.load_workflow(f"key: {literal}\n")
    assert caught.value.code == wy.WORKFLOW_YAML_UNSUPPORTED


def test_quoted_dates_are_plain_strings():
    text = 'key: "2026-08-06"\n'
    assert wy.load_workflow(text) == yaml.safe_load(text) == {"key": "2026-08-06"}


def test_expression_braces_inside_quotes_are_not_nesting():
    """`${{ }}` 는 값이다. 중첩 흐름으로 오해하면 정상 워크플로가 닫힌다."""
    text = "with: {python-version: '${{ env.PYTHON_VERSION }}'}\n"
    assert wy.load_workflow(text) == yaml.safe_load(text)


def test_comment_inside_quotes_is_kept():
    text = 'key: "value # not a comment"\n'
    assert wy.load_workflow(text) == yaml.safe_load(text)


def test_trailing_comment_is_removed():
    text = "key: value   # this is a comment\n"
    assert wy.load_workflow(text) == yaml.safe_load(text)


# ══ 계획 추출 결과가 파서 교체 전후로 같다 ═════════════════════════════
def test_canonical_extraction_still_works_without_pyyaml(monkeypatch):
    """★PyYAML 을 import 할 수 없게 만들어도 추출이 된다.

    원격에서 죽은 그 상황을 그대로 재현한다.
    """
    import builtins

    from ac25 import canonical_plan as cp

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "yaml" or name.startswith("yaml."):
            raise ModuleNotFoundError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    plan = cp.extract_canonical_plan(REPO_ROOT, runner_temp="/runner/temp")
    assert len(plan.preparation) == 10
    assert len(plan.contract_env) == 7
    assert plan.contract_argv == ("bash", cp.CONTRACT_SCRIPT)
