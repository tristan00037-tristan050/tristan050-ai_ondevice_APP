#!/bin/bash
# 데이터베이스 복원 스크립트
# PostgreSQL 데이터베이스 복원

set -e

# 환경 변수
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-collector}"
DB_USER="${DB_USER:-postgres}"
BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 <backup_file.sql.gz>"
  echo "Example: $0 ./backups/collector_20250101_120000.sql.gz"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "❌ Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "🔄 Starting database restore..."
echo "Database: $DB_NAME"
echo "Backup file: $BACKUP_FILE"

# 백업 파일 무결성 검증
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
  echo "❌ Backup file integrity check failed"
  exit 1
fi

# 확인 프롬프트
read -p "⚠️  This will overwrite the existing database. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
  echo "Restore cancelled"
  exit 0
fi

# 데이터베이스 연결 확인
if ! PGPASSWORD="${DB_PASSWORD}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
  echo "❌ Cannot connect to database"
  exit 1
fi

# 데이터베이스 복원
echo "📥 Restoring database..."
gunzip -c "$BACKUP_FILE" | PGPASSWORD="${DB_PASSWORD}" psql \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME"

echo "✅ Database restore completed successfully"

