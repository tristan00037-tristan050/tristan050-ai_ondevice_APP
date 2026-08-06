"""F-03 — host 와 자격 출처를 ★전송 계층에서★ 강제한다.

감사 F-03 판정: 두 안 모두 코드 안에 host allowlist 를 두었지만, 실제로 부르는
`gh api` 에는 아무 제약도 걸지 않았다.

    gh 는 GH_HOST 가 있으면 그 host 로 간다
    gh 는 GH_CONFIG_DIR / ~/.config/gh 의 저장 자격을 쓴다
    gh 는 GH_ENTERPRISE_TOKEN 을 별도로 인식한다

그래서 **코드 안의 allowlist 는 전송 계층의 실제 제약이 아니었다.** 검사기가
"github.com 만 부른다" 고 믿는 동안, 실행 환경이 그것을 조용히 뒤집을 수 있었다.

이 모듈이 닫는 것

    ① `--hostname github.com` 을 argv 에 ★명시★ 한다.
       gh 가 환경에서 host 를 고르게 두지 않는다.
    ② 자식 환경을 ★allowlist 로 새로 만든다★. os.environ 을 물려주지 않는다.
       GH_HOST · GH_ENTERPRISE_TOKEN · GITHUB_TOKEN · GH_CONFIG_DIR 등
       자격·host 를 바꾸는 이름은 ★애초에 들어가지 않는다★.
    ③ ★격리된 빈 GH_CONFIG_DIR★ 을 준다. 저장된 자격이 있어도 쓰이지 않는다.
    ④ ★첫 요청 전에 두 token 을 함께★ 확인한다(v2.0 §3-2). 빈 token 으로 부르면
       익명 호출이 되어 public repo 에서는 200 이 온다 — 권한 검증이 증발한다.
       한쪽만 비어도 ★아무 요청도 보내지 않는다.★
    ⑤ proxy·CA 이름을 자식에게 넘기지 않는다(v2.0 §3-3). 넘기면 호출이 어디로
       가는지·무엇을 신뢰하는지가 바깥에서 바뀐다.

★토큰은 argv 에 넣지 않는다. 자식 env 로만 간다(§3-2).
★이 모듈은 환경을 ★만들 뿐★ 실행하지 않는다. 실행은 output_containment 다.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ── 오류 코드 ──────────────────────────────────────────────────────────
TRANSPORT_TOKEN_MISSING = "TRANSPORT_TOKEN_MISSING"
TRANSPORT_TOKEN_PAIR_INCOMPLETE = "TRANSPORT_TOKEN_PAIR_INCOMPLETE"
TRANSPORT_HOST_NOT_ALLOWED = "TRANSPORT_HOST_NOT_ALLOWED"
TRANSPORT_CONFIG_NOT_ISOLATED = "TRANSPORT_CONFIG_NOT_ISOLATED"
TRANSPORT_ENV_NOT_MINIMAL = "TRANSPORT_ENV_NOT_MINIMAL"

# ★유일하게 허용하는 host. 값이 아니라 ★argv 로도★ 강제한다.
#
# ★v2.0 §3-1 교정 — 이 값은 API URL 이 아니라 ★GitHub 호스트★ 다.
#   gh 는 `--hostname` 을 "The GitHub hostname for the request (default github.com)"
#   으로 정의하고, ghinstance 가 여기에 `api.` 를 붙여 REST 주소를 만든다.
#
#       github.com      → https://api.github.com/       ★맞다
#       api.github.com  → https://api.api.github.com/   ★없는 호스트다
#
#   이전 판은 `api.github.com` 을 주었다. 의미가 다른 정도가 아니라 ★모든 요청이
#   DNS 에서 깨진다★. 병렬 개발이 아니었으면 원격 실행 전까지 몰랐을 결함이다.
ALLOWED_HOSTNAME = "github.com"

# 자식에게 넘기는 이름은 이 목록뿐이다. 나머지는 이름조차 전달하지 않는다.
# ★proxy·CA 이름은 여기 없다. 있으면 호출이 어디로 가는지·무엇을 신뢰하는지가
#   바깥에서 바뀐다(v2.0 §3-3).
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")

# ★자격·host·경로·신뢰원을 바꿀 수 있는 이름. 자식 환경에 ★있어서는 안 된다★.
FORBIDDEN_ENV_NAMES = (
    "GH_HOST",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GITHUB_TOKEN",
    "GH_CONFIG_DIR",       # 우리가 만든 격리 경로로만 들어간다
    "GITHUB_API_URL",
    "GH_REPO",
    "GH_PATH",
    "GH_FORCE_TTY",
    "AC25_APPROVAL_TOKEN",   # 라우팅된 토큰만 GH_TOKEN 으로 간다
    "AC25_CANDIDATE_TOKEN",
    # ── v2.0 §3-3 — 통로와 신뢰원을 바깥에서 바꾸지 못하게 한다 ──────
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)

_TOKEN_RE = re.compile(r"\A[A-Za-z0-9_.\-]{8,512}\Z")


class TransportPolicyError(Exception):
    """메시지에 token·경로 원문을 넣지 않는다. 코드만 갖고 다닌다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TransportEnvironment:
    """한 번의 전송에 쓰는 환경과 argv 조각."""

    env: dict[str, str]
    config_dir: Path

    def argv(self, path: str) -> list[str]:
        """★--hostname 을 명시한 argv. 환경이 host 를 고르지 못한다."""
        return ["gh", "api", "--hostname", ALLOWED_HOSTNAME, "-i", path]


