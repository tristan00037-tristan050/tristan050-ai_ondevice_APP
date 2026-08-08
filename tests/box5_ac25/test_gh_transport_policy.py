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
    assert argv[:4] == ["gh", "api", "--hostname", "github.com"]
    assert argv[-1] == "repos/o/r"
    gp.require_hostname_pinned(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["gh", "api", "-i", "repos/o/r"],                                # 없음
        ["gh", "api", "--hostname", "ghe.internal", "-i", "repos/o/r"],  # 다른 host
        ["gh", "api", "--hostname", "api.github.com", "-i", "repos/o/r"],  # ★옛 잘못된 값
        ["gh", "api", "--hostname", "github.com",
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

    monkeypatch.setattr(os, "environ", {"PATH": "/usr/bin"})  # 두 토큰 다 없다
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
    # ★§3-2 이후 토큰 쌍 검사가 먼저 닫는다. 어느 쪽이든 요청은 0 건이다.
    assert result.message == gp.TRANSPORT_TOKEN_PAIR_INCOMPLETE


def test_transport_sends_pinned_argv_and_minimal_env(monkeypatch, tmp_path):
    """실제 전송 경로가 ★--hostname 과 격리 환경★ 으로 나가는지 본다."""
    from ac25 import output_containment, remote_facts as rf

    hostile = {
        "PATH": "/usr/bin",
        "GH_HOST": "ghe.internal",
        "GH_ENTERPRISE_TOKEN": "enterprise-secret",
        "GITHUB_TOKEN": "other-token",
        "AC25_APPROVAL_TOKEN": GOOD_TOKEN,
        "AC25_CANDIDATE_TOKEN": GOOD_TOKEN,   # §3-2 — 쌍이 갖춰져야 나간다
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


# ══ v2.0 §3-1 — hostname 은 API URL 이 아니라 GitHub 호스트다 ══════════
def test_hostname_is_the_github_host_not_the_api_url():
    """gh 의 --hostname 은 GitHub 호스트를 받고 ghinstance 가 `api.` 를 붙인다.

        github.com      → https://api.github.com/       ★맞다
        api.github.com  → https://api.api.github.com/   ★없는 호스트다

    이전 판은 뒤쪽을 주었다. 의미가 다른 정도가 아니라 모든 요청이 깨진다.
    """
    assert gp.ALLOWED_HOSTNAME == "github.com"
    assert not gp.ALLOWED_HOSTNAME.startswith("api."), (
        "API URL 을 넣으면 gh 가 api.api.github.com 으로 간다"
    )


def test_the_previous_wrong_hostname_is_now_refused():
    """옛 값이 되살아나면 잡힌다 — 회귀 방지."""
    argv = ["gh", "api", "--hostname", "api.github.com", "-i", "repos/o/r"]
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_hostname_pinned(argv)
    assert caught.value.code == gp.TRANSPORT_HOST_NOT_ALLOWED


def test_no_production_module_names_the_api_host_as_the_gh_hostname():
    """production 어디에도 `--hostname api.github.com` 조합이 남지 않는다.

    ★시험 트리는 제외한다 — 부정 시험이 그 잘못된 조합을 ★일부러★ 담고 있고,
      그것이 회귀를 잡는 자리이기 때문이다.
    """
    directory = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ac25"
    for path in sorted(directory.rglob("*.py")):
        body = path.read_text(encoding="utf-8")
        assert '"--hostname", "api.github.com"' not in body, path.name
        assert "--hostname api.github.com" not in body, path.name
    # 상수 자체도 확인한다
    assert gp.ALLOWED_HOSTNAME == "github.com"


def test_the_two_host_axes_are_named_apart():
    """감사가 `F03_GH_HOSTNAME_KIND_CONFUSION` 이라 부른 혼동을 이름으로 닫는다.

        REST_API_HOST   요청이 ★실제로 도달하는★ API 호스트  = api.github.com
        gh --hostname   gh 가 받는 ★GitHub 인스턴스 호스트★  = github.com

    둘은 다른 축이고 둘 다 맞다. 한쪽 값을 다른 쪽에 넣으면 깨진다.
    """
    from ac25 import token_preflight as tp

    assert tp.REST_API_HOST == "api.github.com"
    assert gp.ALLOWED_HOSTNAME == "github.com"
    assert tp.REST_API_HOST != gp.ALLOWED_HOSTNAME
    assert tp.REST_API_HOST == "api." + gp.ALLOWED_HOSTNAME


# ══ v2.0 §3-2 — 두 토큰을 첫 요청 전에 함께 본다 ═══════════════════════
def test_token_pair_passes_when_both_are_present():
    gp.require_token_pair(
        approval_env="A", candidate_env="B",
        source_environ={"A": GOOD_TOKEN, "B": GOOD_TOKEN},
    )


@pytest.mark.parametrize(
    "environ",
    [
        {"A": GOOD_TOKEN},                       # 후보 토큰 없음
        {"B": GOOD_TOKEN},                       # 승인 토큰 없음
        {},                                      # 둘 다 없음
        {"A": GOOD_TOKEN, "B": ""},              # 후보가 빈 문자열
        {"A": "", "B": GOOD_TOKEN},              # 승인이 빈 문자열
        {"A": GOOD_TOKEN, "B": "short"},         # 후보가 형식 불량
    ],
)
def test_incomplete_token_pair_is_refused(environ):
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_token_pair(
            approval_env="A", candidate_env="B", source_environ=environ
        )
    assert caught.value.code == gp.TRANSPORT_TOKEN_PAIR_INCOMPLETE


def test_no_request_is_sent_when_only_one_token_exists(monkeypatch, tmp_path):
    """★한쪽만 있어도 승인 저장소 요청부터 나가던 자리다. 이제 0 건이다."""
    from ac25 import output_containment, remote_facts as rf

    # 승인 토큰만 있고 후보 토큰이 없다
    monkeypatch.setattr(
        os, "environ", {"PATH": "/usr/bin", "AC25_APPROVAL_TOKEN": GOOD_TOKEN}
    )
    monkeypatch.setattr(output_containment, "default_runner_temp", lambda: tmp_path)

    sent: list = []

    def explode(*args, **kwargs):
        sent.append(args)
        raise AssertionError("토큰 쌍이 불완전한데 요청을 보냈다")

    monkeypatch.setattr(output_containment, "run_and_read", explode)

    # ★승인 경로조차 보내지 않는다 — 이것이 §3-2 의 요지다
    result = rf.gh_transport_for("AC25_APPROVAL_TOKEN")("repos/o/r")
    assert sent == []
    assert result.status == 0
    assert result.message == gp.TRANSPORT_TOKEN_PAIR_INCOMPLETE

    # 후보 경로도 마찬가지
    result = rf.gh_transport_for("AC25_CANDIDATE_TOKEN")("repos/o/r")
    assert sent == []
    assert result.message == gp.TRANSPORT_TOKEN_PAIR_INCOMPLETE


def test_both_tokens_present_lets_the_request_through(monkeypatch, tmp_path):
    """막기만 하는 게이트는 합격이 아니다 — 둘 다 있으면 나가야 한다."""
    from ac25 import output_containment, remote_facts as rf

    monkeypatch.setattr(os, "environ", {
        "PATH": "/usr/bin",
        "AC25_APPROVAL_TOKEN": GOOD_TOKEN,
        "AC25_CANDIDATE_TOKEN": GOOD_TOKEN,
    })
    monkeypatch.setattr(output_containment, "default_runner_temp", lambda: tmp_path)
    monkeypatch.setattr(
        output_containment, "run_and_read",
        lambda *a, **k: (0, b'HTTP/2 200\r\n\r\n{"ok": true}', b""),
    )
    assert rf.gh_transport_for("AC25_APPROVAL_TOKEN")("repos/o/r").status == 200


# ══ v2.0 §3-3 — proxy·CA 를 자식에게 물려주지 않는다 ═══════════════════
PROXY_AND_CA_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
)


@pytest.mark.parametrize("name", PROXY_AND_CA_NAMES)
def test_proxy_and_ca_names_are_in_the_forbidden_list(name):
    assert name in gp.FORBIDDEN_ENV_NAMES, name


@pytest.mark.parametrize("name", PROXY_AND_CA_NAMES)
def test_proxy_and_ca_names_never_reach_the_child(name, config_dir):
    """★호출이 어디로 가는지·무엇을 신뢰하는지를 바깥에서 바꾸지 못한다."""
    hostile = {"PATH": "/usr/bin", name: "http://attacker.example:3128"}
    env = gp.build_transport_environment(
        token=GOOD_TOKEN, config_dir=config_dir, source_environ=hostile
    ).env
    assert name not in env
    assert "attacker.example" not in "\n".join(f"{k}={v}" for k, v in env.items())


@pytest.mark.parametrize("name", PROXY_AND_CA_NAMES)
def test_injected_proxy_or_ca_is_refused_by_the_final_check(name, config_dir):
    env = gp.build_transport_environment(token=GOOD_TOKEN, config_dir=config_dir).env
    env[name] = "http://attacker.example:3128"
    with pytest.raises(gp.TransportPolicyError) as caught:
        gp.require_minimal_environment(env, config_dir=config_dir)
    assert caught.value.code == gp.TRANSPORT_ENV_NOT_MINIMAL


def test_allowlist_contains_no_proxy_or_ca_name():
    """allowlist 쪽에서도 못박는다 — 나중에 누가 더해도 시험이 잡는다."""
    for name in gp._ENV_ALLOWLIST:
        upper = name.upper()
        assert "PROXY" not in upper, name
        assert "CERT" not in upper, name
        assert "CA_BUNDLE" not in upper, name


def test_full_hostile_environment_yields_exactly_seven_keys(config_dir):
    """proxy·CA·자격을 전부 심어도 자식은 정해진 키만 받는다."""
    hostile = {name: "hostile" for name in gp.FORBIDDEN_ENV_NAMES}
    hostile.update({"PATH": "/usr/bin", "HOME": "/root", "SURPRISE": "x"})
    env = gp.build_transport_environment(
        token=GOOD_TOKEN, config_dir=config_dir, source_environ=hostile
    ).env
    assert set(env) == {
        "PATH", "HOME", "GH_TOKEN", "GH_CONFIG_DIR",
        "GH_NO_UPDATE_NOTIFIER", "GH_PROMPT_DISABLED", "NO_COLOR",
    }
    leaked = {k: v for k, v in env.items() if k != "GH_CONFIG_DIR"}
    assert "hostile" not in "\n".join(leaked.values())


def test_transport_removes_the_config_dir_afterwards(monkeypatch, tmp_path):
    """격리 디렉터리를 남기지 않는다 — 남으면 다음 실행이 물려받는다."""
    from ac25 import output_containment, remote_facts as rf

    monkeypatch.setattr(os, "environ", {
        "PATH": "/usr/bin",
        "AC25_APPROVAL_TOKEN": GOOD_TOKEN,
        "AC25_CANDIDATE_TOKEN": GOOD_TOKEN,
    })
    monkeypatch.setattr(output_containment, "default_runner_temp", lambda: tmp_path)
    monkeypatch.setattr(
        output_containment, "run_and_read",
        lambda *a, **k: (0, b'HTTP/2 200\r\n\r\n{"ok": true}', b""),
    )
    rf.gh_transport_for("AC25_APPROVAL_TOKEN")("repos/o/r")
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("ac25-ghcfg-")]
    assert leftovers == [], leftovers
