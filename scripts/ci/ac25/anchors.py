"""§E4 · §E7 production 신뢰원 고정값.

★이 값들은 코드 안에 고정한다. 워크플로 입력·환경변수·후보 checkout 에서
  받지 않는다. 부르는 쪽이 고를 수 있으면 신뢰원이 아니다.

★승인 바이트는 오직 아래 (repository, commit, path) 조합의 API 응답으로만
  얻는다. 로컬 파일 경로에서 읽지 않는다(시험 픽스처 포함).
"""
from __future__ import annotations

from .cross_track_approval import TrustAnchor

# ── 승인 저장소(보호 ref 를 가진 별도 저장소) ──────────────────────────
APPROVAL_REPOSITORY = "tristan00037-tristan050/butler-ct-shared"
APPROVAL_PROTECTED_REF = "refs/heads/main"
APPROVAL_COMMIT_SHA = "f73496000e10dc533c3af243c1c0fb1c4d70e080"

APPROVAL_DOCUMENT_PATH = "docs/decisions/교차트랙승인_박스5_AC12_v2_20260805.md"
APPROVAL_SIGNATURE_PATH = "docs/decisions/교차트랙승인_박스5_AC12_v2_20260805.md.sig"
APPROVAL_ALLOWED_SIGNERS_PATH = "docs/decisions/allowed_signers"

# 승인 문서 원문의 고정 지문. 원격에서 읽은 바이트를 이것과 대조한다.
# (승인서 자신이 선언하는 값이 아니다 — 그러면 자기증명이 된다.)
APPROVAL_DOCUMENT_SHA256 = (
    "b278b935b08e2dbcf6eac7ab97bf5fcdbdd74f1f5247f0625938ff27ac2189d6"
)

# ── 후보 저장소 ────────────────────────────────────────────────────────
CANDIDATE_REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
CANDIDATE_PR_NUMBER = 903
CANDIDATE_LOCK_PATH = ".github/box5/ac25/pr903_candidate_lock.json"


def production_trust_anchor() -> TrustAnchor:
    """§8 신뢰원. 인자를 받지 않는다."""
    return TrustAnchor(
        source_repo=APPROVAL_REPOSITORY,
        protected_ref=APPROVAL_PROTECTED_REF,
        document_path=APPROVAL_DOCUMENT_PATH,
        signature_path=APPROVAL_SIGNATURE_PATH,
        allowed_signers_path=APPROVAL_ALLOWED_SIGNERS_PATH,
    )


__all__ = [
    "APPROVAL_ALLOWED_SIGNERS_PATH",
    "APPROVAL_COMMIT_SHA",
    "APPROVAL_DOCUMENT_PATH",
    "APPROVAL_DOCUMENT_SHA256",
    "APPROVAL_PROTECTED_REF",
    "APPROVAL_REPOSITORY",
    "APPROVAL_SIGNATURE_PATH",
    "CANDIDATE_LOCK_PATH",
    "CANDIDATE_PR_NUMBER",
    "CANDIDATE_REPOSITORY",
    "production_trust_anchor",
]
