"""§E4 승인 신뢰원 — 서명 방식.

정오표 v1.2 §E4 가 감사 우선순위 첫째(서명)를 채택했다. 저장소 보호 설정만으로는
신뢰원이 성립하지 않는다.

★지문·namespace·서명자 신원은 이 모듈 안에 고정한다. 부르는 쪽이 고를 수 있으면
  신뢰원이 아니다(§E4 금지 3항). 인자로 받지 않는다.

★allowed_signers 는 승인 저장소의 고정 커밋에서 읽은 바이트만 받는다.
  후보 checkout 에서 읽은 것을 넘기면 안 된다(§E4 금지 2항) — 호출부 계약이며
  이 모듈은 바이트만 다룬다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ── 실패 코드 (§E5) ────────────────────────────────────────────────────
APPROVAL_SIGNATURE_INVALID = "APPROVAL_SIGNATURE_INVALID"
APPROVAL_SIGNER_UNTRUSTED = "APPROVAL_SIGNER_UNTRUSTED"

# ── 코드 안에 고정된 신뢰원 (§E4) ──────────────────────────────────────
SIGNATURE_NAMESPACE = "butler-approval"
SIGNER_IDENTITY = "butler-approval-signer"
SIGNING_KEY_FINGERPRINT = "SHA256:q87ozBPt1b218/lngOptVPRfFpgblANbUuvlUbu8HL4"

_FINGERPRINT_RE = re.compile(r"\bSHA256:[A-Za-z0-9+/]{43}\b")


@dataclass(frozen=True)
class SignatureFailure:
    code: str
    message: str
    expected: str | None = None
    observed: str | None = None


def _fingerprints(allowed_signers_bytes: bytes) -> tuple[str, ...]:
    """allowed_signers 각 줄의 공개키 지문을 계산한다.

    줄 형식: <principal> [options] <keytype> <base64> [comment]
    """
    found: list[str] = []
    keygen = shutil.which("ssh-keygen")
    if keygen is None:
        return ()
    text = allowed_signers_bytes.decode("utf-8", errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        for index, line in enumerate(text.splitlines()):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            key_index = next(
                (i for i, field in enumerate(fields) if field.startswith(("ssh-", "sk-", "ecdsa-"))),
                None,
            )
            if key_index is None or key_index + 1 >= len(fields):
                continue
            pub = Path(tmp) / f"key{index}.pub"
            pub.write_text(" ".join(fields[key_index:]) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [keygen, "-lf", str(pub)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                continue
            match = _FINGERPRINT_RE.search(completed.stdout)
            if match is not None:
                found.append(match.group(0))
    return tuple(found)


def verify_approval_signature(
    *,
    document_bytes: bytes,
    signature_bytes: bytes,
    allowed_signers_bytes: bytes,
) -> tuple[bool, tuple[SignatureFailure, ...]]:
    """승인 문서 서명을 검증한다. (ok, failures).

    지문·namespace·신원은 인자로 받지 않는다. 이 모듈에 고정된 값만 쓴다.
    """
    if not document_bytes or not signature_bytes or not allowed_signers_bytes:
        return False, (
            SignatureFailure(
                APPROVAL_SIGNATURE_INVALID,
                "문서·서명·allowed_signers 바이트가 모두 필요하다",
            ),
        )

    keygen = shutil.which("ssh-keygen")
    if keygen is None:
        return False, (
            SignatureFailure(
                APPROVAL_SIGNATURE_INVALID,
                "ssh-keygen 을 찾을 수 없어 서명을 검증할 수 없다(fail-closed)",
            ),
        )

    # ① 허용 서명자 지문이 고정 지문과 일치하는가 (§E4 3단계)
    observed = _fingerprints(allowed_signers_bytes)
    if SIGNING_KEY_FINGERPRINT not in observed:
        return False, (
            SignatureFailure(
                APPROVAL_SIGNER_UNTRUSTED,
                "allowed_signers 에 고정 지문이 없다",
                expected=SIGNING_KEY_FINGERPRINT,
                observed=", ".join(observed) if observed else "(지문 없음)",
            ),
        )

    # ② 서명 검증 (§E4 4단계)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        signers = root / "allowed_signers"
        signature = root / "document.sig"
        document = root / "document"
        signers.write_bytes(allowed_signers_bytes)
        signature.write_bytes(signature_bytes)
        document.write_bytes(document_bytes)
        with document.open("rb") as stream:
            completed = subprocess.run(
                [
                    keygen,
                    "-Y",
                    "verify",
                    "-f",
                    str(signers),
                    "-I",
                    SIGNER_IDENTITY,
                    "-n",
                    SIGNATURE_NAMESPACE,
                    "-s",
                    str(signature),
                ],
                stdin=stream,
                capture_output=True,
                text=True,
                check=False,
            )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        return False, (
            SignatureFailure(
                APPROVAL_SIGNATURE_INVALID,
                "ssh-keygen -Y verify 실패",
                expected=f"Good {SIGNATURE_NAMESPACE} signature for {SIGNER_IDENTITY}",
                observed=detail[-1] if detail else f"exit={completed.returncode}",
            ),
        )
    return True, ()
