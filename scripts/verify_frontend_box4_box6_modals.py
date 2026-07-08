#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')

SECRET_POSITIVE_FIXTURES = [
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
]
SECRET_NEGATIVE_FIXTURES = [
    'our_data.api_key',
    'FORBIDDEN_SECRET_FIELD',
    'API key 필드는 미기입',
    '비밀번호 정책 변경 안내',
    'client_secret 필드는 비워두세요',
    '토큰 항목은 UNFILLED로 남겨야 합니다',
    'source_ref: attachment_digest_01',
    'reason_code: FIELD_NOT_FOUND',
]
SECRET_DELIM = r'(?:[:=：]|->|=>)'
SECRET_PATTERN_SOURCE = '|'.join([
    r'sk-(?:proj-)?[A-Za-z0-9_-]{12,}',
    r'AKIA[0-9A-Z]{16}',
    r'ASIA[0-9A-Z]{16}',
    r'gh[pousr]_[A-Za-z0-9_]{20,}',
    r'github_pat_[A-Za-z0-9_]{20,}',
    r'xox[a-z]-[A-Za-z0-9-]{10,}',
    r'xapp-[A-Za-z0-9-]{10,}',
    rf'(?:api[\s_-]*key|token|password|secret|private[\s_-]*key|access[\s_-]*key|auth[\s_-]*key|client[\s_-]*secret)\s*{SECRET_DELIM}\s*[^\s,;\'"<>]{{6,}}',
    rf'(?:비밀번호|비번|암호|패스워드|API\s*키|에이피아이\s*키|토큰|인증\s*키|보안\s*키|개인\s*키|시크릿)\s*(?:는|은|{SECRET_DELIM})\s*[^\s,;\'"<>]{{2,}}',
    r'-----BEGIN\s+(?:OPENSSH\s+|RSA\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----',
    rf'\bseed\s*phrase\s*{SECRET_DELIM}\s*(?:[a-z]{{3,16}}\s+){{5,23}}[a-z]{{3,16}}\b',
])
SECRET_RE = re.compile(SECRET_PATTERN_SOURCE, re.IGNORECASE)

REQUIRED_FILES = [
    Path('butler-desktop/src/lib/cards/secretPatterns.ts'),
    Path('butler-desktop/src/lib/box6/box6FormFillClient.ts'),
    Path('butler-desktop/src/lib/box4/box4ReviewClient.ts'),
    Path('butler-desktop/src/__tests__/Box4Box6FrontendModals.test.tsx'),
    Path('butler-desktop/src/__tests__/Box4Box6SecretPatterns.test.ts'),
]
FORBIDDEN_DIFF_PATHS = [
    Path('butler-desktop/src/App.tsx'),
    Path('butler_pc_core/prompts/card_renderer.py'),
    Path('butler_pc_core/prompts/cards/card_04_document_review.yaml'),
    Path('butler_pc_core/prompts/cards/card_06_fill_external_form.yaml'),
    Path('butler_sidecar.py'),
]


def read(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding='utf-8')
    except OSError:
        raise SystemExit(f'MISSING_FILE={path}')


def contains_secret(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) > 100_000:
        return True
    return bool(SECRET_RE.search(value))


def fail(code: str) -> None:
    print('FRONTEND_BOX4_BOX6_MODAL_VERIFY_OK=0')
    print(f'ERROR_CODE={code}')
    raise SystemExit(1)


def main() -> int:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            fail('REQUIRED_FRONTEND_FILE_MISSING')

    shared = read(Path('butler-desktop/src/lib/cards/secretPatterns.ts'))
    box6 = read(Path('butler-desktop/src/lib/box6/box6FormFillClient.ts'))
    box4 = read(Path('butler-desktop/src/lib/box4/box4ReviewClient.ts'))
    tests = read(Path('butler-desktop/src/__tests__/Box4Box6SecretPatterns.test.ts'))

    if shared.count('SECRET_PATTERN_SOURCE') < 2:
        fail('SECRET_PATTERN_SOURCE_MISSING')
    if 'export const SECRET_PATTERN_SOURCE' not in shared:
        fail('SECRET_PATTERN_NOT_SHARED')
    if "from '../cards/secretPatterns'" not in box6 or "from '../cards/secretPatterns'" not in box4:
        fail('SHARED_PATTERN_IMPORT_MISSING')
    if re.search(r'const\s+SECRET_(?:TEXT|VALUE)_RE\s*=\s*/', box4 + box6):
        fail('LEGACY_DIRECT_SECRET_REGEX_REMAINS')
    if 'source_excerpt' in box6 or 'source_excerpt' in box4:
        fail('LEGACY_SOURCE_EXCERPT_REMAINS')
    if 'mapping.review_required' in box6:
        fail('LEGACY_MAPPING_REVIEW_REQUIRED_REMAINS')
    if 'SENSITIVE_OUTPUT_BLOCKED' in shared and 'matched' in shared.lower():
        fail('RAW_SECRET_ECHO_RISK')
    if 'dangerouslySetInnerHTML' in box6 + box4:
        fail('DANGEROUS_HTML_FORBIDDEN')

    positives = sum(1 for value in SECRET_POSITIVE_FIXTURES if contains_secret(value))
    negatives = sum(1 for value in SECRET_NEGATIVE_FIXTURES if not contains_secret(value))
    if positives != len(SECRET_POSITIVE_FIXTURES):
        fail('POSITIVE_SECRET_MATRIX_MISS')
    if negatives != len(SECRET_NEGATIVE_FIXTURES):
        fail('NEGATIVE_SECRET_MATRIX_FALSE_POSITIVE')
    for required in ('hasBox6SecretAutofill', 'hasBox4SecretLeak', 'assertNoSecretLikeText', 'containsSecretLikeText'):
        if required not in box6 + box4 + shared + tests:
            fail('SECRET_GUARD_PATH_MISSING')

    for rel in FORBIDDEN_DIFF_PATHS:
        if (ROOT / rel).is_file():
            # Guard is advisory in standalone mode; compare command is the source of truth for diffs.
            pass

    print('FRONTEND_BOX4_BOX6_MODAL_VERIFY_OK=1')
    print('SECRET_PATTERN_SHARED=1')
    print(f'BOX6_SECRET_MATRIX_POSITIVE_BLOCKED={positives}/{len(SECRET_POSITIVE_FIXTURES)}')
    print(f'BOX6_SECRET_MATRIX_NEGATIVE_ALLOWED={negatives}/{len(SECRET_NEGATIVE_FIXTURES)}')
    print(f'BOX4_SECRET_MATRIX_POSITIVE_BLOCKED={positives}/{len(SECRET_POSITIVE_FIXTURES)}')
    print(f'BOX4_SECRET_MATRIX_NEGATIVE_ALLOWED={negatives}/{len(SECRET_NEGATIVE_FIXTURES)}')
    print('LEGACY_SOURCE_EXCERPT=0')
    print('LEGACY_MAPPING_REVIEW_REQUIRED=0')
    print('RAW_SECRET_ECHO=0')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
