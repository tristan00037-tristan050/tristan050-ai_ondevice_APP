"""§5 R6-2 — 단계 B 좌표 단일 원본 시험(Python 측).

Node 측 시험은 publish_check.test.mjs 가 담당한다. 이 파일은 두 가지를 본다.

  ① Python loader 가 Node loader 와 ★같은 계약★ 을 강제하는가
  ② 기대 좌표가 저장소 어디에도 ★복제되지 않았는가★ (§5-1)

②가 이번 라운드의 핵심이다. 복제되면 한쪽만 고쳐지고, 그 순간 "영수증과 실제가
다름" 이 다시 생긴다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from ac25 import stage_b_coordinates as sbc

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = REPO_ROOT / "scripts" / "ci" / "ac25"
TEST_DIR = Path(__file__).resolve().parent
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

EXPECTED = sbc.load_coordinates()
STALE_PR904_TREE = "aa87b5fa82064fe651f90ab91222e8d74dcaa976"

_OID_LITERAL = re.compile(r"[0-9a-f]{40}")


def _valid_mapping(**overrides) -> dict:
    base = {
        "schema_version": sbc.SCHEMA_VERSION,
        "candidate_commit": EXPECTED.candidate_commit,
        "candidate_tree": EXPECTED.candidate_tree,
        "integration_base": EXPECTED.integration_base,
        "merge_commit": EXPECTED.merge_commit,
        "merge_tree": EXPECTED.merge_tree,
    }
    base.update(overrides)
    return base


# ══ ① loader 계약 ══════════════════════════════════════════════════════
def test_single_source_file_exists_and_is_canonical():
    raw = sbc.coordinate_path().read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    assert set(parsed) == {
        "schema_version", "candidate_commit", "candidate_tree",
        "integration_base", "merge_commit", "merge_tree",
    }
    assert sbc.canonical_bytes(parsed) == raw
    assert raw.endswith(b"}\n")


def test_loader_takes_no_path_argument():
    """부르는 쪽이 다른 파일을 가리킬 수 없다(§5-1)."""
    import inspect

    assert inspect.signature(sbc.load_coordinates).parameters == {}
    assert inspect.signature(sbc.coordinate_path).parameters == {}


def test_expected_merge_parents_order_is_base_then_candidate():
    assert EXPECTED.expected_merge_parents == (
        EXPECTED.integration_base, EXPECTED.candidate_commit
    )


@pytest.mark.parametrize(
    ("label", "raw"),
    [
        ("duplicate key", b'{\n  "schema_version": "x",\n  "schema_version": "y"\n}\n'),
        ("not json", b"nope"),
        ("array root", b"[]"),
        ("empty", b""),
        ("invalid utf-8", b'{"schema_version": "\xff"}'),
    ],
)
def test_malformed_source_is_rejected(label, raw):
    with pytest.raises(sbc.CoordinateContractError) as caught:
        sbc.load_from_bytes(raw)
    assert caught.value.code == sbc.STAGE_B_COORDINATE_CONTRACT_INVALID, label


def test_unknown_key_is_rejected():
    payload = sbc.canonical_bytes(_valid_mapping())
    broken = json.loads(payload.decode("utf-8"))
    broken["surprise"] = 1
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes((json.dumps(broken, indent=2) + "\n").encode("utf-8"))


def test_missing_key_is_rejected():
    mapping = _valid_mapping()
    del mapping["merge_tree"]
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes((json.dumps(mapping, indent=2) + "\n").encode("utf-8"))


@pytest.mark.parametrize("field", ["candidate_commit", "candidate_tree", "integration_base", "merge_commit", "merge_tree"])
@pytest.mark.parametrize("bad", ["0" * 40, "a" * 39, "a" * 41, "A" * 40, "z" * 40, ""])
def test_malformed_oid_in_source_is_rejected(field, bad):
    mapping = _valid_mapping(**{field: bad})
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes(sbc.canonical_bytes(mapping))


def test_non_canonical_spacing_is_rejected():
    compact = (json.dumps(_valid_mapping(), separators=(",", ":")) + "\n").encode("utf-8")
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes(compact)


def test_missing_trailing_newline_is_rejected():
    payload = sbc.canonical_bytes(_valid_mapping()).rstrip(b"\n")
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes(payload)


def test_reordered_keys_are_rejected():
    mapping = _valid_mapping()
    reordered = {key: mapping[key] for key in reversed(list(mapping))}
    payload = (json.dumps(reordered, indent=2) + "\n").encode("utf-8")
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes(payload)


def test_wrong_schema_version_is_rejected():
    with pytest.raises(sbc.CoordinateContractError):
        sbc.load_from_bytes(sbc.canonical_bytes(_valid_mapping(schema_version="v2")))


def test_source_digest_matches_the_file():
    raw = sbc.coordinate_path().read_bytes()
    assert sbc.coordinate_source_sha256() == hashlib.sha256(raw).hexdigest()


# ══ 생산 판정(Python 측) ═══════════════════════════════════════════════
def _observed(**overrides) -> dict:
    base = {
        "candidate_commit": EXPECTED.candidate_commit,
        "candidate_tree": EXPECTED.candidate_tree,
        "integration_base": EXPECTED.integration_base,
        "merge_commit": EXPECTED.merge_commit,
        "merge_tree": EXPECTED.merge_tree,
        "merge_parents": [EXPECTED.integration_base, EXPECTED.candidate_commit],
    }
    base.update(overrides)
    return base


def test_exact_match_passes():
    assert sbc.evaluate_observed(**_observed()) == ()


def test_stale_pr904_tree_fails():
    """감사 직접 증거 — aa87b5fa 로 통과하면 C2 가 다시 열린다."""
    codes = sbc.evaluate_observed(**_observed(candidate_tree=STALE_PR904_TREE))
    assert codes == (sbc.CANDIDATE_TREE_MISMATCH,)


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("candidate_commit", sbc.CANDIDATE_COMMIT_MISMATCH),
        ("candidate_tree", sbc.CANDIDATE_TREE_MISMATCH),
        ("integration_base", sbc.INTEGRATION_BASE_MISMATCH),
        ("merge_commit", sbc.MERGE_COMMIT_MISMATCH),
        ("merge_tree", sbc.MERGE_TREE_MISMATCH),
    ],
)
def test_one_nibble_change_fails_with_its_own_code(field, code):
    value = getattr(EXPECTED, field)
    flipped = value[:-1] + ("1" if value[-1] == "0" else "0")
    codes = sbc.evaluate_observed(**_observed(**{field: flipped}))
    assert code in codes


@pytest.mark.parametrize(
    ("parents", "code"),
    [
        ([EXPECTED.integration_base], sbc.MERGE_PARENT_COUNT_MISMATCH),
        ([], sbc.MERGE_PARENT_COUNT_MISMATCH),
        ("notalist", sbc.MERGE_PARENT_COUNT_MISMATCH),
        (
            [EXPECTED.integration_base, EXPECTED.candidate_commit, EXPECTED.merge_commit],
            sbc.MERGE_PARENT_COUNT_MISMATCH,
        ),
        (
            [EXPECTED.candidate_commit, EXPECTED.integration_base],
            sbc.MERGE_PARENT_ORDER_MISMATCH,
        ),
    ],
)
def test_merge_parent_violations(parents, code):
    codes = sbc.evaluate_observed(**_observed(merge_parents=parents))
    assert code in codes


def test_multiple_failures_come_back_in_the_declared_order():
    codes = sbc.evaluate_observed(**_observed(
        candidate_tree=STALE_PR904_TREE,
        merge_tree="f" * 40,
        merge_parents=[EXPECTED.candidate_commit, EXPECTED.integration_base],
    ))
    order = {code: index for index, code in enumerate(sbc.FAILURE_ORDER)}
    assert list(codes) == sorted(codes, key=lambda code: order[code])
    assert sbc.CANDIDATE_TREE_MISMATCH in codes and sbc.MERGE_TREE_MISMATCH in codes


def test_broken_contract_short_circuits_to_one_code():
    broken = sbc.StageBCoordinates(
        schema_version="", candidate_commit="", candidate_tree="",
        integration_base="", merge_commit="", merge_tree="",
    )
    codes = sbc.evaluate_observed(**_observed(), expected=broken)
    assert set(codes) <= set(sbc.FAILURE_ORDER)
    assert codes  # 빈 기대값으로 통과시키지 않는다


# ══ ② 기대 좌표 복제 0건 (§5-1 핵심) ══════════════════════════════════
def _coordinate_values() -> set[str]:
    return {
        EXPECTED.candidate_commit, EXPECTED.candidate_tree,
        EXPECTED.integration_base, EXPECTED.merge_commit, EXPECTED.merge_tree,
    }


def test_no_production_module_duplicates_the_expected_coordinates():
    """기대 좌표를 담은 파일은 단일 원본 JSON 하나뿐이다."""
    offenders: dict[str, set[str]] = {}
    for path in sorted(PRODUCTION_DIR.rglob("*")):
        if not path.is_file() or path.name == sbc.COORDINATE_FILENAME:
            continue
        if path.suffix not in (".py", ".mjs", ".js", ".json"):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        found = {value for value in _coordinate_values() if value in body}
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    # 후보 잠금(pr903_candidate_lock.json)은 이 디렉터리 밖이며 별도 계약이다.
    assert offenders == {}, offenders


def test_no_workflow_carries_stage_b_expected_coordinates():
    """workflow env·input 이 기대 좌표를 들고 있지 않다(§5-1 · §9-2)."""
    offenders: dict[str, set[str]] = {}
    for path in sorted(WORKFLOW_DIR.glob("box5-ac25-*.yml")):
        body = path.read_text(encoding="utf-8")
        found = {value for value in _coordinate_values() if value in body}
        if found:
            offenders[path.name] = found
    assert offenders == {}, offenders


def test_no_test_file_hardcodes_the_expected_coordinates():
    """시험도 loader 에서 읽는다. 시험이 복제하면 원본이 둘이 된다."""
    offenders: dict[str, set[str]] = {}
    for path in sorted(TEST_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".mjs", ".json"):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        found = {value for value in _coordinate_values() if value in body}
        if found:
            offenders[path.name] = found
    assert offenders == {}, offenders


def test_stale_coordinate_appears_only_as_a_regression_fixture():
    """과거 tree 는 ★실패해야 하는 값★ 으로만 등장한다."""
    holders = set()
    for root in (PRODUCTION_DIR, TEST_DIR, WORKFLOW_DIR):
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".mjs", ".yml", ".json"):
                continue
            if STALE_PR904_TREE in path.read_text(encoding="utf-8", errors="replace"):
                holders.add(path.name)
    assert holders == {"publish_check.test.mjs", "test_stage_b_coordinates.py"}, holders


def test_python_and_node_loaders_agree_on_the_key_order():
    node = (PRODUCTION_DIR / "stage_b_coordinates.mjs").read_text(encoding="utf-8")
    for key in (
        "schema_version", "candidate_commit", "candidate_tree",
        "integration_base", "merge_commit", "merge_tree",
    ):
        assert f"'{key}'" in node, key
    python_order = re.search(r"_KEY_ORDER = \((.*?)\)",
                             (PRODUCTION_DIR / "stage_b_coordinates.py").read_text(encoding="utf-8"),
                             re.S).group(1)
    node_order = re.search(r"const KEY_ORDER = Object\.freeze\(\[(.*?)\]\)", node, re.S).group(1)
    extract = lambda text: re.findall(r"[\"']([a-z_]+)[\"']", text)
    assert extract(python_order) == extract(node_order)


def test_node_loader_never_hardcodes_a_coordinate():
    body = (PRODUCTION_DIR / "stage_b_coordinates.mjs").read_text(encoding="utf-8")
    assert _OID_LITERAL.findall(body) == []


def test_python_loader_never_hardcodes_a_coordinate():
    body = (PRODUCTION_DIR / "stage_b_coordinates.py").read_text(encoding="utf-8")
    assert _OID_LITERAL.findall(body) == []
