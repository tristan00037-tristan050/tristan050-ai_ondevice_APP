"""F-03 — host 와 자격 출처가 ★전송 계층에서★ 실제로 강제되는가.

감사 F-03: 두 안 모두 코드 안에 host allowlist 를 두었지만 `gh api` 에는 아무
제약을 걸지 않았다. 그래서 실행 환경이 그것을 조용히 뒤집을 수 있었다.

    GH_HOST=ghe.internal          → gh 가 그 host 로 간다
    GH_ENTERPRISE_TOKEN=…         → gh 가 그 자격을 쓴다
    GH_CONFIG_DIR=~/.config/gh    → 저장된 자격이 쓰인다

이 시험은 ★그 우회를 실제로 환경에 심어 놓고★ 전송이 그래도 승인된 host·token
으로만 나가는지 본다. 코드에 상수가 있다는 것으로 통과시키지 않는다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from ac25 import gh_transport_policy as gp

pytestmark = pytest.mark.no_sidecar_token

GOOD_TOKEN = "ghp_" + "A" * 36


@pytest.fixture
def config_dir(tmp_path) -> Path:
    return gp.isolated_config_dir(tmp_path)


# ══ ① --hostname 이 argv 에 명시된다 ═══════════════════════════════════
def test_argv_pins_the_hostname(config_dir):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir)
    argv = env.argv("repos/o/r")
    assert argv[:4] == ["gh", "api", "--hostname", "api.github.com"]
    assert argv[-1] == "repos/o/r"
    gp.require_hostname_pinned(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["gh", "api", "-i", "repos/o/r"],                                # 없음
        ["gh", "api", "--hostname", "ghe.internal", "-i", "repos/o/r"],  # 다른 host
        ["gh", "api", "--hostname", "api.github.com",
         "--hostname", "ghe.internal", "-i", "x"],                       # 두 번
        ["curl", "https://api.github.com"],                              # gh 가 아님
    ],
)
def test_unpinned_or_foreign_hostname_is_refused(argv):
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_hostname_pinned(argv)
    assert caught.value.code == gp.TRANSPORT_HOST_NOT_ALLOWED


def test_token_never_appears_in_argv(config_dir):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir)
    argv = env.argv("repos/o/r")
    assert not any(GOOD_TOKEN in part for part in argv)
    assert env.env["GH_TOKEN"] == GOOD_TOKEN  # env 로만 간다


# ══ ② 자식 환경은 allowlist 로 새로 만든다 ═════════════════════════════
def test_environment_is_built_not_inherited(config_dir):
    hostile = {
        "PATH": "/usr/bin",
        "GH_HOST": "ghe.internal",
        "GH_ENTERPRISE_TOKEN": "enterprise-secret",
        "GITHUB_ENTERPRISE_TOKEN": "enterprise-secret-2",
        "GITHUB_TOKEN": "other-token",
        "GH_CONFIG_DIR": "/home/attacker/.config/gh",
        "GITHUB_API_URL": "https://ghe.internal/api/v3",
        "AC25_APPROVAL_TOKEN": "approval-secret",
        "AC25_CANDIDATE_TOKEN": "candidate-secret",
        "SOME_OTHER_SECRET": "leak-me",
    }
    env = gp.build_transport_environment(
        token=GOOD_TOKEN, config_dir=config_dir, source_environ=hostile
    ).env

    # ★우회 이름은 하나도 들어가지 않는다
    for name in gp.FORBIDDEN_ENV_NAMES:
        if name == "GH_CONFIG_DIR":
            continue
        assert name not in env, name
    # ★allowlist 밖 이름도 들어가지 않는다
    assert "SOME_OTHER_SECRET" not in env
    # ★다른 토큰 값이 어떤 자리로도 새지 않는다
    joined = "\n".join(f"{k}={v}" for k, v in env.items())
    for secret in ("enterprise-secret", "other-token", "approval-secret",
                   "candidate-secret", "leak-me"):
        assert secret not in joined, secret
    assert env["PATH"] == "/usr/bin"
    assert env["GH_TOKEN"] == GOOD_TOKEN


@pytest.mark.parametrize("name", [n for n in gp.FORBIDDEN_ENV_NAMES if n != "GH_CONFIG_DIR"])
def test_each_bypass_name_is_refused_if_it_somehow_appears(name, config_dir):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir).env
    env[name] = "injected"
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_minimal_environment(env, config_dir=config_dir)
    assert caught.value.code == gp.TRANSPORT_ENV_NOT_MINIMAL


def test_unexpected_extra_name_is_refused(config_dir):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir).env
    env["SURPRISE"] = "1"
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_minimal_environment(env, config_dir=config_dir)
    assert caught.value.code == gp.TRANSPORT_ENV_NOT_MINIMAL


# ══ ③ GH_CONFIG_DIR 격리 ═══════════════════════════════════════════════
def test_config_dir_is_fresh_empty_and_private(tmp_path):
    directory = gp.isolated_config_dir(tmp_path)
    assert directory.is_dir()
    assert list(directory.iterdir()) == []
    assert oct(directory.stat().st_mode & 0o777) == "0o700"
    assert directory.parent == tmp_path.resolve() or directory.parent == tmp_path


def test_environment_points_at_the_isolated_config_dir(config_dir):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir).env
    assert env["GH_CONFIG_DIR"] == str(config_dir)


def test_non_empty_config_dir_is_refused(tmp_path):
    """저장된 자격이 있을 수 있는 디렉터리는 격리가 아니다."""
    directory = gp.isolated_config_dir(tmp_path)
    (directory / "hosts.yml").write_text("github.com:\n  oauth_token: leaked\n")
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.build_transport_environment(token=GOOD_TOKEN, config_dir=directory)
    assert caught.value.code == gp.TRANSPORT_CONFIG_NOT_ISOLATED


def test_missing_config_dir_is_refused(tmp_path):
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.build_transport_environment(token=GOOD_TOKEN, config_dir=tmp_path / "absent")
    assert caught.value.code == gp.TRANSPORT_CONFIG_NOT_ISOLATED


def test_config_dir_mismatch_is_refused(config_dir, tmp_path):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir).env
    env["GH_CONFIG_DIR"] = str(tmp_path)
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_minimal_environment(env, config_dir=config_dir)
    assert caught.value.code == gp.TRANSPORT_CONFIG_NOT_ISOLATED


# ══ ④ 빈 token 은 요청 전에 닫는다 ═════════════════════════════════════
@pytest.mark.parametrize("token", ["", "   ", None, "short", 12345, "has space"])
def test_missing_or_malformed_token_is_refused(token, config_dir):
    """빈 token 으로 부르면 익명 호출이 되어 public repo 에서 200 이 온다.

    그러면 권한 검증이 증발한다 — 요청을 아예 보내지 않는다.
    """
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.build_transport_environment(token=token, config_dir=config_dir)
    assert caught.value.code == gp.TRANSPORT_TOKEN_MISSING


def test_policy_error_carries_only_a_code(config_dir):
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.build_transport_environment(token="", config_dir=config_dir)
    message = str(caught.value)
    assert message == gp.TRANSPORT_TOKEN_MISSING
    assert "/" not in message


# ══ 실제 전송이 이 정책을 쓴다 ═════════════════════════════════════════
def test_remote_facts_transport_uses_the_policy():
    """★정책 모듈이 있는 것만으로는 강제가 아니다. 전송이 실제로 써야 한다."""
    source = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "ci" / "ac25" / "remote_facts.py"
    ).read_text(encoding="utf-8")
    assert "gh_transport_policy.build_transport_environment" in source
    assert "gh_transport_policy.require_hostname_pinned" in source
    assert "gh_transport_policy.isolated_config_dir" in source
    # ★os.environ 을 그대로 물려주는 옛 경로가 남아 있지 않다
    assert "env = dict(_os.environ)" not in source


def test_transport_refuses_to_send_when_token_is_absent(monkeypatch, tmp_path):
    """token 이 없으면 ★transport 를 부르지 않고★ 코드로 닫는다."""
    from ac25 import output_containment, remote_facts as rf

    monkeypatch.delenv("AC25_APPROVAL_TOKEN", raising=False)
    monkeypatch.setattr(output_containment, "default_runner_temp", lambda: tmp_path)

    called: list = []

    def explode(*args, **kwargs):
        called.append(args)
        raise AssertionError("token 이 없는데 명령을 실행했다")

    monkeypatch.setattr(output_containment, "run_and_read", explode)
    send = rf.gh_transport_for("AC25_APPROVAL_TOKEN")
    result = send("repos/o/r")
    assert called == []
    assert result.status == 0
    assert result.message == gp.TRANSPORT_TOKEN_MISSING


def test_transport_sends_pinned_argv_and_minimal_env(monkeypatch, tmp_path):
    """실제 전송 경로가 ★--hostname 과 격리 환경★ 으로 나가는지 본다."""
    from ac25 import output_containment, remote_facts as rf

    hostile = {
        "PATH": "/usr/bin",
        "GH_HOST": "ghe.internal",
        "GH_ENTERPRISE_TOKEN": "enterprise-secret",
        "GITHUB_TOKEN": "other-token",
        "AC25_APPROVAL_TOKEN": GOOD_TOKEN,
    }
    monkeypatch.setattr(os, "environ", hostile)
    monkeypatch.setattr(output_containment, "default_runner_temp", lambda: tmp_path)

    seen: dict = {}

    def capture(argv, *, cwd, env, **kwargs):
        seen["argv"] = list(argv)
        seen["env"] = dict(env)
        return 0, b'HTTP/2 200\r\n\r\n{"ok": true}', b""

    monkeypatch.setattr(output_containment, "run_and_read", capture)
    send = rf.gh_transport_for("AC25_APPROVAL_TOKEN")
    result = send("repos/o/r")

    assert result.status == 200
    gp.require_hostname_pinned(seen["argv"])
    assert "--hostname" in seen["argv"]
    assert seen["env"]["GH_TOKEN"] == GOOD_TOKEN
    assert "GH_HOST" not in seen["env"]
    assert "GH_ENTERPRISE_TOKEN" not in seen["env"]
    assert "GITHUB_TOKEN" not in seen["env"]
    assert seen["env"]["GH_CONFIG_DIR"].startswith(str(tmp_path))
    # ★다른 자격이 자식 환경 어디에도 없다
    joined = "\n".join(f"{k}={v}" for k, v in seen["env"].items())
    assert "enterprise-secret" not in joined
    assert "other-token" not in joined


def test_transport_removes_the_config_dir_afterwards(monkeypatch, tmp_path):
    """격리 디렉터리를 남기지 않는다 — 남으면 다음 실행이 물려받는다."""
    from ac25 import output_containment, remote_facts as rf

    monkeypatch.setattr(os, "environ", {"PATH": "/usr/bin", "AC25_APPROVAL_TOKEN": GOOD_TOKEN})
    monkeypatch.setattr(output_containment, "default_runner_temp", lambda: tmp_path)
    monkeypatch.setattr(
        output_containment, "run_and_read",
        lambda *a, **k: (0, b'HTTP/2 200\r\n\r\n{"ok": true}', b""),
    )
    rf.gh_transport_for("AC25_APPROVAL_TOKEN")("repos/o/r")
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("ac25-ghcfg-")]
    assert leftovers == [], leftovers
