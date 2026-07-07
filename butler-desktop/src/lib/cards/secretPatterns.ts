const SECRET_DELIM = String.raw`(?:[:=：]|->|=>)`;

export const SECRET_PATTERN_SOURCE = [
  // OpenAI-style / generic sk token, including sk-proj-.
  String.raw`sk-(?:proj-)?[A-Za-z0-9_-]{12,}`,
  // AWS access key IDs and temporary session key IDs.
  String.raw`AKIA[0-9A-Z]{16}`,
  String.raw`ASIA[0-9A-Z]{16}`,
  // GitHub classic and fine-grained token families.
  String.raw`gh[pousr]_[A-Za-z0-9_]{20,}`,
  String.raw`github_pat_[A-Za-z0-9_]{20,}`,
  // Slack bot/user/app token families.
  String.raw`xox[a-z]-[A-Za-z0-9-]{10,}`,
  String.raw`xapp-[A-Za-z0-9-]{10,}`,
  // English key/value labels. A delimiter is required to avoid label-only false positives.
  String.raw`(?:api[\s_-]*key|token|password|secret|private[\s_-]*key|access[\s_-]*key|auth[\s_-]*key|client[\s_-]*secret)\s*${SECRET_DELIM}\s*[^\s,;'"<>]{6,}`,
  // Korean key/value labels. A particle or delimiter is required to avoid policy/label false positives.
  String.raw`(?:비밀번호|비번|암호|패스워드|API\s*키|에이피아이\s*키|토큰|인증\s*키|보안\s*키|개인\s*키|시크릿)\s*(?:는|은|${SECRET_DELIM})\s*[^\s,;'"<>]{2,}`,
  // Private key block headers.
  String.raw`-----BEGIN\s+(?:OPENSSH\s+|RSA\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----`,
  // Seed phrase, capped to avoid pathological matching.
  String.raw`\bseed\s*phrase\s*${SECRET_DELIM}\s*(?:[a-z]{3,16}\s+){5,23}[a-z]{3,16}\b`,
].join('|');

export const SECRET_TEXT_RE = new RegExp(SECRET_PATTERN_SOURCE, 'i');

export function containsSecretLikeText(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  if (value.length > 100_000) return true;
  return SECRET_TEXT_RE.test(value);
}

export function assertNoSecretLikeText(value: unknown, fieldPath: string): void {
  if (containsSecretLikeText(value)) {
    const error = new Error(`SENSITIVE_OUTPUT_BLOCKED:${fieldPath}`);
    error.name = 'SensitiveOutputBlockedError';
    throw error;
  }
}
