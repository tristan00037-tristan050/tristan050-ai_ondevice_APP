#!/bin/bash
# 데이터베이스 백업 스크립트
# PostgreSQL 데이터베이스 백업 및 검증

set -e

# 환경 변수
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-collector}"
DB_USER="${DB_USER:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

# 백업 파일명 (타임스탬프 포함)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/collector_${TIMESTAMP}.sql.gz"

echo "🔄 Starting database backup..."
echo "Database: $DB_NAME"
echo "Backup file: $BACKUP_FILE"

# PostgreSQL 백업 실행
PGPASSWORD="${DB_PASSWORD}" pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --no-owner \
  --no-acl \
  | gzip > "$BACKUP_FILE"

# 백업 파일 검증
if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
  BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
  echo "✅ Backup completed successfully"
  echo "Backup size: $BACKUP_SIZE"
  
  # 백업 파일 무결성 검증 (gzip 테스트)
  if gzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo "✅ Backup file integrity verified"
  else
    echo "❌ Backup file integrity check failed"
    rm -f "$BACKUP_FILE"
    exit 1
  fi
else
  echo "❌ Backup failed: file not created or empty"
  exit 1
fi

# 오래된 백업 파일 삭제 (보존 정책)
echo "🧹 Cleaning up old backups (retention: $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "collector_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
echo "✅ Cleanup completed"

# 백업 목록 출력
echo ""
echo "📦 Available backups:"
ls -lh "$BACKUP_DIR"/collector_*.sql.gz 2>/dev/null || echo "No backups found"


