"""§6 경로 계산 계약.

approved_base_commit → approved_head_commit 의 변경 경로만 계산한다.
HEAD·github.sha·합성 병합 커밋·작업 디렉터리 상태를 끝점으로 쓰지 않는다.

- git diff --name-only -z --no-renames BASE HEAD -- 로 계산
- 출력은 NUL 기준 파싱(줄바꿈 파싱 금지)
- 삭제 경로 제외 금지(--no-renames 로 rename 은 삭제+추가로 나타나 양쪽 검출)
- 각 경로 UTF-8 strict decode, POSIX 상대 경로, 대소문자 보존 정규화
- 표준 fnmatch 사용 금지. 저장소 glob 의미를 직접 구현:
    *  는 '/' 를 넘지 않는다
    ** 는 하위 디렉터리를 포함한다
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class GitPathsError(Exception):
    """구조화된 실패 코드를 담는 예외."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# 실패 코드 (§6)
CHANGED_PATHS_UNAVAILABLE = "CHANGED_PATHS_UNAVAILABLE"
CHANGED_PATH_ENCODING_INVALID = "CHANGED_PATH_ENCODING_INVALID"
CHANGED_PATH_CANONICALIZATION_FAILED = "CHANGED_PATH_CANONICALIZATION_FAILED"
GIT_OBJECT_NOT_FOUND = "GIT_OBJECT_NOT_FOUND"


_OID_RE = re.compile(r"^[0-9a-f]{40}$")


def _run_git(repository_path: str, args: list[str]) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "-C", repository_path, *args],
            capture_output=True,
            check=False,
        )
    except OSError as exc:  # git 미존재 등
        raise GitPathsError(CHANGED_PATHS_UNAVAILABLE, f"git 실행 실패: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")
        if "bad object" in err or "unknown revision" in err or "Not a valid object" in err:
            raise GitPathsError(GIT_OBJECT_NOT_FOUND, err.strip())
        raise GitPathsError(CHANGED_PATHS_UNAVAILABLE, err.strip() or "git diff 실패")
    return proc.stdout


def canonicalize_path(raw_bytes: bytes) -> str:
    """NUL 로 분리된 한 경로 바이트를 정규화. 실패 시 구조화 예외."""
    try:
        text = raw_bytes.decode("utf-8")  # strict
    except UnicodeDecodeError as exc:
        raise GitPathsError(
            CHANGED_PATH_ENCODING_INVALID,
            f"UTF-8 strict 디코딩 실패: {raw_bytes!r} ({exc})",
        ) from exc
    if not text:
        raise GitPathsError(CHANGED_PATH_CANONICALIZATION_FAILED, "빈 경로")
    if text.startswith("/"):
        raise GitPathsError(CHANGED_PATH_CANONICALIZATION_FAILED, f"절대 경로: {text}")
    if "\\" in text:
        raise GitPathsError(CHANGED_PATH_CANONICALIZATION_FAILED, f"역슬래시 경로: {text}")
    if "\x00" in text:
        raise GitPathsError(CHANGED_PATH_CANONICALIZATION_FAILED, "NUL 포함 경로")
    segments = text.split("/")
    if any(seg in (".", "..") for seg in segments):
        raise GitPathsError(CHANGED_PATH_CANONICALIZATION_FAILED, f". 또는 .. 세그먼트: {text}")
    if "" in segments:  # //, 선행/후행 슬래시
        raise GitPathsError(CHANGED_PATH_CANONICALIZATION_FAILED, f"빈 세그먼트: {text}")
    return text  # 대소문자 보존


def compute_changed_paths(
    *, repository_path: str, base_commit: str, head_commit: str,
) -> tuple[str, ...]:
    """base→head 변경 경로를 정규화된 튜플로 반환(정렬·중복제거)."""
    for name, oid in (("base", base_commit), ("head", head_commit)):
        if not _OID_RE.match(oid or ""):
            raise GitPathsError(
                GIT_OBJECT_NOT_FOUND, f"{name} 이 40자 소문자 hex OID 아님: {oid!r}")
    out = _run_git(
        repository_path,
        ["diff", "--name-only", "-z", "--no-renames", base_commit, head_commit, "--"],
    )
    paths: set[str] = set()
    for chunk in out.split(b"\x00"):
        if not chunk:
            continue
        paths.add(canonicalize_path(chunk))
    return tuple(sorted(paths))


def _translate_glob(pattern: str) -> re.Pattern[str]:
    """저장소 glob 의미로 컴파일. '*' 는 '/' 불포함, '**' 는 '/' 포함. 대소문자 구분."""
    i, n = 0, len(pattern)
    out = ["^"]
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")  # ** : '/' 포함
                i += 2
                if i < n and pattern[i] == "/":  # '**/' 는 0개 이상의 디렉터리
                    i += 1
            else:
                out.append("[^/]*")  # * : '/' 불포함
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return re.compile("".join(out))  # 대소문자 구분(IGNORECASE 없음)


def match_glob(pattern: str, path: str) -> bool:
    """단일 패턴이 경로에 매칭되는지(저장소 glob 의미, 대소문자 구분)."""
    return _translate_glob(pattern).fullmatch(path) is not None


@dataclass(frozen=True)
class AllowlistResult:
    inside: tuple[str, ...]
    offending: tuple[str, ...]


def paths_outside_allowlist(
    changed_paths: tuple[str, ...], allowed_patterns: tuple[str, ...],
) -> AllowlistResult:
    """allowed_patterns 중 하나에도 매칭되지 않는 changed_paths = offending."""
    inside, offending = [], []
    for p in changed_paths:
        if any(match_glob(pat, p) for pat in allowed_patterns):
            inside.append(p)
        else:
            offending.append(p)
    return AllowlistResult(tuple(inside), tuple(offending))
