"""§5-1 M-1 — 단계 B dependency manifest 와 실제 설치 명령의 결속.

감사가 잡은 것: 두 레인이 `-r requirements.txt` 를 설치 대상으로 불렀는데 그
파일은 저장소에 없다. 그런데 CI 57개가 전부 초록이었다 — 다른 job 이 먼저
해시 고정 lock 을 깔아 두어 우연히 넘어간 것이다.

★초록은 "검사했다"가 아니라 "그 검사가 본 것만 맞았다"는 뜻이다.

이 모듈은 시험이 실제로 필요로 하는 배포(distribution)를 AST 로 전수 조사해
manifest 가 그것을 전부 담고 있는지 확인한다. 담지 못하면 닫는다.
모든 설치 항목은 정확한 version 과 sha256 hash 를 가져야 한다.
"""
from __future__ import annotations

import ast
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 실재하는 해시 고정 manifest. requirements.txt 는 저장소에 없다.
MANIFEST_CANDIDATES = ("requirements-firstscreen-ci.lock",)

# import 이름 → 배포 이름. 자동 유추하지 않는다(yaml → PyYAML 은 유추 불가).
IMPORT_TO_DISTRIBUTION = {
    "pytest": "pytest",
    "yaml": "PyYAML",
}

# 저장소 내부 패키지. 외부 배포로 세지 않는다.
INTERNAL_ROOTS = frozenset({
    "ac25", "scripts", "tests", "tools",
    "butler_pc_core", "butler_sidecar", "butler_desktop",
})

# ── 오류 코드 (§5-1) ───────────────────────────────────────────────────
STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND = "STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND"
STAGE_B_DEPENDENCY_MANIFEST_AMBIGUOUS = "STAGE_B_DEPENDENCY_MANIFEST_AMBIGUOUS"
STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED = "STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED"
STAGE_B_DEPENDENCY_MANIFEST_INCOMPLETE = "STAGE_B_DEPENDENCY_MANIFEST_INCOMPLETE"
STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED = "STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED"
STAGE_B_IMPORT_DISTRIBUTION_UNMAPPED = "STAGE_B_IMPORT_DISTRIBUTION_UNMAPPED"

# 설치 항목으로 받아들이지 않는 형태
_REJECTED_PREFIXES = ("-e", "--editable", "--extra-index-url", "--find-links", "-f", "-r", "--requirement")
_REJECTED_SCHEMES = ("http://", "https://", "git+", "hg+", "svn+", "bzr+", "file://")

_PINNED_RE = re.compile(r"\A(?P<name>[A-Za-z0-9._-]+)\s*==\s*(?P<version>[^\s;]+)\s*\Z")
_HASH_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}")
_NORMALIZE_RE = re.compile(r"[-_.]+")


class DependencyManifestError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ResolvedManifest:
    relative_path: str
    sha256: str
    distributions: frozenset[str]
    required_distributions: frozenset[str]
    missing_distributions: frozenset[str]
    hash_pinned: bool


def normalize(name: str) -> str:
    """PEP 503 정규화."""
    return _NORMALIZE_RE.sub("-", name).lower()


