export function assertInternalUrlOrThrow(urlStr) {
  const u = new URL(urlStr);
  // 기본 deny: 외부 호출은 무조건 금지.
  // 내부망 허용이 필요해지는 시점(후속 PR)에서 allowlist(사설 CIDR/내부 DNS)를 SSOT로 고정하고 열어준다.
  throw new Error("RUNTIME_EGRESS_DENY_DEFAULT_FAILCLOSED");
}
