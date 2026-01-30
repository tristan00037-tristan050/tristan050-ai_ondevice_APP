# Model Pack v0 Format (SSOT)

## 목적
- Model Pack은 "부서/업무 특화 모델/리소스 패키지"를 서명된 배포 단위로 제공합니다.
- v0 포맷은 서명된 manifest와 fail-closed 검증을 포함합니다.

## 파일 구조

각 Model Pack은 다음 파일로 구성됩니다:

```
model_packs/<pack_name>/
  pack.json          # 메타 정보 (name, version, dept, created_at_utc)
  manifest.json      # 파일 목록 + 각 파일의 SHA256 해시
  signature.json     # Ed25519 서명 (key_id, signature_b64, public_key_b64)
  payload/           # 실제 리소스 파일들
    rules.json       # 규칙 정의
    templates.json   # 템플릿 정의
    ...              # 기타 리소스
```

## pack.json 스키마

```json
{
  "schema_name": "MODEL_PACK_V0",
  "name": "<pack_name>",
  "version": "<semver>",
  "dept": "<department>",
  "created_at_utc": "<ISO8601>"
}
```

## manifest.json 스키마

```json
{
  "schema_name": "MODEL_PACK_MANIFEST_V0",
  "pack_name": "<pack_name>",
  "created_at_utc": "<ISO8601>",
  "files": [
    {
      "path": "pack.json",
      "sha256": "<hex>"
    },
    {
      "path": "payload/rules.json",
      "sha256": "<hex>"
    }
  ]
}
```

## signature.json 스키마

```json
{
  "schema_name": "MODEL_PACK_SIGNATURE_V0",
  "key_id": "<string>",
  "signature_b64": "<base64>",
  "public_key_b64": "<base64>",
  "signed_at_utc": "<ISO8601>"
}
```

## 검증 규칙 (Fail-Closed)

1. **manifest.json 필수**: 없으면 즉시 실패
2. **SHA256 일치**: manifest의 sha256과 실제 파일 해시가 일치해야 함
3. **서명 검증**: signature.json의 서명이 manifest.json에 대해 유효해야 함
4. **PRIVATE KEY 금지**: 레포에 private key 원문/복호화 가능한 형태 커밋 금지

## DoD Keys

- MODEL_PACK_SCHEMA_SSOT_OK=1
- MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=1
- MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=1
- MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=1
- MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=1

