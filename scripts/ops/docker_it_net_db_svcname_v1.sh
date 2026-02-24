#!/usr/bin/env bash
# PR-P0-DEPLOY-03: Docker integration test network + postgres16 service name (SSOT).
# User-defined bridge it-net-v1, DB host=postgres16. No host.docker.internal.
# Output: key=value only (meta-only, no connection strings/secrets).
set -euo pipefail

docker_it_net_name="it-net-v1"
docker_db_container_name="postgres16"
docker_bff_container_name="bff"
docker_db_port="5432"
docker_db_host="postgres16"
docker_database_url_scheme="postgres"

# Required output keys (emit on exit)
emit() {
  echo "docker_it_net_exit_code=${1:-0}"
  echo "docker_it_net_name=$docker_it_net_name"
  echo "docker_db_container_name=$docker_db_container_name"
  echo "docker_bff_container_name=$docker_bff_container_name"
  echo "docker_db_port=$docker_db_port"
  echo "docker_db_host=$docker_db_host"
  echo "docker_database_url_scheme=$docker_database_url_scheme"
  if [[ -n "${docker_it_net_fail_class:-}" ]]; then echo "docker_it_net_fail_class=$docker_it_net_fail_class"; fi
  if [[ -n "${docker_it_net_fail_hint:-}" ]]; then echo "docker_it_net_fail_hint=$docker_it_net_fail_hint"; fi
}

fail() {
  docker_it_net_fail_class="${1:-unknown}"
  docker_it_net_fail_hint="${2:-}"
  emit 1
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "tool_missing" "docker not found"

# Create network if not exists
if ! docker network inspect "$docker_it_net_name" >/dev/null 2>&1; then
  if ! docker network create "$docker_it_net_name" >/dev/null 2>&1; then
    fail "network_create_failed" "docker network create $docker_it_net_name failed"
  fi
fi

# Ensure postgres16 running (idempotent)
if ! docker ps -q -f "name=^${docker_db_container_name}$" | grep -q .; then
  docker rm -f "$docker_db_container_name" >/dev/null 2>&1 || true
  if ! docker run -d --name "$docker_db_container_name" \
    --network "$docker_it_net_name" \
    -p "${docker_db_port}:5432" \
    -e POSTGRES_USER=u \
    -e POSTGRES_PASSWORD=p \
    -e POSTGRES_DB=app \
    postgres:16 \
    >/dev/null 2>&1; then
    fail "container_start_failed" "postgres16 start failed"
  fi
  # Wait for postgres ready
  for i in $(seq 1 30); do
    if docker run --rm --network "$docker_it_net_name" postgres:16 pg_isready -h "$docker_db_host" -p "$docker_db_port" -U u -d app >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
    if [[ "$i" -eq 30 ]]; then
      fail "db_connect_failed" "postgres16 not ready"
    fi
  done
fi

# If BFF_IMAGE not set, only network+postgres (caller runs migrate then re-invokes with BFF_IMAGE)
if [[ -z "${BFF_IMAGE:-}" ]]; then
  emit 0
  exit 0
fi

# Start BFF on same network (host=postgres16)
docker rm -f "$docker_bff_container_name" >/dev/null 2>&1 || true
# DATABASE_URL host must be postgres16 (no host.docker.internal)
if ! docker run -d --name "$docker_bff_container_name" \
  --network "$docker_it_net_name" \
  -p 8081:8081 \
  -e PORT=8081 \
  -e USE_PG=1 \
  -e "DATABASE_URL=postgres://u:p@${docker_db_host}:${docker_db_port}/app" \
  -e EXPORT_SIGN_SECRET="ci-secret" \
  "$BFF_IMAGE" \
  >/dev/null 2>&1; then
  fail "container_start_failed" "bff start failed"
fi

# Meta-only: /readyz 200
for i in $(seq 1 120); do
  if curl -fsS --max-time 2 "http://127.0.0.1:8081/readyz" >/dev/null 2>&1; then
    emit 0
    exit 0
  fi
  sleep 0.5
  if [[ "$i" -eq 120 ]]; then
    fail "db_connect_failed" "bff /readyz not 200"
  fi
done

emit 0
exit 0
