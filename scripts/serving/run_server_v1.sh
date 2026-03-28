#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(pwd)}"
HOST="${BUTLER_HOST:-0.0.0.0}"
PORT="${BUTLER_PORT:-8000}"
VENV_PATH="${BUTLER_VENV_PATH:-/root/butler-venv/bin/activate}"

echo '================================================'
echo '  Butler AI 서빙 서버 시작'
echo "  주소: http://$HOST:$PORT"
echo '  외부 전송: 없음 (온프레미스)'
echo '================================================'

cd "$REPO_DIR"

if [ -f "$VENV_PATH" ]; then
  # shellcheck disable=SC1090
  source "$VENV_PATH"
fi

python - <<'PYEOF'
import importlib
required = ['fastapi', 'uvicorn', 'pydantic']
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit('필수 패키지 누락: ' + ', '.join(missing))
print('DEPENDENCY_CHECK_OK=1')
PYEOF

if [ -z "${BUTLER_API_KEYS:-}" ]; then
  echo '[경고] BUTLER_API_KEYS 미설정 — production에서는 반드시 설정하십시오.'
fi

exec uvicorn scripts.serving.butler_server_v1:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  --log-level info \
  --timeout-keep-alive 30
