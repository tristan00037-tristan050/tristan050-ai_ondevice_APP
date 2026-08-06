"""F-03 — host 와 자격 출처를 ★전송 계층에서★ 강제한다.

감사 F-03 판정: 두 안 모두 코드 안에 host allowlist 를 두었지만, 실제로 부르는
`gh api` 에는 아무 제약도 걸지 않았다.

    gh 는 GH_HOST 가 있으면 그 host 로 간다
    gh 는 GH_CONFIG_DIR / ~/.config/gh 의 저장 자격을 쓴다
    gh 는 GH_ENTERPRISE_TOKEN 을 별도로 인식한다

그래서 **코드 안의 allowlist 는 전송 계층의 실제 제약이 아니었다.** 검사기가
"api.github.com 만 부른다" 고 믿는 동안, 실행 환경이 그것을 조용히 뒤집을 수 있었다.

이 모듈이 닫는 것

    ① `--hostname api.github.com` 을 argv 에 ★명시★ 한다.
       gh 가 환경에서 host 를 고르게 두지 않는다.
    ② 자식 환경을 ★allowlist 로 새로 만든다★. os.environ 을 물려주지 않는다.
       GH_HOST · GH_ENTERPRISE_TOKEN · GITHUB_TOKEN · GH_CONFIG_DIR 등
       자격·host 를 바꾸는 이름은 ★애초에 들어가지 않는다★.
    ③ ★격리된 빈 GH_CONFIG_DIR★ 을 준다. 저장된 자격이 있어도 쓰이지 않는다.
    ④ 전송 전에 해당 token 이 비어 있지 않은지 확인한다. 빈 token 으로 부르면
       익명 호출이 되어 public repo 에서는 200 이 온다 — 권한 검증이 증발한다.

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
TRANSPORT_HOST_NOT_ALLOWED = "TRANSPORT_HOST_NOT_ALLOWED"
TRANSPORT_CONFIG_NOT_ISOLATED = "TRANSPORT_CONFIG_NOT_ISOLATED"
TRANSPORT_ENV_NOT_MINIMAL = "TRANSPORT_ENV_NOT_MINIMAL"

# ★유일하게 허용하는 host. 값이 아니라 ★argv 로도★ 강제한다.
ALLOWED_HOSTNAME = "api.github.com"

# 자식에게 넘기는 이름은 이 목록뿐이다. 나머지는 이름조차 전달하지 않는다.
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")

# ★자격·host 를 바꿀 수 있는 이름. 자식 환경에 ★있어서는 안 된다★.
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
    "TransportEnvironment",
    "TransportPolicyError",
    "require_hostname_pinned",
    "require_minimal_environment",
    "build_transport_environment",
    "isolated_config_dir",
]
