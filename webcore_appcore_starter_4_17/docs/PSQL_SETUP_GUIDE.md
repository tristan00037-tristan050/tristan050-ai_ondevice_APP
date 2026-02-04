# psql 설치 및 사용 가이드

## 문제: `psql: command not found`

`psql` 명령어가 없는 경우, 다음 방법 중 하나를 사용하세요.

---

## 방법 1: Docker를 통한 psql 사용 (권장)

### Docker Compose로 PostgreSQL 실행 중인 경우

```bash
# PostgreSQL 컨테이너에 직접 접속
docker compose exec db psql -U app -d app

# 또는 컨테이너 이름 확인 후
docker ps | grep postgres
docker exec -it <container_name> psql -U app -d app
```

### Docker Compose 없이 직접 실행

```bash
# PostgreSQL 컨테이너에서 psql 실행
docker run -it --rm \
  --network host \
  postgres:16 \
  psql "postgres://app:app@localhost:5432/app"
```

### SQL 파일 실행

```bash
# Docker Compose 사용
docker compose exec -T db psql -U app -d app < scripts/check_audit_events.sql

# 또는 직접 실행
docker run -i --rm \
  --network host \
  -v "$(pwd)/scripts:/scripts" \
  postgres:16 \
  psql "postgres://app:app@localhost:5432/app" -f /scripts/check_audit_events.sql
```

---

## 방법 2: Homebrew로 PostgreSQL 설치

### 설치

```bash
# PostgreSQL 설치 (psql 포함)
brew install postgresql@16

# 또는 최신 버전
brew install postgresql
```

### PATH 설정

```bash
# zsh 사용 시 (~/.zshrc에 추가)
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 또는 bash 사용 시 (~/.bash_profile에 추가)
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
```

### 확인

```bash
which psql
psql --version
```

### 사용

```bash
# DATABASE_URL 설정
export DATABASE_URL="postgres://app:app@localhost:5432/app"

# psql 접속
psql $DATABASE_URL
```

---

## 방법 3: Node.js 스크립트로 대체 (임시)

psql이 없어도 Node.js 스크립트로 쿼리를 실행할 수 있습니다.

### 간단한 쿼리 실행 스크립트

`scripts/run_query.mjs` 파일 생성:

```javascript
#!/usr/bin/env node
import { Pool } from 'pg';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// .env 파일 로드
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const projectRoot = join(__dirname, '..');
const envPath = join(projectRoot, '.env');

try {
  const envContent = readFileSync(envPath, 'utf8');
  envContent.split('\n').forEach(line => {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#')) {
      const [key, ...valueParts] = trimmed.split('=');
      if (key && valueParts.length > 0) {
        const value = valueParts.join('=').trim();
        if (!process.env[key]) {
          process.env[key] = value;
        }
      }
    }
  });
} catch {}

const dbUrl = process.env.DATABASE_URL;
if (!dbUrl) {
  console.error('❌ DATABASE_URL 환경변수가 설정되지 않았습니다.');
  process.exit(1);
}

const pool = new Pool({ connectionString: dbUrl });

async function main() {
  const query = process.argv[2];
  if (!query) {
    console.error('사용법: node scripts/run_query.mjs "SELECT * FROM ..."');
    process.exit(1);
  }

  try {
    const result = await pool.query(query);
    console.log(JSON.stringify(result.rows, null, 2));
  } catch (error) {
    console.error('❌ 오류:', error.message);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

main();
```

### 사용 예시

```bash
# 승인 이벤트 확인
node scripts/run_query.mjs "SELECT action, payload->>'top1_selected' AS top1_selected FROM accounting_audit_events WHERE action = 'approval_apply' ORDER BY ts DESC LIMIT 5"
```

---

## 빠른 참조: Docker를 통한 psql 명령어

### 1. 승인 이벤트 확인

```bash
docker compose exec db psql -U app -d app -c "
SELECT 
  action, 
  payload->>'top1_selected' AS top1_selected,
  payload->>'selected_rank' AS selected_rank,
  payload->>'ai_score' AS ai_score,
  ts
FROM accounting_audit_events
WHERE action = 'approval_apply'
ORDER BY ts DESC
LIMIT 10;
"
```

### 2. Manual Review 이벤트 확인

```bash
docker compose exec db psql -U app -d app -c "
SELECT 
  action, 
  payload->>'reason_code' AS reason_code,
  payload->>'amount' AS amount,
  payload->>'currency' AS currency,
  payload->>'is_high_value' AS is_high_value,
  ts
FROM accounting_audit_events
WHERE action = 'manual_review_request'
ORDER BY ts DESC
LIMIT 10;
"
```

### 3. External Sync 이벤트 확인

```bash
docker compose exec db psql -U app -d app -c "
SELECT 
  action,
  payload->>'source' AS source,
  payload->>'error' AS error,
  ts
FROM accounting_audit_events
WHERE action IN ('external_sync_start','external_sync_success','external_sync_error')
ORDER BY ts DESC
LIMIT 20;
"
```

### 4. 대화형 psql 세션 시작

```bash
docker compose exec db psql -U app -d app
```

대화형 세션에서:

```sql
-- 승인 이벤트 확인
SELECT action, payload->>'top1_selected' AS top1_selected, ts
FROM accounting_audit_events
WHERE action = 'approval_apply'
ORDER BY ts DESC
LIMIT 10;

-- 종료
\q
```

---

## 추천 방법

**현재 상황:** Docker가 설치되어 있고 `docker-compose.yml`이 있음

**권장:** 방법 1 (Docker를 통한 psql 사용)

```bash
# 가장 간단한 방법
docker compose exec db psql -U app -d app
```

이 방법은 PostgreSQL을 별도로 설치할 필요가 없고, Docker Compose로 실행 중인 데이터베이스에 바로 접속할 수 있습니다.

