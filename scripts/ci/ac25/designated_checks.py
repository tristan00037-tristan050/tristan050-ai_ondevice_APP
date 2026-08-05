"""지정 후보 검사의 유도와 ★덮음 계약.

총괄기획1팀 결정(2026-08-05) = 갑.
  후보 검사 범위는 잠금 allowed_paths 안에 머문다. 폴더 단위로 넓히지 않는다.
  폴더로 넓히면 tests 루트가 잡혀 잠금 밖 400여 개가 딸려 오고, 승인받지 않은
  영역의 검사가 AC-25 판정을 막게 된다 — 잠금이 정한 경계를 검사 단계에서
  되돌리는 일이다.

  대신 ★덮는 범위★ 를 계약으로 강제한다. 잠금의 tests 항목은 전부 덮여야 한다.
  직접 선택되거나, 선택된 검사가 실제로 참조하거나 둘 중 하나다.

★★ 덮음 판정의 근거와 한계 (조건 2) ★★
  이 모듈의 판정 근거는 ★선택된 검사 원문에 대한 정적 문자열 참조★ 다.
  ★실행 도달 증거가 아니다. coverage 측정이 아니다.
  참조가 있다는 것은 그 파일이 import 되거나 이름이 적혀 있다는 뜻일 뿐,
  그 코드 경로가 실행 중에 도달한다는 뜻이 아니다. 영수증에 이 문장을 그대로
  싣는다. 읽는 사람이 coverage 로 오해하면 안 된다.

  후보 코드를 실행하지 않는다. 원문 바이트를 읽어 문자열을 찾을 뿐이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

DESIGNATED_CHECK_COVERAGE_GAP = "DESIGNATED_CHECK_COVERAGE_GAP"

# ★영수증에 그대로 실리는 문장. 줄이거나 부드럽게 고치지 말 것.
COVERAGE_BASIS = (
    "static-reference: 선택된 검사 원문에 대한 정적 문자열 참조로만 판정했다. "
    "★실행 도달 증거가 아니며 coverage 측정이 아니다. "
    "참조가 있다는 것은 이름이 적혀 있다는 뜻일 뿐, 그 경로가 실행 중에 "
    "도달한다는 뜻이 아니다."
)

_TESTS_PREFIX = "tests/"

# 참조 토큰이 너무 짧으면 우연히 걸린다. 이보다 짧은 이름은 덮였다고 보지 않는다.
_MIN_TOKEN_LENGTH = 8

BlobReader = Callable[[str], "bytes | None"]


@dataclass(frozen=True)
class CoverageReport:
    basis: str
    lock_test_entries: tuple[str, ...]
    directly_selected: tuple[str, ...]
    indirectly_covered: dict[str, tuple[str, ...]]
    uncovered: tuple[str, ...]
    unreadable: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.uncovered and not self.unreadable

    def as_receipt(self) -> dict:
        return {
            "basis": self.basis,
            "lock_test_entry_count": len(self.lock_test_entries),
            "covered_count": len(self.directly_selected) + len(self.indirectly_covered),
            "directly_selected": list(self.directly_selected),
            "indirectly_covered": {
                entry: list(referrers)
                for entry, referrers in sorted(self.indirectly_covered.items())
            },
            "uncovered": list(self.uncovered),
            "unreadable": list(self.unreadable),
        }


def designated_python_tests(lock) -> list[str]:
    """잠금 허용목록에서 유도한 후보 Python 검사 목록."""
    return sorted(
        path for path in lock.allowed_paths
        if path.startswith(_TESTS_PREFIX)
        and path.endswith(".py")
        and path.rsplit("/", 1)[-1].startswith("test_")
    )


def designated_js_tests(lock) -> list[str]:
    """잠금 허용목록에서 유도한 후보 JS/TS 검사 목록."""
    return sorted(
        path for path in lock.allowed_paths if path.endswith((".test.ts", ".test.tsx"))
    )


def lock_test_entries(lock) -> list[str]:
    """잠금이 승인한 tests 항목 전부. 덮음의 분모다."""
    return sorted(path for path in lock.allowed_paths if path.startswith(_TESTS_PREFIX))


def _reference_token(path: str) -> str:
    """항목을 가리키는 검색 토큰. .py 는 모듈명, 그 밖은 파일명 어간."""
    basename = path.rsplit("/", 1)[-1]
    stem = basename[: -len(".py")] if basename.endswith(".py") else basename
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return stem


def verify_designated_coverage(*, lock, read_blob: BlobReader) -> CoverageReport:
    """잠금의 tests 항목이 전부 덮이는지 판정한다.

    read_blob 은 후보 head 의 원문 바이트를 돌려준다. 읽지 못하면 덮였다고
    보지 않는다(fail-closed) — 증명하지 못한 것은 통과가 아니다.
    """
    entries = tuple(lock_test_entries(lock))
    selected = tuple(designated_python_tests(lock))
    selected_set = set(selected)

    sources: dict[str, str] = {}
    unreadable: list[str] = []
    for path in selected:
        blob = read_blob(path)
        if blob is None:
            unreadable.append(path)
            continue
        sources[path] = blob.decode("utf-8", errors="replace")

    indirect: dict[str, tuple[str, ...]] = {}
    uncovered: list[str] = []
    for entry in entries:
        if entry in selected_set:
            continue
        token = _reference_token(entry)
        if len(token) < _MIN_TOKEN_LENGTH:
            uncovered.append(entry)
            continue
        referrers = tuple(
            sorted(path for path, source in sources.items() if token in source)
        )
        if referrers:
            indirect[entry] = referrers
        else:
            uncovered.append(entry)

    return CoverageReport(
        basis=COVERAGE_BASIS,
        lock_test_entries=entries,
        directly_selected=selected,
        indirectly_covered=indirect,
        uncovered=tuple(uncovered),
        unreadable=tuple(unreadable),
    )


__all__ = [
    "COVERAGE_BASIS",
    "DESIGNATED_CHECK_COVERAGE_GAP",
    "BlobReader",
    "CoverageReport",
    "designated_js_tests",
    "designated_python_tests",
    "lock_test_entries",
    "verify_designated_coverage",
]
