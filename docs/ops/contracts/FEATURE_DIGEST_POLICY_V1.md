# FEATURE_DIGEST_POLICY_V1

FEATURE_DIGEST_POLICY_V1_TOKEN=1

- 목적: fingerprint(해시)만으로는 해석이 어려우므로, meta-only로 "왜 달라졌는지" 좁힐 수 있는 feature_digest_v1을 추가한다.
- 불가침: meta-only / 원문0 / 배열 덤프 금지 / 긴 문자열 금지
- 값 제약:
  - 타입: string|number|boolean|null만 허용
  - 문자열 길이: 64자 초과 금지
- 키 제약:
  - 허용 키는 FEATURE_DIGEST_ALLOWED_KEYS_V1.txt에 있는 키만 허용