def _stdlib_roots() -> frozenset[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names is None:  # pragma: no cover - 3.10 미만 방어
        raise DependencyManifestError(
            STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED,
            "sys.stdlib_module_names 없음(Python 3.10+ 필요)",
        )
    return frozenset(names)


def external_imports(test_root: Path) -> frozenset[str]:
    """시험 트리를 AST 로 전수 조사해 외부 import 최상위 이름을 모은다."""
    stdlib = _stdlib_roots()
    found: set[str] = set()
    for path in sorted(test_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except SyntaxError as exc:
            raise DependencyManifestError(
                STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED, f"{path.name}: {exc}"
            ) from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # 상대 import 는 내부다
                    continue
                if node.module:
                    found.add(node.module.split(".")[0])
    return frozenset(
        name for name in found if name not in stdlib and name not in INTERNAL_ROOTS
    )


def required_distributions(test_root: Path) -> frozenset[str]:
    """외부 import 를 배포 이름으로 옮긴다. 옮기지 못하면 닫는다."""
    unmapped = sorted(
        name for name in external_imports(test_root) if name not in IMPORT_TO_DISTRIBUTION
    )
    if unmapped:
        raise DependencyManifestError(
            STAGE_B_IMPORT_DISTRIBUTION_UNMAPPED, ",".join(unmapped)
        )
    return frozenset(
        normalize(IMPORT_TO_DISTRIBUTION[name]) for name in external_imports(test_root)
    )


def _logical_lines(text: str) -> list[str]:
    """continuation(\\) 을 이어 붙인 논리 줄. 주석은 제거한다."""
    joined = text.replace("\\\n", " ")
    lines: list[str] = []
    for raw in joined.splitlines():
        without_comment = raw.split("#", 1)[0]
        stripped = without_comment.strip()
        if stripped:
            lines.append(stripped)
    return lines


def parse_manifest(text: str) -> tuple[frozenset[str], bool]:
    """설치 항목의 배포 이름 집합과 hash 고정 여부를 돌려준다."""
    distributions: set[str] = set()
    for line in _logical_lines(text):
        lowered = line.lower()
        first = line.split()[0]
        if first.startswith("-"):
            if any(first == prefix or first.startswith(prefix + "=") for prefix in _REJECTED_PREFIXES):
                raise DependencyManifestError(
                    STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED, f"허용하지 않는 지시자: {first}"
                )
            raise DependencyManifestError(
                STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED, f"알 수 없는 지시자: {first}"
            )
        if any(scheme in lowered for scheme in _REJECTED_SCHEMES):
            raise DependencyManifestError(
                STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED, "URL·VCS·file 참조 금지"
            )
        hashes = _HASH_RE.findall(line)
        requirement = _HASH_RE.sub("", line).strip()
        # environment marker 는 떼어 낸다(설치 여부만 좌우한다)
        requirement = requirement.split(";", 1)[0].strip()
        if requirement.startswith(("./", "../", "/")) or requirement.endswith((".whl", ".tar.gz")):
            raise DependencyManifestError(
                STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED, "local path 참조 금지"
            )
        match = _PINNED_RE.match(requirement)
        if match is None:
            raise DependencyManifestError(
                STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED, f"version 미고정: {requirement[:60]}"
            )
        if not hashes:
            raise DependencyManifestError(
                STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED,
                f"hash 누락: {match.group('name')}",
            )
        distributions.add(normalize(match.group("name")))
    if not distributions:
        raise DependencyManifestError(
            STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED, "설치 항목이 하나도 없다"
        )
    # 여기 도달했다면 모든 항목이 version·hash 고정이다(아니면 위에서 닫혔다)
    return frozenset(distributions), True


def resolve_manifest(*, repo_root: Path, test_root: Path) -> ResolvedManifest:
    """manifest 를 찾아 읽고, 시험이 필요로 하는 배포를 전부 담는지 확인한다."""
    present = [name for name in MANIFEST_CANDIDATES if (repo_root / name).is_file()]
    if not present:
        raise DependencyManifestError(
            STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND, ",".join(MANIFEST_CANDIDATES)
        )
    if len(present) > 1:
        raise DependencyManifestError(
            STAGE_B_DEPENDENCY_MANIFEST_AMBIGUOUS, ",".join(present)
        )

    relative = present[0]
    raw = (repo_root / relative).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DependencyManifestError(
            STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED, str(exc)
        ) from exc

    distributions, hash_pinned = parse_manifest(text)
    required = required_distributions(test_root)
    missing = frozenset(required - distributions)
    if missing:
        raise DependencyManifestError(
            STAGE_B_DEPENDENCY_MANIFEST_INCOMPLETE, ",".join(sorted(missing))
        )

    return ResolvedManifest(
        relative_path=relative,
        sha256=hashlib.sha256(raw).hexdigest(),
        distributions=distributions,
        required_distributions=required,
        missing_distributions=missing,
        hash_pinned=hash_pinned,
    )


__all__ = [
    "IMPORT_TO_DISTRIBUTION",
    "INTERNAL_ROOTS",
    "MANIFEST_CANDIDATES",
    "STAGE_B_DEPENDENCY_MANIFEST_AMBIGUOUS",
    "STAGE_B_DEPENDENCY_MANIFEST_INCOMPLETE",
    "STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND",
    "STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED",
    "STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED",
    "STAGE_B_IMPORT_DISTRIBUTION_UNMAPPED",
    "DependencyManifestError",
    "ResolvedManifest",
    "external_imports",
    "normalize",
    "parse_manifest",
    "required_distributions",
    "resolve_manifest",
]
