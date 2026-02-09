# P0 Healthz Proof (Text Evidence)

## 기준 시각
2026-02-09T04:25:28.449Z (UTC)

## 실행 커맨드
```bash
curl -i http://127.0.0.1:8081/healthz
```

## 출력 본문
```json
{"status":"ok","timestamp":"2026-02-09T04:25:28.449Z","buildSha":"2e8e5564049b690679336ae452b4ef7016907dd4","buildShaShort":"2e8e556","buildTime":"2026-02-09T04:23:25.401Z"}
```

## PASS 조건
- HTTP 200 응답
- buildSha 존재 (2e8e5564049b690679336ae452b4ef7016907dd4)

## 검증 결과
✅ PASS

