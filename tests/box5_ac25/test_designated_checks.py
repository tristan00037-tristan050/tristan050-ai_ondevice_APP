"""지정 후보 검사의 유도와 덮음 계약 시험 (총괄 결정 = 갑, 조건 1·2·3).

조건 1  22/22 덮임을 계약으로 강제한다. 우연히 덮이는 것을 믿지 않는다.
조건 2  판정 근거가 정적 참조이고 실행 도달 증거가 아님을 영수증에 적는다.
조건 3  세 항목 중 하나라도 참조가 끊기면 실패로 떨어진다.

실제 잠금 파일을 그대로 쓴다(저장소 안에 있으므로 네트워크가 필요 없다).
후보 원문은 주입한다 — 후보 코드를 실행하지 않는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ac25 import anchors, designated_checks as dc, lock_verifier

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = lock_verifier.load_candidate_lock(
    (REPO_ROOT / anchors.CANDIDATE_LOCK_PATH).read_bytes()
)

# 잠금 tests 항목 중 직접 선택되지 않는 셋(도우미 1 · 자료 2)
TESTKIT = "tests/accounting/assignment/authorization_testkit.py"
MUTATIONS = "tests/fixtures/box5_ac11_schema_mutations_v1.json"
GOLDEN = "tests/fixtures/box5_ua2_golden_v1.json"
INDIRECT = (TESTKIT, MUTATIONS, GOLDEN)

# 후보 head 실측으로 확인한 참조 관계(2026-08-05, 61ba1bf4)
REFERENCES = {
    "tests/accounting/assignment/test_assignment_api.py": [TESTKIT],
    "tests/accounting/assignment/test_authorization_product_route.py": [TESTKIT],
    "tests/accounting/assignment/test_authorization_replay_round3.py": [MUTATIONS],
    "tests/accounting/assignment/test_authorization_wire_round3.py": [GOLDEN],
}


def make_reader(references: dict[str, list[str]], *, unreadable: tuple[str, ...] = ()):
    """선택된 검사 원문을 흉내낸다. 참조 대상의 어간을 본문에 심는다."""

    def read(path: str) -> bytes | None:
        if path in unreadable:
            return None
        tokens = [dc._reference_token(target) for target in references.get(path, [])]
        body = "import pytest\n" + "".join(f"# uses {token}\n" for token in tokens)
        return body.encode("utf-8")

    return read


# ══ 유도 규칙이 실제 잠금에서 뽑는 것 ═══════════════════════════════════
def test_real_lock_has_no_folder_entries():
    """총괄 전제 확인 — 이 잠금에는 폴더/글로브 항목이 없다."""
    assert not any(
        any(character in path for character in "*?[") for path in LOCK.allowed_paths
    )
    assert len(LOCK.allowed_paths) == 92


def test_real_lock_yields_nineteen_python_and_two_js():
    """★합성 픽스처가 아니라 실제 잠금 기준 수치다."""
    python = dc.designated_python_tests(LOCK)
    js = dc.designated_js_tests(LOCK)
    assert len(python) == 19, python
    assert js == [
        "butler-desktop/src/__tests__/AccountingReviewPage.test.tsx",
        "butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.test.ts",
    ]


def test_lock_has_twenty_two_test_entries():
    assert len(dc.lock_test_entries(LOCK)) == 22


def test_the_three_indirect_entries_are_exactly_these():
    selected = set(dc.designated_python_tests(LOCK))
    remainder = [e for e in dc.lock_test_entries(LOCK) if e not in selected]
    assert remainder == sorted(INDIRECT)


# ══ 조건 1 · 22/22 덮임 계약 ═══════════════════════════════════════════
def test_all_twenty_two_entries_are_covered():
    report = dc.verify_designated_coverage(lock=LOCK, read_blob=make_reader(REFERENCES))
    assert report.ok
    assert report.uncovered == ()
    assert report.unreadable == ()
    covered = len(report.directly_selected) + len(report.indirectly_covered)
    assert covered == len(report.lock_test_entries) == 22


def test_indirect_entries_record_who_refers_to_them():
    report = dc.verify_designated_coverage(lock=LOCK, read_blob=make_reader(REFERENCES))
    assert set(report.indirectly_covered) == set(INDIRECT)
    assert report.indirectly_covered[TESTKIT] == (
        "tests/accounting/assignment/test_assignment_api.py",
        "tests/accounting/assignment/test_authorization_product_route.py",
    )
    assert report.indirectly_covered[MUTATIONS] == (
        "tests/accounting/assignment/test_authorization_replay_round3.py",
    )
    assert report.indirectly_covered[GOLDEN] == (
        "tests/accounting/assignment/test_authorization_wire_round3.py",
    )


# ══ 조건 3 · 참조가 끊기면 실패 ════════════════════════════════════════
@pytest.mark.parametrize("dropped", INDIRECT)
def test_breaking_any_single_reference_fails(dropped):
    """세 항목 중 ★하나라도★ 참조가 끊기면 덮임이 깨진다."""
    weakened = {
        source: [t for t in targets if t != dropped]
        for source, targets in REFERENCES.items()
    }
    report = dc.verify_designated_coverage(lock=LOCK, read_blob=make_reader(weakened))
    assert not report.ok
    assert report.uncovered == (dropped,)


def test_unreadable_selected_test_is_fail_closed():
    """원문을 못 읽으면 덮였다고 보지 않는다 — 증명 못 한 것은 통과가 아니다."""
    report = dc.verify_designated_coverage(
        lock=LOCK,
        read_blob=make_reader(
            REFERENCES,
            unreadable=("tests/accounting/assignment/test_assignment_api.py",),
        ),
    )
    assert not report.ok
    assert report.unreadable == ("tests/accounting/assignment/test_assignment_api.py",)


def test_no_references_at_all_leaves_all_three_uncovered():
    report = dc.verify_designated_coverage(lock=LOCK, read_blob=make_reader({}))
    assert not report.ok
    assert report.uncovered == tuple(sorted(INDIRECT))


def test_directly_selected_entries_never_need_a_reference():
    report = dc.verify_designated_coverage(lock=LOCK, read_blob=make_reader({}))
    for entry in report.directly_selected:
        assert entry not in report.uncovered


# ══ 조건 2 · 근거를 영수증에 그대로 적는다 ═════════════════════════════
def test_basis_states_static_reference_not_execution():
    assert "static-reference" in dc.COVERAGE_BASIS
    assert "실행 도달 증거가 아니" in dc.COVERAGE_BASIS
    assert "coverage 측정이 아니" in dc.COVERAGE_BASIS


def test_receipt_carries_the_basis_verbatim():
    report = dc.verify_designated_coverage(lock=LOCK, read_blob=make_reader(REFERENCES))
    receipt = report.as_receipt()
    assert receipt["basis"] == dc.COVERAGE_BASIS
    assert receipt["lock_test_entry_count"] == 22
    assert receipt["covered_count"] == 22
    assert receipt["uncovered"] == []


def test_receipt_never_claims_coverage_measurement():
    receipt = dc.verify_designated_coverage(
        lock=LOCK, read_blob=make_reader(REFERENCES)
    ).as_receipt()
    # coverage 로 읽히는 낱말을 근거 문장 밖에서 쓰지 않는다
    assert "coverage" not in {key for key in receipt if key != "basis"}


# ══ 우연한 일치 차단 ═══════════════════════════════════════════════════
def test_short_tokens_are_not_accepted_as_references():
    """짧은 이름은 우연히 걸린다. 덮였다고 보지 않는다."""
    assert dc._MIN_TOKEN_LENGTH >= 8


def test_reference_token_is_the_module_or_file_stem():
    assert dc._reference_token(TESTKIT) == "authorization_testkit"
    assert dc._reference_token(MUTATIONS) == "box5_ac11_schema_mutations_v1"
    assert dc._reference_token(GOLDEN) == "box5_ua2_golden_v1"
