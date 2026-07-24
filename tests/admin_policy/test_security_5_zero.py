"""ALG 보안 5 ZERO 회귀 — 본 PR 범위 정합 (박스 3 머지본 환경).

ALG 원본은 connect_loop schemas·docs/ssot 가 미존재한 격리 zip 환경에서 작성되어
`assert not (ROOT / "schemas" / "connect_loop").exists()` 같이 *부재 자체*를
검증했다. 박스 3 머지본 repo 는 두 디렉터리가 기존 자산으로 존재하므로 본 PR 의
보안 5 ZERO 의무를 *본 PR 범위* 한정으로 정합화한다 — 본 PR 이 들고 온 자산이
schemas/connect_loop·docs/ssot 를 수정/포함하지 않음 + raw/path/secret/token
storage/training artifact 0 건을 검증.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PR_PATHS = (
    "butler_pc_core/company_policy",
    "butler_pc_core/cards/box3/adapters/company_format_adapter.py",
    "butler_pc_core/sidecar/routes/admin_policy_format.py",
    "tests/company_policy",
    "tests/admin_policy",
    "scripts/run_admin_policy_format_self_check.py",
    "scripts/run_security_scan_v1_2.py",
    "scripts/verify_admin_policy_format_v1_2.sh",
)

_BINARY_SUFFIXES = {
    ".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm", ".pdf",
    ".zip", ".gz", ".tar", ".db", ".sqlite", ".so", ".dylib",
}


_SELF = Path(__file__).resolve()
# 5 ZERO 검증 도구 자체는 needle 리터럴(예: "Trainer(", "save_pretrained", "http://",
# "localStorage", "sk-proj-", "schemas/connect_loop", "/Users/") 을 검증 목적으로
# 보유하므로 self-검사 fail 회피를 위해 검사 대상에서 제외(verifier-self-exclude).
_EXCLUDED = {
    (ROOT / "tests" / "admin_policy" / "test_security_5_zero.py").resolve(),
    (ROOT / "tests" / "admin_policy" / "test_policy_format_registration.py").resolve(),
    (ROOT / "scripts" / "run_security_scan_v1_2.py").resolve(),
    (ROOT / "scripts" / "verify_admin_policy_format_v1_2.sh").resolve(),
}


def _read_pr_scope() -> str:
    parts: list[str] = []
    for rel in PR_PATHS:
        base = ROOT / rel
        if base.is_file():
            if base.resolve() in _EXCLUDED:
                continue
            try:
                parts.append(base.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix in _BINARY_SUFFIXES:
                continue
            if path.resolve() in _EXCLUDED:
                continue
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
    return "\n".join(parts)


def test_connect_loop_contract_modified_zero():
    for rel in PR_PATHS:
        base = ROOT / rel
        assert not str(base).startswith(str(ROOT / "schemas" / "connect_loop"))
        assert not str(base).startswith(str(ROOT / "docs" / "ssot"))
    text = _read_pr_scope()
    assert "schemas/connect_loop" not in text
    assert "docs/ssot/connect_loop" not in text


def test_token_storage_log_zero():
    text = _read_pr_scope()
    assert "localStorage" not in text
    assert "sessionStorage" not in text
    assert "console.log" not in text


# --- narrowed source-scan primitives (loopback-aware / real-secret-pattern) ---
# The original scans forbade the bare substrings "http://" and "Bearer ", which
# false-flag (a) the local-UI CORS origins http://localhost / http://127.0.0.1
# and (b) f-string auth headers f"Bearer {token}". Narrow to actual egress /
# actual literal secrets. Regression tests below plant genuine positives to
# prove the narrowed scanners still detect real leaks.
_HTTP_SCHEME_RE = re.compile(r"https?://")
# a loopback host immediately after the scheme (localhost / 127.0.0.1 / [::1]),
# optional :port, not followed by another host char.
_LOOPBACK_AFTER_SCHEME_RE = re.compile(
    r"(?i)(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?(?![\w.\-])"
)
_LITERAL_BEARER_RE = re.compile(r"Bearer\s+([A-Za-z0-9._\-]{16,})")


def _nonloopback_http(text: str) -> list[str]:
    """Every http(s):// scheme occurrence NOT immediately followed by a loopback
    host. Scheme-anchored (not host-anchored) so it also catches split/dynamic
    egress — e.g. `requests.get("https://" + host)` — that a host-only regex
    would miss (Codex #876). Only localhost / 127.0.0.1 / ::1 are permitted."""
    offenders: list[str] = []
    for m in _HTTP_SCHEME_RE.finditer(text):
        if _LOOPBACK_AFTER_SCHEME_RE.match(text, m.end()):
            continue
        offenders.append(text[m.start() : m.end() + 24].splitlines()[0])
    return offenders


def _literal_bearer_secrets(text: str) -> list[str]:
    """`Bearer <literal high-entropy token>`. f"Bearer {token}" is NOT matched:
    the char after 'Bearer ' is '{', outside the token charset (interpolation)."""
    return _LITERAL_BEARER_RE.findall(text)


def test_non_local_network_zero():
    text = _read_pr_scope()
    assert "axios" not in text
    assert "new WebSocket" not in text
    # loopback-aware: only non-loopback http(s) egress is forbidden; the local UI
    # CORS origins http://localhost / http://127.0.0.1 are permitted.
    assert _nonloopback_http(text) == []


def test_raw_secret_path_scan_zero():
    text = _read_pr_scope()
    assert re.search(r"\braw_text\b", text) is None
    assert "sk-proj-" not in text
    assert "/Users/" not in text and "/home/" not in text and "/Volumes/" not in text
    # real-secret-pattern: a literal Bearer token, not an f-string/format interpolation.
    assert _literal_bearer_secrets(text) == []


def test_nonloopback_http_regression_still_detected():
    """★ Plant genuine external egress: the narrowed scan must still flag it."""
    # full external URLs
    assert _nonloopback_http('x = "http://evil.example.com/exfil"')
    assert _nonloopback_http('u = "https://198.51.100.7:9000/c2"')
    # ★ split / dynamically-built egress (Codex #876): scheme literal with the
    # host concatenated at runtime — a host-only regex would miss these.
    assert _nonloopback_http('requests.get("https://" + host)')
    assert _nonloopback_http('u = "http://" + dept + ".corp.example.com"')
    assert _nonloopback_http('fetch(`https://${host}/x`)')
    # loopback stays permitted (the reason the original scan false-flagged)
    assert _nonloopback_http('cors = "http://localhost:1420"') == []
    assert _nonloopback_http('cors = "http://127.0.0.1:1420"') == []
    assert _nonloopback_http('cors = "http://[::1]:1420"') == []


def test_literal_bearer_regression_still_detected():
    """★ Plant a genuine literal Bearer secret: the narrowed scan must flag it."""
    assert _literal_bearer_secrets('h = {"Authorization": "Bearer AKIAIOSFODNN7EXAMPLEKEY01"}') == [
        "AKIAIOSFODNN7EXAMPLEKEY01"
    ]
    # f-string interpolation is not a literal secret
    assert _literal_bearer_secrets('h = {"Authorization": f"Bearer {token}"}') == []


def test_training_model_artifact_zero():
    text = _read_pr_scope()
    for needle in ["Trainer(", "save_pretrained", "safetensors", "gguf"]:
        assert needle not in text
