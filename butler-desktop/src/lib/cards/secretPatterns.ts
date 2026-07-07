const SECRET_DELIM = String.raw`(?:[:=：]|->|=>)`;

export const SECRET_PATTERN_SOURCE = [
  String.raw`sk-(?:proj-)?[A-Za-z0-9_-]{12,}`,
  String.raw`AKIA[0-9A-Z]{16}`,
  String.raw`ASIA[0-9A-Z]{16}`,
  String.raw`gh[pousr]_[A-Za-z0-9_]{20,}`,
  String.raw`github_pat_[A-Za-z0-9_]{20,}`,
  String.raw`xox[a-z]-[A-Za-z0-9-]{10,}`,
  String.raw`xapp-[A-Za-z0-9-]{10,}`,
  String.raw`(?:api[\s_-]*key|token|password|secret|private[\s_-]*key|access[\s_-]*key|auth[\s_-]*key|client[\s_-]*secret)\s*${SECRET_DELIM}\s*[^\s,;'"<>]{6,}`,
  String.raw`(?:비밀번호|비번|암호|패스워드|API\s*키|에이피아이\s*키|토큰|인증\s*키|보안\s*키|개인\s*키|시크릿)\s*(?:는|은|${SECRET_DELIM})\s*[^\s,;'"<>]{2,}`,
  String.raw`-----BEGIN\s+(?:OPENSSH\s+|RSA\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----`,
  String.raw`\bseed\s*phrase\s*${SECRET_DELIM}\s*(?:[a-z]{3,16}\s+){5,23}[a-z]{3,16}\b`,
].join('|');

export const SECRET_TEXT_RE = new RegExp(SECRET_PATTERN_SOURCE, 'i');

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
];

export const SECRET_NEGATIVE_FIXTURES = [
  'our_data.api_key',
  'FORBIDDEN_SECRET_FIELD',
  'API key 필드는 미기입',
  '비밀번호 정책 변경 안내',
  'client_secret 필드는 비워두세요',
  '토큰 항목은 UNFILLED로 남겨야 합니다',
  'source_ref: attachment_digest_01',
  'reason_code: FIELD_NOT_FOUND',
];

export function containsSecretLikeText(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  if (value.length > 100_000) return true;
  return SECRET_TEXT_RE.test(value);
}

export function assertNoSecretLikeText(value: unknown, fieldPath: string): void {
  if (containsSecretLikeText(value)) {
    const err = new Error(`SENSITIVE_OUTPUT_BLOCKED:${fieldPath}`);
    err.name = 'SensitiveOutputBlockedError';
    throw err;
  }
}
