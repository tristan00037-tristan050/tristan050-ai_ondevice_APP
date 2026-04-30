# Butler PC Core — Day 1.5 Hotfix 증거

**날짜**: 2026-04-30  
**브랜치**: `hotfix/day1-codex-review`  
**트리거**: Codex Connector PR #644 머지 직후 P1·P2 결함 발견

---

## 수정 항목

### P1 — Partial Result 안전 직렬화

**위치**: `butler_pc_core/runtime/timeout_controller.py`

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| `json.dumps` | `default` 인자 없음 → set/bytes 직렬화 시 `TypeError` | `default=_safe_json_default` 추가 |
| 직렬화 실패 시 | 예외 전파 → partial_result.json 미생성 | fallback 최소 메타데이터 파일 강제 생성 |
| fallback 내용 | — | task_id, completed_count, error_class, saved_at |

**추가된 `_safe_json_default` 처리 범위**:
- `set / frozenset` → `{"__type__": "set", "values": [...]}`
- `bytes` → `{"__type__": "bytes", "size": N, "preview": "hex..."}`
- `__dict__` 보유 객체 → `{"__type__": "ClassName", "repr": "..."}`
- 그 외 → `{"__type__": "unserializable", "repr": "..."}`

---

### P2 — 비파일 경로 사전 거절

**위치**: `butler_pc_core/router/task_budget_router.py`, `butler_sidecar.py`

| 입력 유형 | 수정 전 | 수정 후 |
|---------|---------|---------|
| 디렉터리 | `st_size` 호출 → `IsADirectoryError` (OS 레벨, 메시지 불명확) | 명시적 `IsADirectoryError("폴더가 아닌 개별 파일을...")` |
| 존재하지 않는 경로 | `FileNotFoundError` (기존 동작) | 동일 (메시지 한국어 명확화) |
| 빈 파일 (0 바이트) | `tier="S"` 로 잘못 분류 | `tier="empty"`, `blocked=True`, 처리 거부 |
| 심볼릭 링크 (broken) | 비정형 예외 | `FileNotFoundError` (대상 없음) |
| 일반 파일이 아닌 경우 | 미처리 | `NotAFileError` (신규 커스텀 예외) |

**/api/precheck HTTP 매핑**:

| 예외 | 이전 응답 | 이후 응답 |
|------|---------|---------|
| `IsADirectoryError` | 500 Internal Error | **422** "폴더가 아닌 개별 파일을 첨부해 주세요" |
| `NotAFileError` | 500 Internal Error | **422** "원본 파일을 직접 첨부해 주세요" |
| 빈 파일 | 200 tier=S | **200** tier=empty, blocked=True (정상 응답, 클라이언트가 blocked 체크) |

---

## 회귀 테스트 결과

```
tests/butler_pc_core/test_partial_result_serialization.py (P1 — 5케이스)
  TestSetContent::test_set_serializes_safely           PASSED
  TestBytesContent::test_bytes_serializes_safely       PASSED
  TestNestedSetContent::test_nested_set_in_dict        PASSED
  TestUnserializableFallback::test_fallback_file_created PASSED
  TestNormalDictContent::test_normal_dict_preserved    PASSED

tests/butler_pc_core/test_router_invalid_paths.py (P2 — 5케이스)
  TestInvalidPaths::test_01_directory_raises           PASSED
  TestInvalidPaths::test_02_missing_path_raises        PASSED
  TestInvalidPaths::test_03_empty_file_refused         PASSED
  TestInvalidPaths::test_04_symlink_raises             PASSED
  TestInvalidPaths::test_05_normal_file_works          PASSED

tests/butler_pc_core/test_task_budget_router.py (기존 13케이스 — 회귀 없음)
  ... 13 passed

총계: 23 passed in 0.03s  ✅ 회귀 없음
```

---

## 수정 파일 목록

| 파일 | 변경 내용 |
|------|---------|
| `butler_pc_core/runtime/timeout_controller.py` | `_safe_json_default` 추가, `_save_partial` fallback 로직, `datetime` import |
| `butler_pc_core/router/task_budget_router.py` | `NotAFileError` 커스텀 예외, `classify_file` 진입부 4가지 검증, `tier="empty"` 반환 |
| `butler_sidecar.py` | `NotAFileError` import, `IsADirectoryError`/`NotAFileError` → 422 매핑 |
| `tests/butler_pc_core/test_partial_result_serialization.py` | 신규 (P1 5케이스) |
| `tests/butler_pc_core/test_router_invalid_paths.py` | 신규 (P2 5케이스) |