def isolated_config_dir(parent: Path | None = None) -> Path:
    """★빈 GH_CONFIG_DIR 을 만든다. 저장된 자격이 상속되지 않는다.

    호출부가 finally 에서 지운다. 남겨도 비어 있으므로 자격이 새지 않는다.
    """
    root = Path(tempfile.mkdtemp(dir=str(parent) if parent else None, prefix="ac25-ghcfg-"))
    os.chmod(root, 0o700)
    return root


def build_transport_environment(
    *, token: str, config_dir: Path, source_environ: dict[str, str] | None = None
) -> TransportEnvironment:
    """자식 환경을 ★allowlist 로 새로 만든다★. 물려주지 않는다.

    token 은 GH_TOKEN 하나로만 들어간다. 빈 token 은 여기서 닫는다 — 익명 호출로
    떨어지면 public repo 에서 200 이 오고 권한 검증이 사라진다.
    """
    if not isinstance(token, str) or _TOKEN_RE.match(token) is None:
        raise TransportPolicyError(TRANSPORT_TOKEN_MISSING)

    resolved = Path(config_dir)
    if not resolved.is_dir():
        raise TransportPolicyError(TRANSPORT_CONFIG_NOT_ISOLATED)
    if any(resolved.iterdir()):
        # 비어 있지 않으면 저장된 자격이 있을 수 있다 — 격리가 아니다
        raise TransportPolicyError(TRANSPORT_CONFIG_NOT_ISOLATED)

    origin = dict(os.environ if source_environ is None else source_environ)
    env: dict[str, str] = {}
    for name in _ENV_ALLOWLIST:
        value = origin.get(name)
        if isinstance(value, str) and value:
            env[name] = value
    env["GH_TOKEN"] = token
    env["GH_CONFIG_DIR"] = str(resolved)
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    env["GH_PROMPT_DISABLED"] = "1"
    env["NO_COLOR"] = "1"

    require_minimal_environment(env, config_dir=resolved)
    return TransportEnvironment(env=env, config_dir=resolved)


def require_minimal_environment(env: dict[str, str], *, config_dir: Path) -> None:
    """자식 환경이 계약을 지키는지 마지막으로 본다. 어기면 요청 전에 닫는다."""
    for name in FORBIDDEN_ENV_NAMES:
        if name == "GH_CONFIG_DIR":
            continue  # 우리가 넣은 격리 경로만 허용한다(아래에서 값까지 본다)
        if name in env:
            raise TransportPolicyError(TRANSPORT_ENV_NOT_MINIMAL)
    if env.get("GH_CONFIG_DIR") != str(config_dir):
        raise TransportPolicyError(TRANSPORT_CONFIG_NOT_ISOLATED)
    if not env.get("GH_TOKEN"):
        raise TransportPolicyError(TRANSPORT_TOKEN_MISSING)
    unexpected = set(env) - set(_ENV_ALLOWLIST) - {
        "GH_TOKEN", "GH_CONFIG_DIR", "GH_NO_UPDATE_NOTIFIER",
        "GH_PROMPT_DISABLED", "NO_COLOR",
    }
    if unexpected:
        raise TransportPolicyError(TRANSPORT_ENV_NOT_MINIMAL)


def require_token_pair(
    *, approval_env: str, candidate_env: str, source_environ: dict[str, str] | None = None
) -> None:
    """★v2.0 §3-2 — ★첫 요청을 보내기 전에★ 두 토큰을 ★함께★ 본다.

    이전 판은 각 전송 직전에 ★그때 고른 한 토큰만★ 확인했다. 그러면 승인 토큰만
    있고 후보 토큰이 없는 상태에서도 승인 저장소 요청 여러 건이 먼저 나간 뒤,
    후보 요청 차례가 되어서야 닫힌다. **이미 보낸 요청은 되돌릴 수 없다.**

    한쪽이라도 비어 있으면 ★아무 요청도 보내지 않고★ 닫는다.
    """
    origin = dict(os.environ if source_environ is None else source_environ)
    for name in (approval_env, candidate_env):
        value = origin.get(name, "")
        if not isinstance(value, str) or _TOKEN_RE.match(value) is None:
            raise TransportPolicyError(TRANSPORT_TOKEN_PAIR_INCOMPLETE)


def require_hostname_pinned(argv: list[str]) -> None:
    """argv 에 --hostname 이 정확히 한 번, 허용 host 로 들어갔는지 본다."""
    if argv[:2] != ["gh", "api"]:
        raise TransportPolicyError(TRANSPORT_HOST_NOT_ALLOWED)
    if argv.count("--hostname") != 1:
        raise TransportPolicyError(TRANSPORT_HOST_NOT_ALLOWED)
    index = argv.index("--hostname")
    if index + 1 >= len(argv) or argv[index + 1] != ALLOWED_HOSTNAME:
        raise TransportPolicyError(TRANSPORT_HOST_NOT_ALLOWED)


__all__ = [
    "ALLOWED_HOSTNAME",
    "FORBIDDEN_ENV_NAMES",
    "TRANSPORT_CONFIG_NOT_ISOLATED",
    "TRANSPORT_ENV_NOT_MINIMAL",
    "TRANSPORT_HOST_NOT_ALLOWED",
    "TRANSPORT_TOKEN_MISSING",
    "TRANSPORT_TOKEN_PAIR_INCOMPLETE",
    "TransportEnvironment",
    "TransportPolicyError",
    "require_hostname_pinned",
    "require_token_pair",
    "require_minimal_environment",
    "build_transport_environment",
    "isolated_config_dir",
]
