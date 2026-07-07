export const SECRET_POSITIVE_FIXTURES = [
  'ASIA1234567890ABCDEF',
  'AKIA1234567890ABCDEF',
  'ghp_abcdefghijklmnopqrstuv',
  'gho_abcdefghijklmnopqrstuv',
  'github_pat_abcdefghijklmnopqrstuv_1234567890',
  'xoxb-1234567890-abcdef',
  'xapp-1-A1234567890-1234567890-abcdef',
  'access_key: xyz999999',
  'auth_key=abcdef123456',
  'client_secret: qqqqqq',
  'API 키: sk-실제값123456',
  '토큰은 abcd1234567',
  '인증 키: zzzzzzzz',
  '보안 키는 111111',
  '개인 키: aaaaaaaaaa',
  '-----BEGIN OPENSSH PRIVATE KEY-----',
] as const;

export const SECRET_NEGATIVE_FIXTURES = [
  'our_data.api_key',
  'FORBIDDEN_SECRET_FIELD',
  'API key 필드는 미기입',
  '비밀번호 정책 변경 안내',
  'client_secret 필드는 비워두세요',
  '토큰 항목은 UNFILLED로 남겨야 합니다',
  'source_ref: attachment_digest_01',
  'reason_code: FIELD_NOT_FOUND',
] as const;
