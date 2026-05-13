# Anonymization Standard (단계 6.5.5 Day 1)

## 1. 원칙

- **raw 입력 미보관**. 원문 텍스트와 첨부 파일 원문은 EvalSet 에 저장 금지.
- **digest16 만 보관**. 원문의 sha256 해시 앞 16자만 중복 방지 목적으로 보관 (복원 불가).
- **표준 토큰 치환**. PII / 식별 가능 정보는 21종 표준 토큰으로 치환.
- **익명화 후 검증**. `check_pii_leak.py` 가 한 번 더 본문을 검사하여 잔존 PII 차단.

## 2. 표준 치환 토큰 21종

| 토큰 | 대상 | 예시 (치환 전 → 후) |
|------|------|---------------------|
| `[PERSON]` | 사람 이름 | 김부장 → [PERSON] |
| `[TEAM]` | 팀 / 부서 | 개발팀 → [TEAM] |
| `[COMPANY]` | 회사 / 조직 | ㈜버틀러 → [COMPANY] |
| `[DOCUMENT]` | 문서 / 파일명 | 견적서_v2.xlsx → [DOCUMENT] |
| `[PROJECT]` | 프로젝트 / 제품명 | Project-X → [PROJECT] |
| `[DATE]` | 절대 날짜 | 2026-05-13 → [DATE] |
| `[TIME]` | 시각 | 14:30 → [TIME] |
| `[EMAIL]` | 이메일 | user@example.com → [EMAIL] |
| `[PHONE]` | 전화 번호 | 010-1234-5678 → [PHONE] |
| `[URL]` | URL | https://example.com → [URL] |
| `[ACCOUNT]` | 계좌 / 사번 | 110-123-456789 → [ACCOUNT] |
| `[AMOUNT]` | 금액 | 1,234,567원 → [AMOUNT] |
| `[ADDRESS]` | 주소 | 서울시 강남구 ... → [ADDRESS] |
| `[ID]` | 식별자 (user-id, ticket-id) | TKT-12345 → [ID] |
| `[VERSION]` | 버전 | v1.2.3 → [VERSION] |
| `[PR]` | Pull Request 번호 | PR #123 → [PR] |
| `[BRANCH]` | Git 브랜치명 | feat/foo-bar → [BRANCH] |
| `[COMMIT]` | Git SHA | a1b2c3d → [COMMIT] |
| `[SERVER]` | 서버 / 호스트 / IP | 10.0.0.1 → [SERVER] |
| `[PATH]` | 파일 경로 | /var/log/app.log → [PATH] |
| `[SECRET]` | API key / token / 비밀번호 | sk_live_... → [SECRET] |

치환 결과에서 위 토큰 자체는 보관 OK (원문 식별 불가).

## 3. raw_text 금지 키 5개

EvalSet JSONL 어떤 sample 도 다음 키를 포함 금지:

1. `raw_text`
2. `original_text`
3. `plain_text`
4. `user_text`
5. `source_text`

검사: `scripts/evalset/check_no_raw_text.py` — JSON value 재귀 순회 시 key 가 위 목록에 있으면 fail.

## 4. digest16 형식

```
sha256:<16 hex>
```

- 정규식: `^sha256:[0-9a-f]{16}$`
- 산출: `hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]` → `f"sha256:{digest[:16]}"`
- 용도: EvalSet 내 중복 sample 차단, 동일 입력의 라벨 일관성 모니터링.
- 복원 불가. 32-bit hash 비교만 가능.

## 5. PII leak 판정 기준

`check_pii_leak.py` 가 다음 5종 잔존 패턴을 본문에서 검출 시 fail:

| 잔존 패턴 | 정규식 |
|-----------|--------|
| EMAIL | `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` |
| PHONE | `(?<!\d)0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)` |
| SERVER_IP | `(?<!\d)(\d{1,3}\.){3}\d{1,3}(?!\d)` |
| SECRET | `(sk[_-]live[_-][A-Za-z0-9]+\|AKIA[0-9A-Z]{16}\|ghp_[A-Za-z0-9]{36})` |
| CARD | `(?<!\d)(\d{4}[- ]?){3}\d{4}(?!\d)` |

검출 1건이라도 있으면 PII leak count > 0 → CI Gate fail.
